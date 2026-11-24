from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.orm import Session, selectinload
from app.api.auth import get_current_user, utc_now
from app.core.database import get_db
from app.models import (
    AcademicAffiliation, AuditLog, Course, Department, Faculty, LecturerProfile,
    Programme, ProgrammeCourse, University, User, UserRole,
)
from app.schemas.academic import (
    CourseDetailResponse, CourseListResponse, DepartmentResponse,
    ProgrammeResponse, ProgrammeCurriculumResponse, ProgrammeCourseResponse,
)

router = APIRouter(prefix="/api/academic", tags=["Academic"])


class AffiliationRequest(BaseModel):
    department_id: int = Field(ge=1)
    programme_id: int | None = Field(default=None, ge=1)
    level: str | None = Field(default=None, min_length=1, max_length=20)


def _affiliation_response(db: Session, user: User, affiliation: AcademicAffiliation | None):
    lecturer_profile = db.scalar(
        select(LecturerProfile).where(LecturerProfile.user_id == user.id)
    ) if user.role == UserRole.LECTURER else None
    department_id = affiliation.department_id if affiliation else (
        lecturer_profile.department_id if lecturer_profile else None
    )
    department = db.get(Department, department_id) if department_id else None
    faculty = db.get(Faculty, department.faculty_id) if department else None
    university = db.get(University, faculty.university_id) if faculty else None
    programme = db.get(Programme, affiliation.programme_id) if affiliation and affiliation.programme_id else None
    return {
        "status": affiliation.status if affiliation else "not_submitted",
        "department_id": department_id,
        "department_name": department.name if department else None,
        "faculty_name": faculty.name if faculty else None,
        "university_name": university.name if university else None,
        "programme_id": programme.id if programme else None,
        "programme_name": programme.name if programme else None,
        "level": affiliation.level if affiliation else None,
        "submitted_at": affiliation.submitted_at if affiliation else None,
        "verified_at": affiliation.verified_at if affiliation else None,
        "review_note": affiliation.review_note if affiliation else None,
        "department_locked": bool(lecturer_profile and lecturer_profile.department_id),
    }


@router.get("/affiliation/me")
def get_my_academic_affiliation(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.role == UserRole.ADMINISTRATOR:
        raise HTTPException(status_code=403, detail="Administrator accounts do not have academic affiliations.")
    affiliation = db.scalar(
        select(AcademicAffiliation).where(AcademicAffiliation.user_id == user.id)
    )
    return _affiliation_response(db, user, affiliation)


@router.put("/affiliation/me")
def request_academic_affiliation(
    data: AffiliationRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.role == UserRole.ADMINISTRATOR:
        raise HTTPException(status_code=403, detail="Administrator accounts do not have academic affiliations.")
    department = db.get(Department, data.department_id)
    if department is None:
        raise HTTPException(status_code=404, detail="Department not found.")
    programme = db.get(Programme, data.programme_id) if data.programme_id else None
    if data.programme_id and programme is None:
        raise HTTPException(status_code=404, detail="Programme not found.")
    if programme and programme.department_id != department.id:
        raise HTTPException(status_code=422, detail="Programme must belong to the selected department.")
    level = data.level.strip() if data.level else None
    if user.role == UserRole.STUDENT and (programme is None or not level):
        raise HTTPException(status_code=422, detail="Students must select a programme and academic level.")
    if user.role == UserRole.LECTURER:
        profile = db.scalar(select(LecturerProfile).where(LecturerProfile.user_id == user.id))
        if not profile or profile.department_id != department.id:
            raise HTTPException(status_code=403, detail="Lecturer affiliation must match the department assigned by an administrator.")
    affiliation = db.scalar(
        select(AcademicAffiliation).where(AcademicAffiliation.user_id == user.id)
    )
    if affiliation and (
        affiliation.department_id == department.id
        and affiliation.programme_id == (programme.id if programme else None)
        and affiliation.level == level
        and affiliation.status == "verified"
    ):
        return _affiliation_response(db, user, affiliation)
    if affiliation is None:
        affiliation = AcademicAffiliation(
            user_id=user.id,
            department_id=department.id,
            programme_id=programme.id if programme else None,
            level=level,
        )
        db.add(affiliation)
    else:
        affiliation.department_id = department.id
        affiliation.programme_id = programme.id if programme else None
        affiliation.level = level
        affiliation.status = "pending"
        affiliation.submitted_at = utc_now()
        affiliation.verified_at = None
        affiliation.verified_by_id = None
        affiliation.review_note = None
    db.add(AuditLog(
        user_id=user.id,
        action="academic.affiliation.submitted",
        entity_type="academic_affiliation",
        entity_id=user.id,
        details=f"department_id={department.id}; programme_id={programme.id if programme else 'none'}",
    ))
    db.commit()
    db.refresh(affiliation)
    return _affiliation_response(db, user, affiliation)


@router.get("/departments", response_model=list[DepartmentResponse])
def list_departments(db: Session = Depends(get_db)):
    return db.scalars(select(Department).order_by(Department.name.asc())).all()


@router.get("/programmes", response_model=list[ProgrammeResponse])
def list_programmes(db: Session = Depends(get_db)):
    return db.scalars(select(Programme).order_by(Programme.name.asc())).all()


@router.get("/programmes/{programme_id}/curriculum", response_model=ProgrammeCurriculumResponse)
def get_programme_curriculum(programme_id: int, db: Session = Depends(get_db)):
    programme = db.get(Programme, programme_id)
    if programme is None:
        raise HTTPException(status_code=404, detail="Programme not found.")
    rows = db.scalars(
        select(ProgrammeCourse)
        .options(selectinload(ProgrammeCourse.course).selectinload(Course.topics))
        .where(ProgrammeCourse.programme_id == programme_id)
        .order_by(ProgrammeCourse.semester, ProgrammeCourse.course_id)
    ).all()
    items = [
        ProgrammeCourseResponse(
            id=row.id, course_id=row.course.id, code=row.course.code,
            title=row.course.title, semester=row.semester or row.course.semester,
            credit_units=row.course.credit_units, requirement_type=row.requirement_type,
            verification_status=row.verification_status, source=row.source,
        ) for row in rows
    ]
    return ProgrammeCurriculumResponse(programme=programme, total=len(items), items=items)


@router.get("/courses", response_model=CourseListResponse)
def list_courses(
    level: str | None = Query(default=None, min_length=1, max_length=20),
    semester: str | None = Query(default=None, min_length=1, max_length=20),
    department_id: int | None = Query(default=None, ge=1),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
):
    statement = select(Course).options(selectinload(Course.topics))
    count_statement = select(func.count(Course.id))
    if level is not None:
        statement = statement.where(Course.level == level.strip())
        count_statement = count_statement.where(Course.level == level.strip())
    if semester is not None:
        statement = statement.where(Course.semester == semester.strip())
        count_statement = count_statement.where(Course.semester == semester.strip())
    if department_id is not None:
        statement = statement.where(Course.department_id == department_id)
        count_statement = count_statement.where(Course.department_id == department_id)
    total = db.scalar(count_statement) or 0
    courses = db.scalars(statement.order_by(Course.code.asc()).offset(skip).limit(limit)).all()
    for course in courses:
        course.topics.sort(key=lambda topic: (topic.position, topic.id))
    return CourseListResponse(total=total, skip=skip, limit=limit, items=courses)


@router.get("/courses/{course_id}", response_model=CourseDetailResponse)
def get_course(course_id: int, db: Session = Depends(get_db)):
    course = db.scalar(
        select(Course).options(selectinload(Course.topics)).where(Course.id == course_id)
    )
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found.")
    course.topics.sort(key=lambda topic: (topic.position, topic.id))
    return course
