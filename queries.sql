-- =====================================================================
-- CampusDB analytical queries (PostgreSQL).  psql -d campusdb -f queries.sql
-- =====================================================================

-- Q1. Admissions trend: new students per programme per year (JOIN, GROUP BY, conditional aggregation)
SELECT p.programme_code,
       COUNT(*) FILTER (WHERE s.admission_year = 2021) AS y2021,
       COUNT(*) FILTER (WHERE s.admission_year = 2022) AS y2022,
       COUNT(*) FILTER (WHERE s.admission_year = 2023) AS y2023,
       COUNT(*) FILTER (WHERE s.admission_year = 2024) AS y2024,
       COUNT(*) FILTER (WHERE s.admission_year = 2025) AS y2025,
       COUNT(*)                                         AS total
FROM student s
JOIN programme p ON p.programme_id = s.programme_id
GROUP BY p.programme_code
ORDER BY total DESC;

-- Q2. Seat fill rate by programme and year (JOIN, GROUP BY, arithmetic)
SELECT p.programme_code, s.admission_year, COUNT(*) AS admitted, p.seats,
       ROUND(100.0 * COUNT(*) / p.seats, 1) AS seat_fill_pct
FROM student s
JOIN programme p ON p.programme_id = s.programme_id
GROUP BY p.programme_code, p.seats, s.admission_year
ORDER BY p.programme_code, s.admission_year;

-- Q3. Pass percentage by course, hardest first (view + JOIN-free reuse)
SELECT programme_code, course_code, course_title, appeared, passed, pass_pct, avg_pct
FROM v_course_pass_rate
ORDER BY pass_pct, course_code
LIMIT 10;

-- Q4. Courses that fall below the programme-wide pass rate (HAVING + scalar subquery)
SELECT course_code, course_title,
       ROUND(100.0 * COUNT(*) FILTER (WHERE passed) / COUNT(*), 1) AS pass_pct
FROM v_result_detail
GROUP BY course_code, course_title
HAVING 100.0 * COUNT(*) FILTER (WHERE passed) / COUNT(*) <
       (SELECT 100.0 * COUNT(*) FILTER (WHERE passed) / COUNT(*) FROM v_result_detail)
ORDER BY pass_pct;

-- Q5. Toppers per programme: top 3 CGPA in each programme (window function RANK in a CTE)
WITH ranked AS (
    SELECT p.programme_code, s.reg_no, s.full_name, s.admission_year, s.cgpa,
           RANK() OVER (PARTITION BY s.programme_id ORDER BY s.cgpa DESC) AS rnk
    FROM student s
    JOIN programme p ON p.programme_id = s.programme_id
)
SELECT programme_code, rnk, reg_no, full_name, cgpa
FROM ranked
WHERE rnk <= 3
ORDER BY programme_code, rnk, reg_no;

-- Q6. Students below the CGPA cut-off of 5.0 (JOIN, filter, ORDER BY)
SELECT s.reg_no, s.full_name, p.programme_code, s.admission_year, s.entrance_score, s.cgpa
FROM student s
JOIN programme p ON p.programme_id = s.programme_id
WHERE s.cgpa < 5.0
ORDER BY s.cgpa, s.reg_no;

-- Q7. Cut-off breakdown: how many students per programme are at risk (GROUP BY + HAVING)
SELECT p.programme_code,
       COUNT(*)                                  AS students,
       COUNT(*) FILTER (WHERE s.cgpa < 5.0)      AS below_cutoff,
       ROUND(100.0 * COUNT(*) FILTER (WHERE s.cgpa < 5.0) / COUNT(*), 1) AS at_risk_pct,
       ROUND(AVG(s.cgpa), 2)                     AS avg_cgpa
FROM student s
JOIN programme p ON p.programme_id = s.programme_id
GROUP BY p.programme_code
HAVING COUNT(*) FILTER (WHERE s.cgpa < 5.0) > 0
ORDER BY at_risk_pct DESC;

-- Q8. Does the entrance score predict CGPA? Average CGPA by entrance-score band (CASE + GROUP BY)
SELECT CASE WHEN entrance_score >= 80 THEN '80+'
            WHEN entrance_score >= 70 THEN '70-79'
            WHEN entrance_score >= 60 THEN '60-69'
            ELSE 'below 60' END      AS entrance_band,
       COUNT(*)                      AS students,
       ROUND(AVG(cgpa), 2)           AS avg_cgpa
FROM student
GROUP BY 1
ORDER BY MIN(entrance_score) DESC;

-- Q9. Students who beat their own programme's average CGPA (correlated subquery)
SELECT s.reg_no, s.full_name, s.cgpa
FROM student s
WHERE s.cgpa > (SELECT AVG(s2.cgpa) FROM student s2 WHERE s2.programme_id = s.programme_id)
  AND s.admission_year = 2023
ORDER BY s.cgpa DESC
LIMIT 10;

-- Q10. Year-on-year pass rate per programme (LAG window over an aggregate)
WITH yearly AS (
    SELECT programme_code, academic_year,
           ROUND(100.0 * COUNT(*) FILTER (WHERE passed) / COUNT(*), 1) AS pass_pct
    FROM v_result_detail
    GROUP BY programme_code, academic_year
)
SELECT programme_code, academic_year, pass_pct,
       ROUND(pass_pct - LAG(pass_pct) OVER (PARTITION BY programme_code ORDER BY academic_year), 1) AS change_vs_prev
FROM yearly
ORDER BY programme_code, academic_year;

-- Q11. Courses nobody failed (NOT EXISTS anti-join)
SELECT c.course_code, c.title
FROM course c
WHERE EXISTS (SELECT 1 FROM enrolment en WHERE en.course_id = c.course_id)
  AND NOT EXISTS (SELECT 1 FROM v_result_detail v WHERE v.course_id = c.course_id AND NOT v.passed)
ORDER BY c.course_code;

-- =====================================================================
-- Trigger demonstration (run inside a transaction and roll back).
-- The CGPA of student 1 is recomputed automatically; a mismatched exam is rejected.
-- =====================================================================
BEGIN;
  SELECT student_id, reg_no, cgpa AS cgpa_before FROM student WHERE student_id = 1;
  UPDATE result SET marks_obtained = 99
   WHERE result_id = (SELECT MIN(r.result_id) FROM result r JOIN enrolment e USING (enrolment_id) WHERE e.student_id = 1);
  SELECT student_id, reg_no, cgpa AS cgpa_after_one_mark_raised FROM student WHERE student_id = 1;
ROLLBACK;

-- Expected to FAIL with: "Marks 120 exceed the exam maximum 100"
-- UPDATE result SET marks_obtained = 120 WHERE result_id = 1;
