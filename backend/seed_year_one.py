
import sys

sys.path.insert(0, "backend")

from sqlalchemy import select
from app.core.database import SessionLocal
from app.models import University, Faculty, Department, Course

SOURCE = "User-provided UNIZIK 100 Level curriculum image"
LEVEL = "100"

# Course code, title, semester, units, lecture hours, practical hours
COURSES = [
    # FIRST SEMESTER
    ("COS 101", "Introduction to Computing Sciences", "First", 3, 30, 45),
    ("MTH 101", "Elementary Mathematics I", "First", 2, 30, 0),
    ("PHY 101", "General Physics I", "First", 2, 30, 0),
    ("PHY 107", "General Practical Physics I", "First", 1, 0, 45),
    ("STA 111", "Descriptive Statistics", "First", 3, 45, 0),
    ("NAU-CSC 111", "Foundations of Computing Sciences I", "First", 3, 30, 45),
    ("NAU-CHM 101", "General Inorganic Chemistry", "First", 2, 30, 0),
    ("NAU-BIO 101", "General Biology 1", "First", 2, 30, 0),
    ("GST 111", "Communication in English", "First", 2, 30, 0),
    ("NAU-GST 113", "Humanities", "First", 2, 30, 0),
    ("NAU-GST 115", "Communication Skills", "First", 0, 30, 0),

    # SECOND SEMESTER
    ("COS 102", "Problem Solving", "Second", 3, 30, 45),
    ("GST 112", "Nigerian Peoples and Culture", "Second", 2, 30, 0),
    ("MTH 102", "Elementary Mathematics II", "Second", 2, 30, 0),
    ("PHY 108", "General Practical Physics II", "Second", 1, 0, 45),
    ("PHY 102", "General Physics II", "Second", 2, 30, 0),
    ("NAU-CSC 110", "Foundations of Computing Sciences II", "Second", 3, 30, 45),
    ("NAU-CSC 112", "Computer Application and Management", "Second", 2, 30, 45),
    ("NAU-STA 112", "Probability 1", "Second", 3, 30, 0),
    ("NAU-MAT 112", "Introduction to Actuarial Mathematics I", "Second", 2, 30, 0),
    ("NAU-GST 114", "Basic Igbo Studies", "Second", 2, 30, 0),
]

def import_courses():
    db = SessionLocal()

    try:
        university = db.scalar(
            select(University).where(
                University.name == "Nnamdi Azikiwe University"
            )
        )

        if university is None:
            raise RuntimeError("University not found.")

        faculty = db.scalar(
            select(Faculty).where(
                Faculty.name == "Faculty of Physical Sciences",
                Faculty.university_id == university.id,
            )
        )

        if faculty is None:
            raise RuntimeError("Faculty of Physical Sciences not found.")

        department = db.scalar(
            select(Department).where(
                Department.name == "Computer Science",
                Department.faculty_id == faculty.id,
            )
        )

        if department is None:
            raise RuntimeError("Computer Science department not found.")

        created = 0
        skipped = 0

        for code, title, semester, units, lh, ph in COURSES:
            existing = db.scalar(
                select(Course).where(
                    Course.department_id == department.id,
                    Course.code == code,
                )
            )

            if existing:
                print("ALREADY EXISTS:", code)
                skipped += 1
                continue

            course = Course(
                code=code,
                title=title,
                level=LEVEL,
                semester=semester,
                credit_units=units,
                lecture_hours=lh,
                practical_hours=ph,
                verification_status="unverified",
                source=SOURCE,
                department_id=department.id,
            )

            db.add(course)
            print("ADDED:", code, "-", title)
            created += 1

        db.commit()

        print("\nIMPORT COMPLETED")
        print("Created:", created)
        print("Skipped:", skipped)
        print("Total curriculum entries:", len(COURSES))

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()

if __name__ == "__main__":
    import_courses()