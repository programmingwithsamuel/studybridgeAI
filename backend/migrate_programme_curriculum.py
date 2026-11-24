"""Safe, repeatable SQLite migration for programme-based curricula.

Run from C:\\studybridgeAi with the backend virtual environment active.
This migration adds tables/one metadata column; it does not delete or rewrite
courses, topics, users, documents, or existing department IDs.
"""
from pathlib import Path
import sqlite3

DB = Path(__file__).resolve().parent / "studybridge.db"
conn = sqlite3.connect(DB)
conn.execute("PRAGMA foreign_keys = ON")

def columns(table):
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}

try:
    conn.execute("BEGIN")
    if "department_assignment_status" not in columns("courses"):
        conn.execute(
            "ALTER TABLE courses ADD COLUMN department_assignment_status "
            "VARCHAR(30) NOT NULL DEFAULT 'unverified'"
        )

    conn.execute("""
        CREATE TABLE IF NOT EXISTS programmes (
            id INTEGER PRIMARY KEY,
            name VARCHAR(200) NOT NULL,
            code VARCHAR(50) NOT NULL UNIQUE,
            department_id INTEGER NOT NULL REFERENCES departments(id) ON DELETE RESTRICT,
            level VARCHAR(20) NOT NULL DEFAULT '100 Level',
            university_id INTEGER NOT NULL REFERENCES universities(id) ON DELETE RESTRICT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS programme_courses (
            id INTEGER PRIMARY KEY,
            programme_id INTEGER NOT NULL REFERENCES programmes(id) ON DELETE CASCADE,
            course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE RESTRICT,
            academic_year VARCHAR(30),
            semester VARCHAR(20),
            requirement_type VARCHAR(30) NOT NULL DEFAULT 'required',
            source VARCHAR(500),
            verification_status VARCHAR(30) NOT NULL DEFAULT 'unverified',
            CONSTRAINT uq_programme_course UNIQUE(programme_id, course_id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS ix_programmes_department_id ON programmes(department_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_programmes_university_id ON programmes(university_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_programme_courses_programme_id ON programme_courses(programme_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_programme_courses_course_id ON programme_courses(course_id)")

    # Resolve the existing Computer Science department and university without assuming IDs.
    dept = conn.execute(
        "SELECT d.id, f.university_id FROM departments d "
        "JOIN faculties f ON f.id=d.faculty_id WHERE lower(d.name)=lower(?)",
        ("Computer Science",)
    ).fetchone()
    if not dept:
        raise RuntimeError("Computer Science department was not found. No migration committed.")
    department_id, university_id = dept

    conn.execute("""
        INSERT OR IGNORE INTO programmes
        (name, code, department_id, level, university_id)
        VALUES (?, ?, ?, ?, ?)
    """, (
        "B.Sc. Computer Science",
        "UNIZIK-BSC-CSC",
        department_id,
        "100 Level",
        university_id,
    ))
    programme_id = conn.execute(
        "SELECT id FROM programmes WHERE code=?", ("UNIZIK-BSC-CSC",)
    ).fetchone()[0]

    # Associate every existing Year One course with the programme curriculum.
    # Preserve its current department_id; mark that assignment unverified because
    # it was a temporary import workaround, not verified teaching-department data.
    course_rows = conn.execute(
        "SELECT id, semester, source FROM courses WHERE level IN ('100 Level','100') OR level IS NULL"
    ).fetchall()
    for course_id, semester, source in course_rows:
        conn.execute("""
            INSERT OR IGNORE INTO programme_courses
            (programme_id, course_id, semester, requirement_type, source, verification_status)
            VALUES (?, ?, ?, 'required', ?, 'unverified')
        """, (programme_id, course_id, semester, source or "Imported Year One curriculum; source requires verification"))

    conn.execute(
        "UPDATE courses SET department_assignment_status='unverified' "
        "WHERE id IN (SELECT course_id FROM programme_courses WHERE programme_id=?)",
        (programme_id,)
    )
    conn.commit()

    linked = conn.execute(
        "SELECT COUNT(*) FROM programme_courses WHERE programme_id=?", (programme_id,)
    ).fetchone()[0]
    total_topics = conn.execute("SELECT COUNT(*) FROM course_topics").fetchone()[0]
    print("MIGRATION COMPLETED")
    print(f"Programme: B.Sc. Computer Science (ID {programme_id})")
    print(f"Curriculum courses linked: {linked}")
    print(f"Existing course topics preserved: {total_topics}")
    print("Department assignments remain unverified; no course was reassigned.")
except Exception:
    conn.rollback()
    raise
finally:
    conn.close()
