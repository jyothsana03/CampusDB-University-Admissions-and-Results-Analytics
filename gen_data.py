"""Generate the synthetic CampusDB dataset (seeded, reproducible).

Outputs
  data/*.csv                 one CSV per table (loaded by the notebook through DB-API)
  sql/data.sql               INSERT script (loaded with psql)
  mongo/activity_logs.jsonl  student activity documents (mongoimport, one JSON per line)
  (mongo/results_snapshot.jsonl is exported from PostgreSQL by export_results_for_mongo.py)
"""
import csv, json, math, random, datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
random.seed(2026)

DEPTS = ["Computer Science", "Mathematics and Statistics", "Management Studies", "Life Sciences"]
# code, name, dept index, level, seats, admissions 2021..2025 (headcount sampled here)
PROGS = [
    ("BCS", "B.Sc Computer Science", 0, "UG", 60, [15, 17, 20, 23, 27]),
    ("MDS", "M.Sc Data Science", 0, "PG", 50, [9, 11, 14, 18, 22]),
    ("BMA", "B.Sc Mathematics", 1, "UG", 40, [12, 11, 10, 10, 9]),
    ("MST", "M.Sc Statistics", 1, "PG", 30, [8, 8, 9, 10, 11]),
    ("MBA", "MBA Analytics", 2, "PG", 50, [14, 15, 16, 18, 19]),
    ("BBT", "B.Sc Biotechnology", 3, "UG", 40, [10, 10, 11, 12, 12]),
]
COURSES = {  # 8 per programme: 2 per semester, (title, credits)
    "BCS": [("Programming in Python", 4), ("Discrete Mathematics", 3), ("Data Structures", 4), ("Digital Logic", 3),
            ("Database Systems", 4), ("Operating Systems", 3), ("Computer Networks", 3), ("Software Engineering", 3)],
    "MDS": [("Statistics for Data Science", 4), ("Python for Analytics", 4), ("Linear Algebra", 3), ("Probability Theory", 3),
            ("DBMS for Analytics", 4), ("Machine Learning", 4), ("Big Data Systems", 3), ("Data Visualisation", 3)],
    "BMA": [("Calculus I", 4), ("Algebra I", 4), ("Calculus II", 4), ("Real Analysis I", 4),
            ("Differential Equations", 3), ("Linear Algebra", 3), ("Numerical Methods", 3), ("Abstract Algebra", 4)],
    "MST": [("Probability Distributions", 4), ("Statistical Inference", 4), ("Regression Analysis", 4), ("Sampling Theory", 3),
            ("Multivariate Analysis", 4), ("Time Series", 3), ("Bayesian Methods", 3), ("Design of Experiments", 3)],
    "MBA": [("Managerial Economics", 3), ("Financial Accounting", 3), ("Marketing Analytics", 3), ("Operations Management", 3),
            ("Business Statistics", 4), ("Corporate Finance", 3), ("People Analytics", 3), ("Strategy", 3)],
    "BBT": [("Cell Biology", 4), ("Biochemistry", 4), ("Genetics", 4), ("Microbiology", 3),
            ("Molecular Biology", 4), ("Bioinformatics", 3), ("Immunology", 3), ("Bioprocess Engineering", 3)],
}
HARD = {"Discrete Mathematics", "Real Analysis I", "Probability Theory", "Abstract Algebra", "Bayesian Methods",
        "Operating Systems", "Machine Learning", "Biochemistry", "Statistical Inference"}
EASY = {"Data Visualisation", "Strategy", "People Analytics", "Software Engineering", "Programming in Python"}
FIRST = ["Aarav", "Aditi", "Akash", "Ananya", "Arjun", "Bhavna", "Chaitra", "Deepak", "Divya", "Farhan", "Gayathri",
         "Harish", "Ishita", "Jayesh", "Kavya", "Karthik", "Lakshmi", "Manoj", "Meera", "Nikhil", "Nisha", "Pooja",
         "Pranav", "Priya", "Rahul", "Riya", "Rohan", "Sahana", "Sanjay", "Sneha", "Suresh", "Tanvi", "Uday", "Varun",
         "Vidya", "Yash", "Zoya", "Imran", "Fathima", "Joseph", "Mary", "Naveen", "Swathi", "Tarun", "Anjali"]
LAST = ["Iyer", "Nair", "Reddy", "Sharma", "Patel", "Khan", "Das", "Menon", "Gupta", "Rao", "Kulkarni", "Joshi",
        "Pillai", "Banerjee", "Singh", "Verma", "Shetty", "Naidu", "Mishra", "Fernandes", "George", "Bhat"]
LAST_YEAR = 2025


def q(v):
    if v is None:
        return "NULL"
    if isinstance(v, (int, float)):
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"


def term_dates(sem, ay):
    """odd semester: Aug-Nov of ay, exam in Dec; even: Jan-Apr of ay+1, exam in May."""
    if sem % 2 == 1:
        return dt.date(ay, 8, 1), dt.date(ay, 11, 30), dt.date(ay, 12, 10)
    return dt.date(ay + 1, 1, 15), dt.date(ay + 1, 4, 30), dt.date(ay + 1, 5, 10)


# ---------- reference tables ----------
department = [(i + 1, n) for i, n in enumerate(DEPTS)]
programme = [(i + 1, c, n, d + 1, lv, seats) for i, (c, n, d, lv, seats, _) in enumerate(PROGS)]
course, course_by_prog = [], {}
cid = 0
for pi, (code, *_rest) in enumerate(PROGS):
    for k, (title, cr) in enumerate(COURSES[code]):
        cid += 1
        sem = k // 2 + 1
        course.append((cid, f"{code}{sem}{k % 2 + 1}0", title, cr, sem, pi + 1))
        course_by_prog.setdefault(pi + 1, []).append(course[-1])

# ---------- students ----------
student, ability = [], {}
sid = 0
for pi, (code, name, d, lv, seats, counts) in enumerate(PROGS):
    for yi, n in enumerate(counts):
        year = 2021 + yi
        for seq in range(1, n + 1):
            sid += 1
            a = random.gauss(0, 1)
            ability[sid] = a
            entrance = round(min(99.5, max(35, 68 + 9 * a + random.gauss(0, 4))), 2)
            fn, ln = random.choice(FIRST), random.choice(LAST)
            gender = random.choices(["F", "M", "O"], [0.49, 0.50, 0.01])[0]
            birth = dt.date(year - (18 if lv == "UG" else 21) - random.randint(0, 2), random.randint(1, 12), random.randint(1, 28))
            reg = f"{str(year)[2:]}{code}{seq:03d}"
            student.append((sid, reg, f"{fn} {ln}", gender, birth.isoformat(), f"{reg.lower()}@campus.example.edu", pi + 1, year, entrance))

# ---------- enrolments, exams, results ----------
enrolment, exam, result = [], [], []
exam_key, enrol_info = {}, {}
eid = xid = rid = 0
for s in student:
    sid_, _reg, _n, _g, _b, _e, prog, year, _ent = s
    a = ability[sid_]
    for c in course_by_prog[prog]:
        cid_, ccode, title, cr, sem, _p = c
        ay = year + (sem - 1) // 2
        if ay > LAST_YEAR:
            continue
        eid += 1
        enrolment.append((eid, sid_, cid_, ay))
        key = (cid_, ay)
        if key not in exam_key:
            xid += 1
            _s, _e2, exam_date = term_dates(sem, ay)
            exam.append((xid, cid_, ay, "Final", exam_date.isoformat(), 100))
            exam_key[key] = xid
        diff = -7 if title in HARD else (5 if title in EASY else 0)
        marks = round(min(100, max(8, 64 + 12 * a + diff + random.gauss(0, 9))), 2)
        rid += 1
        result.append((rid, eid, exam_key[key], marks))
        enrol_info[eid] = (sid_, ccode, ay, sem, a, marks)

# ---------- write CSVs ----------
def write_csv(name, header, rows):
    p = ROOT / "data" / f"{name}.csv"
    with open(p, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)

write_csv("department", ["dept_id", "dept_name"], department)
write_csv("programme", ["programme_id", "programme_code", "programme_name", "dept_id", "level", "seats"], programme)
write_csv("course", ["course_id", "course_code", "title", "credits", "semester", "programme_id"], course)
write_csv("student", ["student_id", "reg_no", "full_name", "gender", "birth_date", "email", "programme_id", "admission_year", "entrance_score"], student)
write_csv("enrolment", ["enrolment_id", "student_id", "course_id", "academic_year"], enrolment)
write_csv("exam", ["exam_id", "course_id", "academic_year", "exam_type", "exam_date", "max_marks"], exam)
write_csv("result", ["result_id", "enrolment_id", "exam_id", "marks_obtained"], result)

# ---------- data.sql ----------
tables = [
    ("department", ["dept_id", "dept_name"], department),
    ("programme", ["programme_id", "programme_code", "programme_name", "dept_id", "level", "seats"], programme),
    ("course", ["course_id", "course_code", "title", "credits", "semester", "programme_id"], course),
    ("student", ["student_id", "reg_no", "full_name", "gender", "birth_date", "email", "programme_id", "admission_year", "entrance_score"], student),
    ("enrolment", ["enrolment_id", "student_id", "course_id", "academic_year"], enrolment),
    ("exam", ["exam_id", "course_id", "academic_year", "exam_type", "exam_date", "max_marks"], exam),
    ("result", ["result_id", "enrolment_id", "exam_id", "marks_obtained"], result),
]
pk = {"department": "dept_id", "programme": "programme_id", "course": "course_id", "student": "student_id",
      "enrolment": "enrolment_id", "exam": "exam_id", "result": "result_id"}
out = ["-- CampusDB sample data (PostgreSQL). Synthetic, generated by python/gen_data.py (seed 2026).",
       "-- Insert order follows foreign-key dependencies. student.cgpa is filled by trigger trg_result_cgpa",
       "-- as result rows are inserted, so it is deliberately not listed here.",
       "BEGIN;", ""]
for name, cols, rows in tables:
    out.append(f"-- {name}: {len(rows)} rows")
    for i in range(0, len(rows), 100):
        chunk = rows[i:i + 100]
        vals = ",\n  ".join("(" + ", ".join(q(v) for v in r) + ")" for r in chunk)
        out.append(f"INSERT INTO {name} ({', '.join(cols)}) VALUES\n  {vals};")
    out.append("")
out.append("-- keep SERIAL sequences in step with the explicit ids loaded above")
for name, _c, _r in tables:
    out.append(f"SELECT setval(pg_get_serial_sequence('{name}', '{pk[name]}'), (SELECT MAX({pk[name]}) FROM {name}));")
out += ["", "COMMIT;", ""]
(ROOT / "sql" / "data.sql").write_text("\n".join(out))

# ---------- MongoDB documents (LMS activity for the latest academic year only) ----------
# One document per event; login and submission events carry different `details`.
# Results for the $lookup are exported from PostgreSQL by python/export_results_for_mongo.py.
course_id_of = {c[1]: c[0] for c in course}
docs = []
def sig(x):
    return 1 / (1 + math.exp(-x))
def iso(ts):
    return {"$date": ts.strftime("%Y-%m-%dT%H:%M:%SZ")}
for e_id, (s_id, ccode, ay, sem, a, marks) in enrol_info.items():
    if ay != LAST_YEAR:
        continue
    t0, t1, _ex = term_dates(sem, ay)
    span = (t1 - t0).days
    base = {"student_id": s_id, "course_id": course_id_of[ccode], "course_code": ccode, "academic_year": ay}
    for _ in range(max(0, int(random.gauss(7 + 4.0 * a, 2.5)))):
        ts = dt.datetime.combine(t0 + dt.timedelta(days=random.randint(0, span)), dt.time(random.randint(7, 23), random.randint(0, 59)))
        docs.append({**base, "event_type": "login", "event_ts": iso(ts),
                     "details": {"device": random.choice(["mobile", "laptop", "laptop", "lab-pc"]),
                                 "session_minutes": random.randint(3, 95)}})
    for n in range(1, 5):
        if random.random() < sig(1.1 + 1.1 * a):
            due = t0 + dt.timedelta(days=int(span * n / 4.4))
            late = random.random() < sig(-1.2 - 0.8 * a)
            ts = dt.datetime.combine(due + dt.timedelta(days=random.randint(1, 4) if late else -random.randint(0, 6)),
                                     dt.time(random.randint(8, 23), random.randint(0, 59)))
            score = round(min(100, max(0, marks + random.gauss(0, 8) - (6 if late else 0))), 1)
            docs.append({**base, "event_type": "assignment_submission", "event_ts": iso(ts),
                         "details": {"assignment_no": n, "score": score, "late": late}})
docs.sort(key=lambda d: (d["event_ts"]["$date"], d["student_id"]))
with open(ROOT / "mongo" / "activity_logs.jsonl", "w") as f:
    for d in docs:
        f.write(json.dumps(d, separators=(",", ":")) + "\n")

total = sum(len(r) for _n, _c, r in tables)
print({n: len(r) for n, _c, r in tables}, "TOTAL SQL ROWS", total)
print("mongo activity docs", len(docs))
