#!/usr/bin/env python3
"""
Export final-exam results from PostgreSQL to mongo/results_snapshot.jsonl so the
MongoDB aggregation can link LMS activity to exam outcomes ($lookup).

Uses the Python DB-API (psycopg2). Connection settings come from the usual PG* environment
variables. Where psycopg2 is not installed (the build sandbox) the psql-backed DB-API wrapper is used.
Run:  python3 python/export_results_for_mongo.py
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
try:
    import psycopg2
    conn = psycopg2.connect(host=os.getenv("PGHOST", "localhost"), port=int(os.getenv("PGPORT", "5432")),
                            dbname=os.getenv("PGDATABASE", "campusdb"), user=os.getenv("PGUSER", "postgres"),
                            password=os.getenv("PGPASSWORD", ""))
except ImportError:
    sys.path.insert(0, str(ROOT / "python"))
    from psql_dbapi_shim import connect
    conn = connect(dbname=os.getenv("PGDATABASE", "campusdb"))

cur = conn.cursor()
cur.execute("""
    SELECT student_id, course_id, course_code, academic_year,
           marks_obtained, percentage, grade_points, passed
    FROM   v_result_detail
    ORDER BY student_id, course_id, academic_year
""")
columns = [d[0] for d in cur.description]
CASTS = {"student_id": int, "course_id": int, "academic_year": int, "grade_points": int,
         "marks_obtained": float, "percentage": float,
         "passed": lambda v: v in (True, "t", "true", "True")}
n = 0
with open(ROOT / "mongo" / "results_snapshot.jsonl", "w", encoding="utf-8") as f:
    for row in cur.fetchall():
        doc = {c: CASTS[c](v) if c in CASTS else v for c, v in zip(columns, row)}
        doc["grade_point"] = doc.pop("grade_points")
        f.write(json.dumps(doc, separators=(",", ":")) + "\n")
        n += 1
conn.close()
print(f"wrote {n} documents to mongo/results_snapshot.jsonl")
