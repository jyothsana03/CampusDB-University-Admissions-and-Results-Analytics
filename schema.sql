-- =====================================================================
-- CampusDB  -  University admissions and results analytics   (PostgreSQL 16)
-- Normalised to 3NF. Run:  psql -d campusdb -f schema.sql
-- =====================================================================
DROP VIEW     IF EXISTS v_course_pass_rate, v_result_detail CASCADE;
DROP TABLE    IF EXISTS result, exam, enrolment, student, course, programme, department CASCADE;
DROP FUNCTION IF EXISTS grade_point(NUMERIC, NUMERIC), fn_result_validate(), fn_recompute_cgpa() CASCADE;

-- ---------------------------------------------------------------------
-- Tables
-- ---------------------------------------------------------------------
CREATE TABLE department (
    dept_id    SERIAL       PRIMARY KEY,
    dept_name  VARCHAR(80)  NOT NULL UNIQUE
);

CREATE TABLE programme (
    programme_id    SERIAL       PRIMARY KEY,
    programme_code  VARCHAR(8)   NOT NULL UNIQUE,
    programme_name  VARCHAR(100) NOT NULL UNIQUE,
    dept_id         INT          NOT NULL REFERENCES department (dept_id),
    level           VARCHAR(2)   NOT NULL CHECK (level IN ('UG', 'PG')),
    seats           INT          NOT NULL CHECK (seats > 0)
);

CREATE TABLE course (
    course_id     SERIAL       PRIMARY KEY,
    course_code   VARCHAR(10)  NOT NULL UNIQUE,
    title         VARCHAR(100) NOT NULL,
    credits       SMALLINT     NOT NULL CHECK (credits BETWEEN 1 AND 6),
    semester      SMALLINT     NOT NULL CHECK (semester BETWEEN 1 AND 8),
    programme_id  INT          NOT NULL REFERENCES programme (programme_id),
    UNIQUE (programme_id, title)
);

CREATE TABLE student (
    student_id      SERIAL        PRIMARY KEY,
    reg_no          VARCHAR(12)   NOT NULL UNIQUE,
    full_name       VARCHAR(100)  NOT NULL,
    gender          CHAR(1)       NOT NULL CHECK (gender IN ('F', 'M', 'O')),
    birth_date      DATE          NOT NULL,
    email           VARCHAR(120)  NOT NULL UNIQUE,
    programme_id    INT           NOT NULL REFERENCES programme (programme_id),
    admission_year  SMALLINT      NOT NULL CHECK (admission_year BETWEEN 2000 AND 2100),
    entrance_score  NUMERIC(5,2)  NOT NULL CHECK (entrance_score BETWEEN 0 AND 100),
    -- Derived value kept on purpose (see README, "Deliberate denormalisation"):
    -- maintained only by trigger trg_result_cgpa, never written by hand.
    cgpa            NUMERIC(4,2)  NOT NULL DEFAULT 0 CHECK (cgpa BETWEEN 0 AND 10)
);

CREATE TABLE enrolment (
    enrolment_id   SERIAL    PRIMARY KEY,
    student_id     INT       NOT NULL REFERENCES student (student_id) ON DELETE CASCADE,
    course_id      INT       NOT NULL REFERENCES course (course_id),
    academic_year  SMALLINT  NOT NULL CHECK (academic_year BETWEEN 2000 AND 2100),
    UNIQUE (student_id, course_id)
);

CREATE TABLE exam (
    exam_id        SERIAL      PRIMARY KEY,
    course_id      INT         NOT NULL REFERENCES course (course_id),
    academic_year  SMALLINT    NOT NULL CHECK (academic_year BETWEEN 2000 AND 2100),
    exam_type      VARCHAR(10) NOT NULL DEFAULT 'Final' CHECK (exam_type IN ('Final', 'Supplement')),
    exam_date      DATE        NOT NULL,
    max_marks      SMALLINT    NOT NULL DEFAULT 100 CHECK (max_marks > 0),
    UNIQUE (course_id, academic_year, exam_type)
);

CREATE TABLE result (
    result_id       SERIAL        PRIMARY KEY,
    enrolment_id    INT           NOT NULL REFERENCES enrolment (enrolment_id) ON DELETE CASCADE,
    exam_id         INT           NOT NULL REFERENCES exam (exam_id),
    marks_obtained  NUMERIC(5,2)  NOT NULL CHECK (marks_obtained >= 0),
    UNIQUE (enrolment_id, exam_id)
);

CREATE INDEX idx_student_programme ON student (programme_id, admission_year);
CREATE INDEX idx_enrolment_course  ON enrolment (course_id);
CREATE INDEX idx_result_exam       ON result (exam_id);

-- ---------------------------------------------------------------------
-- Grading rule: 10-point scale, pass mark 40 % (IMMUTABLE so it can be indexed/reused)
-- ---------------------------------------------------------------------
CREATE FUNCTION grade_point(marks NUMERIC, max_marks NUMERIC) RETURNS INT
LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE
        WHEN marks * 100 / max_marks >= 90 THEN 10
        WHEN marks * 100 / max_marks >= 80 THEN 9
        WHEN marks * 100 / max_marks >= 70 THEN 8
        WHEN marks * 100 / max_marks >= 60 THEN 7
        WHEN marks * 100 / max_marks >= 50 THEN 6
        WHEN marks * 100 / max_marks >= 40 THEN 5
        ELSE 0 END
$$;

-- ---------------------------------------------------------------------
-- Trigger 1 (BEFORE INSERT/UPDATE on result): integrity the FKs cannot express.
-- The exam must belong to the same course and year as the enrolment,
-- and marks may not exceed the exam's maximum.
-- ---------------------------------------------------------------------
CREATE FUNCTION fn_result_validate() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    e_course INT; e_year INT; x_course INT; x_year INT; x_max INT;
BEGIN
    SELECT course_id, academic_year INTO e_course, e_year FROM enrolment WHERE enrolment_id = NEW.enrolment_id;
    SELECT course_id, academic_year, max_marks INTO x_course, x_year, x_max FROM exam WHERE exam_id = NEW.exam_id;
    IF e_course <> x_course OR e_year <> x_year THEN
        RAISE EXCEPTION 'Exam % is not the exam for enrolment % (course/year mismatch)', NEW.exam_id, NEW.enrolment_id;
    END IF;
    IF NEW.marks_obtained > x_max THEN
        RAISE EXCEPTION 'Marks % exceed the exam maximum %', NEW.marks_obtained, x_max;
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER trg_result_validate
    BEFORE INSERT OR UPDATE ON result
    FOR EACH ROW EXECUTE FUNCTION fn_result_validate();

-- ---------------------------------------------------------------------
-- Trigger 2 (AFTER INSERT/UPDATE/DELETE on result): recompute the student's CGPA
-- CGPA = SUM(grade_point x credits) / SUM(credits) over all of the student's results.
-- ---------------------------------------------------------------------
CREATE FUNCTION fn_recompute_cgpa() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    sid INT;
BEGIN
    SELECT en.student_id INTO sid
    FROM enrolment en
    WHERE en.enrolment_id = CASE WHEN TG_OP = 'DELETE' THEN OLD.enrolment_id ELSE NEW.enrolment_id END;

    -- the row may already be gone when an enrolment/student delete cascades
    IF sid IS NOT NULL AND EXISTS (SELECT 1 FROM student WHERE student_id = sid) THEN
        UPDATE student s
        SET cgpa = COALESCE((
            SELECT ROUND(SUM(grade_point(r.marks_obtained, x.max_marks) * c.credits)::NUMERIC / SUM(c.credits), 2)
            FROM result r
            JOIN enrolment en ON en.enrolment_id = r.enrolment_id
            JOIN exam x       ON x.exam_id       = r.exam_id
            JOIN course c     ON c.course_id     = en.course_id
            WHERE en.student_id = s.student_id), 0)
        WHERE s.student_id = sid;
    END IF;
    RETURN NULL;
END $$;

CREATE TRIGGER trg_result_cgpa
    AFTER INSERT OR UPDATE OR DELETE ON result
    FOR EACH ROW EXECUTE FUNCTION fn_recompute_cgpa();

-- ---------------------------------------------------------------------
-- Views
-- ---------------------------------------------------------------------
-- v_result_detail: one flat row per result, hiding the 6-table join behind a name.
CREATE VIEW v_result_detail AS
SELECT r.result_id, s.student_id, s.reg_no, s.full_name, s.admission_year,
       p.programme_id, p.programme_code, p.programme_name,
       c.course_id, c.course_code, c.title AS course_title, c.credits,
       x.academic_year, r.marks_obtained, x.max_marks,
       ROUND(r.marks_obtained * 100 / x.max_marks, 1)  AS percentage,
       grade_point(r.marks_obtained, x.max_marks)      AS grade_points,
       (r.marks_obtained * 100 / x.max_marks >= 40)    AS passed
FROM result r
JOIN enrolment en ON en.enrolment_id = r.enrolment_id
JOIN student   s  ON s.student_id    = en.student_id
JOIN programme p  ON p.programme_id  = s.programme_id
JOIN course    c  ON c.course_id     = en.course_id
JOIN exam      x  ON x.exam_id       = r.exam_id;

-- v_course_pass_rate: pass percentage per course (the headline metric of the project).
CREATE VIEW v_course_pass_rate AS
SELECT programme_code, course_code, course_title,
       COUNT(*)                                             AS appeared,
       COUNT(*) FILTER (WHERE passed)                       AS passed,
       ROUND(100.0 * COUNT(*) FILTER (WHERE passed) / COUNT(*), 1) AS pass_pct,
       ROUND(AVG(percentage), 1)                            AS avg_pct
FROM v_result_detail
GROUP BY programme_code, course_code, course_title;
