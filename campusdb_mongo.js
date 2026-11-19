// =====================================================================
// CampusDB : MongoDB part  (mongosh, MongoDB 5.0+)
//
// Models student LMS activity (logins, assignment submissions) as documents,
// plus a snapshot of final-exam results exported from PostgreSQL so activity
// can be linked to outcomes.
//
// Setup (from the project folder):
//   mongoimport --db campusdb --collection student_activity --file mongo/activity_logs.jsonl
//   mongoimport --db campusdb --collection results          --file mongo/results_snapshot.jsonl
//   mongosh campusdb mongo/campusdb_mongo.js
//
// activity_logs.jsonl is written by python/gen_data.py and
// results_snapshot.jsonl by python/export_results_for_mongo.py.
// event_ts is stored as extended JSON {"$date": ...} so mongoimport makes a real Date.
// =====================================================================

const db = db.getSiblingDB("campusdb");

// ---------------------------------------------------------------------
// 1. DOCUMENT MODEL
// One document per event. Different event types carry different `details`
// (login: device, session_minutes; submission: assignment_no, score, late),
// which is why a document model fits better than one wide SQL table.
//
// {
//   student_id: 270, course_id: 26, course_code: "MST120", academic_year: 2025,
//   event_type: "login",                       // or "assignment_submission"
//   event_ts: ISODate("2025-08-04T06:19:00Z"),
//   details: { device: "mobile", session_minutes: 31 }
// }
//
// student_id / course_id are the PostgreSQL primary keys (soft references).
// ---------------------------------------------------------------------

// Optional schema validation (collMod works on an imported collection)
db.runCommand({
  collMod: "student_activity",
  validator: { $jsonSchema: {
    bsonType: "object",
    required: ["student_id", "course_id", "academic_year", "event_type", "event_ts"],
    properties: {
      student_id:    { bsonType: "int" },
      course_id:     { bsonType: "int" },
      academic_year: { bsonType: "int" },
      event_type:    { enum: ["login", "assignment_submission"] },
      event_ts:      { bsonType: "date" },
      details:       { bsonType: "object" }
    }
  } },
  validationLevel: "moderate",
  validationAction: "error"
});

// ---------------------------------------------------------------------
// 2. INDEXES  (student id and date, as required, plus one for the pipelines)
// ---------------------------------------------------------------------
db.student_activity.createIndex({ student_id: 1, event_ts: -1 },
                                { name: "idx_student_date" });
db.student_activity.createIndex({ event_ts: 1 },
                                { name: "idx_date" });
db.student_activity.createIndex({ course_id: 1, academic_year: 1, event_ts: 1 },
                                { name: "idx_course_year_date" });
db.results.createIndex({ student_id: 1, course_id: 1, academic_year: 1 },
                       { unique: true, name: "uq_result_key" });

printjson(db.student_activity.getIndexes().map(i => i.name));

// Show that the student/date index is used
printjson(db.student_activity
  .find({ student_id: 270 }).sort({ event_ts: -1 }).limit(5)
  .explain("queryPlanner").queryPlanner.winningPlan);

// ---------------------------------------------------------------------
// 3. CRUD
// ---------------------------------------------------------------------

// CREATE ---------------------------------------------------------------
db.student_activity.insertOne({
  student_id: NumberInt(270), course_id: NumberInt(26), course_code: "MST120",
  academic_year: NumberInt(2025), event_type: "login",
  event_ts: new Date("2025-11-18T09:30:00Z"),
  details: { device: "web", session_minutes: 42 }
});

db.student_activity.insertMany([
  { student_id: NumberInt(270), course_id: NumberInt(26), course_code: "MST120",
    academic_year: NumberInt(2025), event_type: "assignment_submission",
    event_ts: new Date("2025-11-19T14:05:00Z"),
    details: { assignment_no: 4, score: 71.5, late: false } },
  { student_id: NumberInt(270), course_id: NumberInt(25), course_code: "MST110",
    academic_year: NumberInt(2025), event_type: "login",
    event_ts: new Date("2025-11-19T20:10:00Z"),
    details: { device: "mobile", session_minutes: 18 } }
]);

// READ -----------------------------------------------------------------
// one student's latest five events (served by idx_student_date)
db.student_activity.find({ student_id: 270 }).sort({ event_ts: -1 }).limit(5);

// late submissions scoring under 40, newest first
db.student_activity.find(
  { event_type: "assignment_submission", "details.late": true, "details.score": { $lt: 40 } },
  { _id: 0, student_id: 1, course_code: 1, "details.score": 1, event_ts: 1 }
).sort({ event_ts: -1 }).limit(10);

// how many mobile logins in November 2025?
db.student_activity.countDocuments({
  event_type: "login", "details.device": "mobile",
  event_ts: { $gte: ISODate("2025-11-01"), $lt: ISODate("2025-12-01") }
});

// UPDATE ---------------------------------------------------------------
// re-grade one submission
db.student_activity.updateOne(
  { student_id: 270, course_id: 26, event_type: "assignment_submission",
    "details.assignment_no": 4 },
  { $set: { "details.score": 76.0 }, $currentDate: { regraded_at: true } }
);

// flag every submission for a course-year as reviewed
db.student_activity.updateMany(
  { course_code: "MST120", academic_year: 2025, event_type: "assignment_submission" },
  { $set: { reviewed: true } }
);

// DELETE ---------------------------------------------------------------
// remove the test events inserted above
db.student_activity.deleteOne({ student_id: 270, course_code: "MST110",
                                event_ts: new Date("2025-11-19T20:10:00Z") });
db.student_activity.deleteMany({ student_id: 270, event_ts: { $gte: ISODate("2025-11-18") },
                                 "details.session_minutes": 42 });

// ---------------------------------------------------------------------
// 4. AGGREGATION PIPELINE 1 : weekly activity per course (AY 2025-26)
//    Weeks start on Monday. Output one row per course per week.
// ---------------------------------------------------------------------
const weeklyActivity = db.student_activity.aggregate([
  { $match: { academic_year: 2025 } },
  { $group: {
      _id: { course_code: "$course_code",
             week: { $dateTrunc: { date: "$event_ts", unit: "week", startOfWeek: "monday" } } },
      logins:      { $sum: { $cond: [{ $eq: ["$event_type", "login"] }, 1, 0] } },
      submissions: { $sum: { $cond: [{ $eq: ["$event_type", "assignment_submission"] }, 1, 0] } },
      active_students: { $addToSet: "$student_id" },
      avg_session_min: { $avg: "$details.session_minutes" } } },
  { $project: { _id: 0, course_code: "$_id.course_code", week: "$_id.week",
                logins: 1, submissions: 1,
                active_students: { $size: "$active_students" },
                avg_session_min: { $round: ["$avg_session_min", 1] } } },
  { $sort: { course_code: 1, week: 1 } }
]);
// busiest ten course-weeks
db.student_activity.aggregate([
  { $match: { academic_year: 2025 } },
  { $group: { _id: { course_code: "$course_code",
                     week: { $dateTrunc: { date: "$event_ts", unit: "week", startOfWeek: "monday" } } },
              events: { $sum: 1 } } },
  { $sort: { events: -1 } }, { $limit: 10 }
]).forEach(printjson);

// ---------------------------------------------------------------------
// 5. AGGREGATION PIPELINE 2 : link activity to exam results
//    Per student per course: number of events in the term, joined to the
//    result snapshot with $lookup, then bucketed by engagement.
//    Result: pass rate and mean mark for low / medium / high engagement.
// ---------------------------------------------------------------------
const activityVsResults = db.student_activity.aggregate([
  { $match: { academic_year: 2025 } },
  { $group: { _id: { student_id: "$student_id", course_id: "$course_id",
                     academic_year: "$academic_year" },
              events: { $sum: 1 } } },
  { $lookup: { from: "results",
               let: { s: "$_id.student_id", c: "$_id.course_id", y: "$_id.academic_year" },
               pipeline: [{ $match: { $expr: { $and: [
                 { $eq: ["$student_id", "$$s"] }, { $eq: ["$course_id", "$$c"] },
                 { $eq: ["$academic_year", "$$y"] } ] } } }],
               as: "result" } },
  { $unwind: "$result" },
  { $addFields: { engagement: { $switch: { branches: [
      { case: { $lt: ["$events", 6] },  then: "1 Low (<6 events)" },
      { case: { $lt: ["$events", 12] }, then: "2 Medium (6-11 events)" } ],
      default: "3 High (12+ events)" } } } },
  { $group: { _id: "$engagement",
              enrolments: { $sum: 1 },
              avg_events: { $avg: "$events" },
              avg_mark_pct: { $avg: "$result.percentage" },
              pass_rate_pct: { $avg: { $cond: ["$result.passed", 100, 0] } } } },
  { $project: { _id: 0, engagement: "$_id", enrolments: 1,
                avg_events: { $round: ["$avg_events", 1] },
                avg_mark_pct: { $round: ["$avg_mark_pct", 1] },
                pass_rate_pct: { $round: ["$pass_rate_pct", 1] } } },
  { $sort: { engagement: 1 } }
]);
activityVsResults.forEach(printjson);

// ---------------------------------------------------------------------
// 6. (Optional) PIPELINE 3 : late-submission rate by programme (first 3 letters of course_code)
// ---------------------------------------------------------------------
db.student_activity.aggregate([
  { $match: { event_type: "assignment_submission" } },
  { $group: { _id: { $substrCP: ["$course_code", 0, 3] },
              submissions: { $sum: 1 },
              late_pct: { $avg: { $cond: ["$details.late", 100, 0] } },
              avg_score: { $avg: "$details.score" } } },
  { $project: { _id: 0, programme: "$_id", submissions: 1,
                late_pct: { $round: ["$late_pct", 1] }, avg_score: { $round: ["$avg_score", 1] } } },
  { $sort: { programme: 1 } }
]).forEach(printjson);
