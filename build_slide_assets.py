"""Renders the three pictures used in the presentation: ER diagram, query-result image, pipeline-output image.
Needs graphviz `dot` and matplotlib. Reads outputs/toppers_per_programme.csv (written by the notebook)
and mongo/*.jsonl (for the pandas replica of pipeline 2)."""
import json, subprocess
from pathlib import Path
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs"
INK, MUTED, GRID, BLUE, SOFT = "#0b0b0b", "#52514e", "#e4e3df", "#2a78d6", "#eaf1fb"

# ---------------------------------------------------------------- ER diagram (graphviz)
ER = {
    "department": [("PK", "dept_id"), ("", "dept_name")],
    "programme": [("PK", "programme_id"), ("", "programme_code"), ("", "programme_name"), ("FK", "dept_id"), ("", "level, seats")],
    "course": [("PK", "course_id"), ("", "course_code, title"), ("", "credits, semester"), ("FK", "programme_id")],
    "student": [("PK", "student_id"), ("", "reg_no, full_name"), ("FK", "programme_id"), ("", "admission_year"), ("", "entrance_score"), ("", "cgpa (trigger)")],
    "enrolment": [("PK", "enrolment_id"), ("FK", "student_id"), ("FK", "course_id"), ("", "academic_year")],
    "exam": [("PK", "exam_id"), ("FK", "course_id"), ("", "academic_year"), ("", "exam_date, max_marks")],
    "result": [("PK", "result_id"), ("FK", "enrolment_id"), ("FK", "exam_id"), ("", "marks_obtained")],
}
POS = {"department": (0, 2.7), "programme": (3.0, 2.7), "course": (6.0, 2.7), "exam": (9.0, 2.7),
       "student": (3.0, 0), "enrolment": (6.0, 0), "result": (9.0, 0)}
def node(name, cols):
    rows = "".join(
        f'<TR><TD ALIGN="LEFT" WIDTH="26"><FONT COLOR="{"#b3261e" if k == "PK" else "#6250d6"}" POINT-SIZE="10"><B>{k or "&#160;"}</B></FONT></TD>'
        f'<TD ALIGN="LEFT"><FONT POINT-SIZE="13">{c}</FONT></TD></TR>' for k, c in cols)
    return (f'{name} [pos="{POS[name][0]},{POS[name][1]}!", label=<<TABLE BORDER="1" CELLBORDER="0" CELLSPACING="0" CELLPADDING="3" COLOR="#9bb7de" BGCOLOR="white">'
            f'<TR><TD COLSPAN="2" BGCOLOR="#0b5cad"><FONT COLOR="white" POINT-SIZE="14"><B>{name}</B></FONT></TD></TR>{rows}</TABLE>>];')
edges = [("department", "programme"), ("programme", "course"), ("programme", "student"),
         ("student", "enrolment"), ("course", "enrolment"), ("course", "exam"), ("enrolment", "result"), ("exam", "result")]
dot = ['digraph ER {', 'bgcolor="white"; pad=0.1; splines=line;',
       'node [shape=plaintext, fontname="DejaVu Sans"]; edge [color="#52514e", arrowhead=crow, arrowtail=tee, dir=both, penwidth=1.2];']
dot += [node(n, c) for n, c in ER.items()] + [f"{a} -> {b};" for a, b in edges] + ["}"]
(OUT / "er_diagram.dot").write_text("\n".join(dot))
subprocess.run(["neato", "-Tpng", "-Gdpi=300", str(OUT / "er_diagram.dot"), "-o", str(OUT / "er_diagram.png")], check=True)

# ---------------------------------------------------------------- query-result image (psql-style table)
t = pd.read_csv(OUT / "toppers_per_programme.csv")
t.columns = ["programme", "reg_no", "full_name", "cgpa"]
t["cgpa"] = t.cgpa.map(lambda v: f"{v:.2f}")
fig, ax = plt.subplots(figsize=(6.33, 1.7))
ax.axis("off")
ax.text(0, 1.0, "Q5  topper per programme   RANK() OVER (PARTITION BY programme ORDER BY cgpa DESC)", fontsize=8, color=MUTED,
        fontfamily="DejaVu Sans Mono", va="top", transform=ax.transAxes)
tb = ax.table(cellText=t.values, colLabels=list(t.columns), cellLoc="left", colLoc="left", bbox=[0, 0, 1, 0.84])
tb.auto_set_font_size(False); tb.set_fontsize(8.5)
for (r, c), cell in tb.get_celld().items():
    cell.set_edgecolor(GRID); cell.set_linewidth(0.6)
    cell.get_text().set_fontfamily("DejaVu Sans Mono"); cell.PAD = 0.04
    if r == 0:
        cell.set_facecolor("#0b5cad"); cell.get_text().set_color("white"); cell.get_text().set_fontweight("bold")
    else:
        cell.set_facecolor("white" if r % 2 else "#f3f7fc"); cell.get_text().set_color(INK)
fig.savefig(OUT / "query_result_toppers.png", dpi=250, facecolor="white", bbox_inches=None)
plt.close(fig)

# ---------------------------------------------------------------- pipeline-output image (pandas replica of pipeline 2)
ev = pd.DataFrame(json.loads(l) for l in open(ROOT / "mongo" / "activity_logs.jsonl"))
res = pd.DataFrame(json.loads(l) for l in open(ROOT / "mongo" / "results_snapshot.jsonl"))
g = ev[ev.academic_year == 2025].groupby(["student_id", "course_id", "academic_year"]).size().rename("events").reset_index()
m = g.merge(res, on=["student_id", "course_id", "academic_year"])
m["engagement"] = m.events.map(lambda x: "1 Low (<6)" if x < 6 else "2 Medium (6-11)" if x < 12 else "3 High (12+)")
p2 = (m.groupby("engagement").agg(enrolments=("passed", "size"), avg_mark_pct=("percentage", "mean"),
                                   pass_rate_pct=("passed", lambda s: 100 * s.mean())).round(1).reset_index())
fig, ax = plt.subplots(figsize=(3.6, 1.6))
ax.axis("off")
ax.text(0, 1.0, "pipeline 2 output (expected)", fontsize=7.5, color=MUTED, fontfamily="DejaVu Sans Mono", va="top", transform=ax.transAxes)
cols = ["engagement", "n", "avg_mark", "pass_%"]
vals = [[r.engagement, int(r.enrolments), f"{r.avg_mark_pct:.1f}", f"{r.pass_rate_pct:.1f}"] for r in p2.itertuples()]
tb = ax.table(cellText=vals, colLabels=cols, cellLoc="left", colLoc="left", bbox=[0, 0.04, 1, 0.78], colWidths=[0.42, 0.14, 0.22, 0.22])
tb.auto_set_font_size(False); tb.set_fontsize(7.5)
for (r, c), cell in tb.get_celld().items():
    cell.set_edgecolor(GRID); cell.set_linewidth(0.6); cell.get_text().set_fontfamily("DejaVu Sans Mono")
    if r == 0:
        cell.set_facecolor("#0b5cad"); cell.get_text().set_color("white"); cell.get_text().set_fontweight("bold")
    else:
        cell.set_facecolor("white" if r % 2 else "#f3f7fc"); cell.get_text().set_color(INK)
fig.savefig(OUT / "pipeline_output.png", dpi=250, facecolor="white")
plt.close(fig)
print("assets written:", sorted(p.name for p in OUT.glob("*.png")))
