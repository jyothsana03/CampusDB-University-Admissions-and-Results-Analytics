#!/usr/bin/env python3
"""
CampusDB MongoDB part, written with pymongo (pip install pymongo).
Same operations as campusdb_mongo.js: load, indexes, CRUD, two aggregation pipelines.

Run:  python3 mongo/campusdb_mongo.py            (MONGO_URI defaults to localhost)
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from pymongo import ASCENDING, DESCENDING, MongoClient

ROOT = Path(__file__).resolve().parent.parent
client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"))
db = client["campusdb"]


def load_jsonl(path, convert_dates=False):
    docs = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            if convert_dates and isinstance(d.get("event_ts"), dict):
                d["event_ts"] = datetime.strptime(d["event_ts"]["$date"], "%Y-%m-%dT%H:%M:%SZ") \
                                        .replace(tzinfo=timezone.utc)
            docs.append(d)
    return docs


# ---- load (idempotent) ------------------------------------------------
db.student_activity.drop()
db.results.drop()
db.student_activity.insert_many(load_jsonl(ROOT / "mongo" / "activity_logs.jsonl", True))
db.results.insert_many(load_jsonl(ROOT / "mongo" / "results_snapshot.jsonl"))
print("activity events:", db.student_activity.count_documents({}),
      "| results:", db.results.count_documents({}))

# ---- indexes ----------------------------------------------------------
db.student_activity.create_index([("student_id", ASCENDING), ("event_ts", DESCENDING)], name="idx_student_date")
db.student_activity.create_index([("event_ts", ASCENDING)], name="idx_date")
db.student_activity.create_index([("course_id", ASCENDING), ("academic_year", ASCENDING),
                                  ("event_ts", ASCENDING)], name="idx_course_year_date")
db.results.create_index([("student_id", ASCENDING), ("course_id", ASCENDING),
                         ("academic_year", ASCENDING)], unique=True, name="uq_result_key")
print("indexes:", [i["name"] for i in db.student_activity.list_indexes()])

# ---- CRUD -------------------------------------------------------------
now = datetime(2025, 11, 18, 9, 30, tzinfo=timezone.utc)
db.student_activity.insert_one({"student_id": 270, "course_id": 26, "course_code": "MST120",
                                "academic_year": 2025, "event_type": "login", "event_ts": now,
                                "details": {"device": "web", "session_minutes": 42}})                    # create
latest = list(db.student_activity.find({"student_id": 270}).sort("event_ts", -1).limit(5))                 # read
db.student_activity.update_many({"course_code": "MST120", "academic_year": 2025,
                                 "event_type": "assignment_submission"},
                                {"$set": {"reviewed": True}})                                            # update
db.student_activity.delete_one({"student_id": 270, "event_ts": now})                                      # delete
print("latest event for student 270:", latest[0]["event_type"], latest[0]["event_ts"])

# ---- pipeline 1: weekly activity per course ---------------------------
weekly = list(db.student_activity.aggregate([
    {"$match": {"academic_year": 2025}},
    {"$group": {"_id": {"course_code": "$course_code",
                        "week": {"$dateTrunc": {"date": "$event_ts", "unit": "week", "startOfWeek": "monday"}}},
                "logins": {"$sum": {"$cond": [{"$eq": ["$event_type", "login"]}, 1, 0]}},
                "submissions": {"$sum": {"$cond": [{"$eq": ["$event_type", "assignment_submission"]}, 1, 0]}},
                "active_students": {"$addToSet": "$student_id"}}},
    {"$project": {"_id": 0, "course_code": "$_id.course_code", "week": "$_id.week",
                  "logins": 1, "submissions": 1, "active_students": {"$size": "$active_students"}}},
    {"$sort": {"course_code": 1, "week": 1}},
]))
print("weekly rows:", len(weekly), weekly[0])

# ---- pipeline 2: engagement vs results --------------------------------
linked = list(db.student_activity.aggregate([
    {"$match": {"academic_year": 2025}},
    {"$group": {"_id": {"student_id": "$student_id", "course_id": "$course_id",
                        "academic_year": "$academic_year"}, "events": {"$sum": 1}}},
    {"$lookup": {"from": "results",
                 "let": {"s": "$_id.student_id", "c": "$_id.course_id", "y": "$_id.academic_year"},
                 "pipeline": [{"$match": {"$expr": {"$and": [
                     {"$eq": ["$student_id", "$$s"]}, {"$eq": ["$course_id", "$$c"]},
                     {"$eq": ["$academic_year", "$$y"]}]}}}],
                 "as": "result"}},
    {"$unwind": "$result"},
    {"$addFields": {"engagement": {"$switch": {"branches": [
        {"case": {"$lt": ["$events", 6]}, "then": "1 Low (<6 events)"},
        {"case": {"$lt": ["$events", 12]}, "then": "2 Medium (6-11 events)"}],
        "default": "3 High (12+ events)"}}}},
    {"$group": {"_id": "$engagement", "enrolments": {"$sum": 1},
                "avg_mark_pct": {"$avg": "$result.percentage"},
                "pass_rate_pct": {"$avg": {"$cond": ["$result.passed", 100, 0]}}}},
    {"$project": {"_id": 0, "engagement": "$_id", "enrolments": 1,
                  "avg_mark_pct": {"$round": ["$avg_mark_pct", 1]},
                  "pass_rate_pct": {"$round": ["$pass_rate_pct", 1]}}},
    {"$sort": {"engagement": 1}},
]))
for row in linked:
    print(row)
