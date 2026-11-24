
import sys

sys.path.insert(0, "backend")

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import University, Faculty, Department

UNIVERSITY_NAME = "Nnamdi Azikiwe University"
FACULTY_NAME = "Faculty of Physical Sciences"

DEPARTMENTS = [
    "Computer Science",
    "Geology",
    "Applied Geophysics",
    "Mathematics",
    "Physics and Industrial Physics",
    "Pure and Industrial Chemistry",
    "Statistics",
]

def import_academic_structure():
    db = SessionLocal()

    try:
        # Find or create university
        university = db.scalar(
            select(University).where(
                University.name == UNIVERSITY_NAME
            )
        )

        if university is None:
            university = University(name=UNIVERSITY_NAME)
            db.add(university)
            db.flush()
            print("CREATED UNIVERSITY:", university.name)
        else:
            print("UNIVERSITY ALREADY EXISTS:", university.name)

        # Find or create faculty
        faculty = db.scalar(
            select(Faculty).where(
                Faculty.name == FACULTY_NAME,
                Faculty.university_id == university.id,
            )
        )

        if faculty is None:
            faculty = Faculty(
                name=FACULTY_NAME,
                university_id=university.id,
            )
            db.add(faculty)
            db.flush()
            print("CREATED FACULTY:", faculty.name)
        else:
            print("FACULTY ALREADY EXISTS:", faculty.name)

        # Find or create departments
        for department_name in DEPARTMENTS:
            department = db.scalar(
                select(Department).where(
                    Department.name == department_name,
                    Department.faculty_id == faculty.id,
                )
            )

            if department is None:
                department = Department(
                    name=department_name,
                    faculty_id=faculty.id,
                )
                db.add(department)
                print("CREATED DEPARTMENT:", department_name)
            else:
                print("ALREADY EXISTS:", department_name)

        db.commit()

        print("\nIMPORT COMPLETED SUCCESSFULLY")
        print("University:", UNIVERSITY_NAME)
        print("Faculty:", FACULTY_NAME)
        print("Departments:", len(DEPARTMENTS))

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()

if __name__ == "__main__":
    import_academic_structure()