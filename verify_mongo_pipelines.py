#!/usr/bin/env python3
"""
Reproduces the two MongoDB aggregation pipelines in pandas on the same data files, so
the expected output of mongo/campusdb_mongo.js can be checked without a MongoDB server.
(Not a substitute for running the pipelines on MongoDB.)  Writes outputs/mongo_expected.txt
and outputs/engagement_vs_results.png.
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
ev = pd.DataFrame(json.loads(l) for l in open(ROOT / "mongo" / "activity_logs.jsonl"))
ev["event_ts"] = pd.to_datetime(ev["event_ts"].map(lambda d: d["$date"]))
res = pd.DataFrame(json.loads(l) for l in open(ROOT / "mongo" / "results_snapshot.jsonl"))
out = []

# ---- pipeline 1: weekly activity per course (AY 2025) -----------------
a = ev[ev.academic_year == 2025].copy()
a["week"] = a.event_ts.dt.tz_localize(None).dt.to_period("W-SUN").dt.start_time   # Monday start
weekly = (a.groupby(["course_code", "week"])
            .agg(logins=("event_type", lambda s: (s == "login").sum()),
                 submissions=("event_type", lambda s: (s == "assignment_submission").sum()),
                 active_students=("student_id", "nunique"))
            .reset_index().sort_values(["course_code", "week"]))
out.append(f"PIPELINE 1  weekly activity per course: {len(weekly)} course-weeks")
out.append(weekly.head(6).to_string(index=False))
by_week = a.groupby("week").size()
out.append(f"\nevents per week across all courses: min {by_week.min()}, max {by_week.max()} "
           f"(peak week starting {by_week.idxmax().date()})")

# ---- pipeline 2: engagement vs results --------------------------------
g = (a.groupby(["student_id", "course_id", "academic_year"]).size().rename("events").reset_index())
m = g.merge(res, on=["student_id", "course_id", "academic_year"])
def band(x):
    return "1 Low (<6 events)" if x < 6 else "2 Medium (6-11 events)" if x < 12 else "3 High (12+ events)"
m["engagement"] = m.events.map(band)
tab = (m.groupby("engagement")
         .agg(enrolments=("passed", "size"), avg_mark_pct=("percentage", "mean"),
              pass_rate_pct=("passed", lambda s: 100 * s.mean()))
         .round(1).reset_index())
corr = m.events.corr(m.percentage)
out.append("\nPIPELINE 2  engagement vs exam results (AY 2025-26)")
out.append(tab.to_string(index=False))
out.append(f"\ncorrelation(events in term, final mark %) = {corr:.2f} over {len(m)} enrolments")

# ---- pipeline 3: late submission rate by programme prefix -------------
s = ev[ev.event_type == "assignment_submission"].copy()
s["late"] = s.details.map(lambda d: d["late"]); s["score"] = s.details.map(lambda d: d["score"])
s["prefix"] = s.course_code.str[:3]
p3 = (s.groupby("prefix").agg(submissions=("late", "size"), late_pct=("late", lambda x: 100 * x.mean()),
                              avg_score=("score", "mean")).round(1).reset_index())
out.append("\nPIPELINE 3  late-submission rate by programme")
out.append(p3.to_string(index=False))
(ROOT / "outputs" / "mongo_expected.txt").write_text("\n".join(out) + "\n")
print("\n".join(out))

# ---- chart --------------------------------------------------------------
SURFACE, INK, INK2, GRID, BLUE = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df", "#2a78d6"
fig, ax = plt.subplots(figsize=(6.4, 3.8), facecolor=SURFACE)
ax.set_facecolor(SURFACE)
labels = ["Low\n(<6 events)", "Medium\n(6-11)", "High\n(12+)"]
bars = ax.bar(labels, tab.pass_rate_pct, color=BLUE, width=0.5, edgecolor=SURFACE)
for b, p, n, mk in zip(bars, tab.pass_rate_pct, tab.enrolments, tab.avg_mark_pct):
    ax.text(b.get_x() + b.get_width() / 2, p + 1, f"{p:.0f}% pass\navg mark {mk:.0f}%  (n={n})",
            ha="center", va="bottom", fontsize=9, color=INK)
ax.set_ylim(0, 125); ax.set_yticks([0, 25, 50, 75, 100]); ax.set_ylabel("Pass rate (%)", color=INK2)
ax.set_title("More LMS activity goes with higher pass rates", loc="left", fontsize=12, fontweight="bold", color=INK)
for sp in ("top", "right"): ax.spines[sp].set_visible(False)
ax.spines["left"].set_color(GRID); ax.spines["bottom"].set_color(GRID)
ax.grid(axis="y", color=GRID); ax.set_axisbelow(True)
ax.tick_params(colors=INK2)
fig.savefig(ROOT / "outputs" / "engagement_vs_results.png", dpi=160, bbox_inches="tight", facecolor=SURFACE)
