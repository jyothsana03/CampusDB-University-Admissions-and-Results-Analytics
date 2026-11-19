"""Fills the DBMS project presentation template with CampusDB content.

    python3 python/build_deck.py [template.pptx] [output.pptx]

Edits the template's own shapes (text runs keep their formatting), fills every template table,
and swaps each "Insert screenshot" box for a real picture from outputs/.
"""
import copy, json, sys
from pathlib import Path
from lxml import etree
from pptx import Presentation
from pptx.util import Emu, Inches, Pt

ROOT = Path(__file__).resolve().parent.parent
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "template" / "template.pptx"
DST = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "CampusDB_DBMS_Project_Presentation.pptx"
OUT = ROOT / "outputs"
M = json.loads((OUT / "metrics.json").read_text())
NS = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
A = "{%s}" % NS["a"]

prs = Presentation(str(SRC))
S = list(prs.slides)


# ------------------------------------------------------------------ helpers
def shape(slide, name, nth=0):
    hits = [s for s in slide.shapes if s.name == name]
    return hits[nth]


def drop(sh):
    sh._element.getparent().remove(sh._element)


def set_runs(p, texts):
    runs = p.runs
    assert len(runs) >= len(texts), (len(runs), texts)
    for r, t in zip(runs, texts):
        r.text = t
    for r in runs[len(texts):]:
        p._p.remove(r._r)


def set_paras(sh, paras, rebuild_from_first=False):
    """paras: list of lists of run texts. Paragraph/run formatting is cloned from the template."""
    tf = sh.text_frame
    ps = tf.paragraphs
    base = copy.deepcopy(ps[0]._p) if rebuild_from_first else None
    while len(ps) < len(paras):
        ps[-1]._p.addnext(copy.deepcopy(ps[-1]._p))
        ps = tf.paragraphs
    while len(ps) > len(paras):
        ps[-1]._p.getparent().remove(ps[-1]._p)
        ps = tf.paragraphs
    if rebuild_from_first:
        for p in ps[1:]:
            p._p.getparent().replace(p._p, copy.deepcopy(base))
        ps = tf.paragraphs
    for p, texts in zip(ps, paras):
        set_runs(p, texts)


def set_cell(cell, text, size=1100, bold=False):
    p = cell.text_frame.paragraphs[0]._p
    for r in p.findall(A + "r"):
        p.remove(r)
    r = etree.SubElement(p, A + "r")
    rpr = etree.SubElement(r, A + "rPr", lang="en-US", sz=str(size), dirty="0")
    if bold:
        rpr.set("b", "1")
    fill = etree.SubElement(rpr, A + "solidFill")
    etree.SubElement(fill, A + "schemeClr", val="tx1")
    etree.SubElement(r, A + "t").text = text
    end = p.find(A + "endParaRPr")
    if end is not None:            # a:r must come before a:endParaRPr
        p.remove(end)
        p.append(end)


def fill_table(sh, rows, size=1100, row_h=None):
    """rows: body rows (list of lists). Adds rows by cloning the last one, removes surplus rows."""
    tbl = sh.table
    trs = tbl._tbl.tr_lst
    while len(tbl._tbl.tr_lst) < len(rows) + 1:
        tbl._tbl.append(copy.deepcopy(tbl._tbl.tr_lst[-1]))
    while len(tbl._tbl.tr_lst) > len(rows) + 1:
        tbl._tbl.remove(tbl._tbl.tr_lst[-1])
    for r_i, row in enumerate(rows, start=1):
        for c_i, text in enumerate(row):
            set_cell(tbl.cell(r_i, c_i), text, size)
    if row_h:
        for tr in tbl._tbl.tr_lst:
            tr.set("h", str(int(row_h)))
    sh.height = Emu(sum(int(tr.get("h")) for tr in tbl._tbl.tr_lst))


def picture(slide, path, box, name, alt, fit="width"):
    x, y, w, h = box
    from PIL import Image
    iw, ih = Image.open(path).size
    if fit == "width":
        pw, ph = w, w * ih / iw
    else:
        pw, ph = h * iw / ih, h
    pic = slide.shapes.add_picture(str(path), Inches(x + (w - pw) / 2), Inches(y), Inches(pw), Inches(ph))
    pic.name = name
    pic._element.nvPicPr.cNvPr.set("descr", alt)
    return pic


def clone_box(slide, src, x, y, w, h):
    el = copy.deepcopy(src._element)
    slide.shapes._spTree.append(el)
    new = slide.shapes[-1]
    new.left, new.top, new.width, new.height = Inches(x), Inches(y), Inches(w), Inches(h)
    ids = [int(i) for i in slide.shapes._spTree.xpath("//p:cNvPr/@id")]
    el.xpath(".//p:cNvPr")[0].set("id", str(max(ids) + 1))
    return new


def notes(slide, text):
    slide.notes_slide.notes_text_frame.text = text


# ================================================================== slide 1: title
s = S[0]
title = shape(s, "Project title")
set_paras(title, [["CampusDB: University Admissions and Results Analytics"]])
title.text_frame.paragraphs[0].runs[0].font.size = Pt(28)      # two lines at 28pt need a taller box
title.top, title.height = Inches(0.95), Inches(0.95)
set_paras(shape(s, "Text 6"), [["Problem statement no. 01   ·   Domain: Education"]])
t = shape(s, "Table 0")
tbl = t.table
set_cell(tbl.cell(1, 1), "[Your name]", 1200)
set_cell(tbl.cell(1, 2), "[Reg. no.]", 1200)
set_cell(tbl.cell(1, 3), "All parts (individual)", 1200)
for tr in tbl._tbl.tr_lst[2:]:
    tbl._tbl.remove(tr)
t.height = Emu(sum(int(tr.get("h")) for tr in tbl._tbl.tr_lst))
drop(shape(s, "Text 7"))                                         # template instruction line
set_paras(shape(s, "Text 8"), [["Database: ", "PostgreSQL 16  +  MongoDB"]])
data_box = clone_box(s, shape(s, "Text 8"), 6.10, 3.75, 6.70, 0.65)
data_box.text_frame.word_wrap = True
set_paras(data_box, [["Data: ", f"synthetic, generated with Python (seed 2026): {M['total_rows']:,} rows in "
                      f"{M['tables']} tables, plus 6,995 MongoDB activity documents"]])
data_box.name = "Data source"
notes(s, "CampusDB is a relational database for a university's admissions, enrolment and exam data, with student LMS "
         "activity kept in MongoDB. It supports three decisions: where intake is growing, which courses are hardest, "
         "and which students are at risk. All data is synthetic, generated with a seeded Python script.")

# ================================================================== slide 2: schema
s = S[1]
drop(shape(s, "Screenshot placeholder"))
picture(s, OUT / "er_diagram.png", (0.5, 2.30, 6.6, 2.85), "ER diagram",
        "ER diagram of seven tables: department, programme, course, student, enrolment, exam and result, joined by one-to-many keys")
cap = clone_box(s, shape(s, "Text 7"), 0.5, 5.35, 6.6, 1.2)
cap.name = "ER caption"
set_paras(cap, [["Relationships: ", "department 1:N programme; programme 1:N course and student; student and course 1:N "
                 "enrolment; course 1:N exam; enrolment and exam 1:N result."],
                ["Derived column: ", "student.cgpa is kept on purpose and maintained only by a trigger."],
                ["Keys: ", "PK = primary key, FK = foreign key."]])
fill_table(shape(s, "Table 0"), [
    ["department", "dept_id", "none"],
    ["programme", "programme_id", "dept_id"],
    ["course", "course_id", "programme_id"],
    ["student", "student_id", "programme_id"],
    ["enrolment", "enrolment_id", "student_id, course_id"],
    ["exam", "exam_id", "course_id"],
    ["result", "result_id", "enrolment_id, exam_id"],
], row_h=Inches(0.31))
set_paras(shape(s, "Text 7", 0), [["Key functional dependency: ", "course_id → programme_id"],
                                  ["Highest normal form reached: ", "3NF"],
                                  ["Redundancy removed: ", "programme and department names stored once"]])
notes(s, "Seven tables in third normal form. Every non-key column depends on the key, the whole key and nothing but the "
         "key. Example: a course determines its programme, and the programme determines its name and department, so "
         "programme details live in one table instead of being repeated on every course or student row. "
         "student.cgpa is derived data kept deliberately for fast reporting; a trigger is the only thing that writes it.")

# ================================================================== slide 3: SQL
s = S[2]
set_paras(shape(s, "Code sample"), [
    ["-- one result per student per exam"],
    ["CREATE TABLE result ("],
    ["  result_id      SERIAL PRIMARY KEY,"],
    ["  enrolment_id   INT NOT NULL"],
    ["    REFERENCES enrolment ON DELETE CASCADE,"],
    ["  exam_id        INT NOT NULL REFERENCES exam,"],
    ["  marks_obtained NUMERIC(5,2) NOT NULL"],
    ["    CHECK (marks_obtained >= 0),"],
    ["  UNIQUE (enrolment_id, exam_id)"],
    [");"]], rebuild_from_first=True)
set_paras(shape(s, "Text 5"), [
    ["Trigger: ", "trg_result_cgpa (AFTER insert/update/delete) recomputes CGPA; trg_result_validate (BEFORE) blocks bad marks"],
    ["View: ", "v_course_pass_rate and v_result_detail hide a 6-table join"],
    ["Rows loaded: ", f"{M['total_rows']:,} across {M['tables']} tables"]])
fill_table(shape(s, "Table 0"), [
    ["Admissions per programme per year", "JOIN, GROUP BY, FILTER", f"Intake up 47% ({M['admitted_2021']} to {M['admitted_2025']})"],
    ["Pass % by course, hardest first", "View, GROUP BY, HAVING", f"Lowest: {M['hardest'][0][0]} {M['hardest'][0][1]}%"],
    ["Topper in each programme", "CTE, RANK() OVER", "Best: M.Sc Data Science, CGPA 9.71"],
    ["Students below CGPA 5.0", "JOIN, WHERE, ORDER BY", f"{M['below_5']} of {M['students']} ({M['below_5'] / M['students']:.1%})"],
])
drop(shape(s, "Screenshot placeholder"))
picture(s, OUT / "query_result_toppers.png", (6.5, 4.85, 6.33, 1.70), "Query result",
        "Result of the toppers query: the highest CGPA in each of the six programmes")
notes(s, "The result table shows the DDL with its constraints. Live demo: update one mark and show that trg_result_cgpa "
         "changes the student's CGPA, then try 120 marks and show trg_result_validate reject it. Then run the toppers "
         "query (a window function) and the students-below-5.0 query.")

# ================================================================== slide 4: Python
s = S[3]
set_paras(shape(s, "Code sample"), [
    ["import os, psycopg2"],
    ["import pandas as pd"],
    [""],
    ["conn = psycopg2.connect("],
    ['    dbname="campusdb_py", user="postgres",'],
    ['    password=os.getenv("PGPASSWORD"))'],
    ["cur = conn.cursor()"],
    ["cur.executemany(INSERT, csv_rows)"],
    ["cur.execute(QUERY); rows = cur.fetchall()"],
    ["df = pd.DataFrame(rows, columns=cols)"]], rebuild_from_first=True)
set_paras(shape(s, "Text 5"), [["Used for:  loading CSV files  ·  running queries  ·  pandas and matplotlib charts"]])
drop(shape(s, "Screenshot placeholder", 0))
drop(shape(s, "Screenshot placeholder", 0))
picture(s, OUT / "chart1_admissions_trend.png", (5.40, 1.90, 3.60, 2.60), "Chart 1",
        "Line chart of new students per year for six programmes; BCS and MDS rise fastest", fit="height")
picture(s, OUT / "chart2_pass_rate_by_course.png", (9.23, 1.90, 3.60, 2.60), "Chart 2",
        "Dot chart of the eight courses with the lowest pass percentage; Operating Systems is lowest at 86.7", fit="height")
set_paras(shape(s, "Text 10"), [
    [f"Insight 1:  Intake up 47% since 2021 ({M['admitted_2021']} to {M['admitted_2025']}); M.Sc Data Science {M['mds_2021']} to {M['mds_2025']}."],
    [f"Insight 2:  Overall pass rate {M['overall_pass_pct']}%; hardest is {M['hardest'][0][0]} at {M['hardest'][0][1]}%."],
    [f"Insight 3:  Entrance score predicts CGPA: {M['band_80plus']} (80+) vs {M['band_below60']} (below 60)."]])
notes(s, "Run the notebook: it connects with the Python DB-API, creates the schema, loads the seven CSV files with "
         "executemany (the CGPA trigger fires as results load), runs the queries into pandas and draws the charts. "
         "A third chart in the notebook shows average CGPA by entrance-score band.")

# ================================================================== slide 5: MongoDB
s = S[4]
set_paras(shape(s, "Code sample", 0), [
    ["{"],
    ['  "student_id": 73,'],
    ['  "course_id": 6,'],
    ['  "course_code": "BCS320",'],
    ['  "event_type": "login",'],
    ['  "event_ts": ISODate("2025-08-01"),'],
    ['  "details": {'],
    ['    "device": "lab-pc",'],
    ['    "session_minutes": 27 }'],
    ["}"]], rebuild_from_first=True)
set_paras(shape(s, "Text 5"), [["Indexes created: student_id+date, date, course+year"]])
set_paras(shape(s, "Code sample", 1), [
    ["db.student_activity.aggregate(["],
    ["  { $match: {academic_year: 2025} },"],
    ["  { $group: {_id: {sid, cid},"],
    ["      events: {$sum: 1}} },"],
    ['  { $lookup: {from: "results"} },'],
    ["  { $addFields: {band: ...} },"],
    ['  { $group: {_id: "$band",'],
    ['      avg_mark: {$avg: "$mark"}} }'],
    ["])"]], rebuild_from_first=True)
drop(shape(s, "Screenshot placeholder"))
picture(s, OUT / "pipeline_output.png", (5.10, 4.70, 3.60, 1.60), "Pipeline output",
        "Expected output of the engagement pipeline: pass rate rises from 84.1 percent to 100 percent with more activity", fit="height")
fill_table(shape(s, "Table 0"), [
    ["Schema", "Fixed", "Flexible"],
    ["Relations", "FK and JOIN", "Embed or $lookup"],
    ["Best for", "Marks, CGPA", "Event logs"],
    ["Our choice", "Core records", "LMS activity"],
])
set_paras(shape(s, "Text 12"), [["Why this suits a document model: login and submission events have different fields and arrive in bulk, so each event is one flexible document."]])
notes(s, "Activity events are stored as one document per event: logins carry device and session minutes, submissions carry "
         "assignment number, score and late flag. Indexes: student_id with date, date alone, and course with year. "
         "Show insert, find, update and delete, then the aggregation. The output shown is the expected result, produced "
         "by reproducing the same pipeline in pandas on the same data; run campusdb_mongo.js against a MongoDB server to "
         "see it live.")

# ================================================================== slide 6: findings
s = S[5]
set_paras(shape(s, "Text 4"), [
    [f"Finding 1: Intake grew 47% ({M['admitted_2021']} to {M['admitted_2025']}); Data Science grew fastest."],
    [f"Finding 2: CGPA {M['band_80plus']} for entrance 80+, {M['band_below60']} for below 60."],
    ["Finding 3: Low LMS activity: 84% pass; high activity: 100% (r = 0.62)."]])
set_paras(shape(s, "Text 6"), [
    ["Challenge: CGPA must stay correct after every mark change."],
    ["How we solved it: a trigger recomputes it from results and credits."],
    ["Learning: derive values inside the database, in one place."]])
set_paras(shape(s, "Text 9"), [
    ["Show the schema in PostgreSQL"],
    ["Insert a row that fires the trigger"],
    ["Run two analytical queries"],
    ["Run the Python notebook and charts"],
    ["Run CRUD and an aggregation in MongoDB"]])
set_paras(shape(s, "Text 10"), [["Files submitted: ", "schema.sql · data.sql · queries.sql · campusdb_analysis.ipynb · MongoDB scripts · README"]])
notes(s, "Finish with the live demo, then the three findings: intake is growing (especially Data Science), the entrance "
         "score is a strong predictor of CGPA, and engagement in the LMS goes with better results. Be ready to write or "
         "change a query live.")

prs.save(str(DST))
print("saved", DST)
