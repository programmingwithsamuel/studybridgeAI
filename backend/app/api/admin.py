from datetime import timedelta
import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.auth import checked_email, create_auth_token, rate_limit, token_hash, utc_now
from app.api.dependencies import require_roles
from app.core.database import get_db
from app.core.email_delivery import EmailDeliveryError, invitation_url, send_email
from app.core.security import hash_password
from app.models import (
    AcademicAffiliation, AuditLog, AuthToken, ChatMessage, ChatSession,
    Course, Department, DocumentPermission,
    LecturerCourseAssignment, LecturerProfile, Programme, ProfileChangeRequest,
    ReviewerAssignment, StudentProfile, StudentProgress, User, UserRole, UserSession,
)

router = APIRouter(prefix="/api/admin", tags=["Administration"])
AdminUser = Depends(require_roles(UserRole.ADMINISTRATOR))


class LecturerCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=150)
    staff_number: str = Field(min_length=2, max_length=50)
    username: str = Field(min_length=3, max_length=80)
    email: str = Field(min_length=5, max_length=255)
    phone: str | None = Field(default=None, max_length=30)
    department_id: int
    title: str | None = Field(default=None, max_length=100)
    course_ids: list[int] = Field(default_factory=list)


class LecturerUpdate(BaseModel):
    department_id: int
    course_ids: list[int] = Field(default_factory=list)


class MemberRoleUpdate(BaseModel):
    role: UserRole


class MemberSuspendRequest(BaseModel):
    reason: str = Field(min_length=5, max_length=500)


class AffiliationReview(BaseModel):
    decision: str = Field(pattern="^(verified|rejected)$")
    note: str | None = Field(default=None, max_length=1000)


class ReviewerAssignmentCreate(BaseModel):
    user_id: int = Field(ge=1)
    department_id: int | None = Field(default=None, ge=1)
    course_id: int | None = Field(default=None, ge=1)


def audit(db: Session, actor: User, action: str, entity_type: str, entity_id: int, details: str):
    db.add(AuditLog(user_id=actor.id, action=action, entity_type=entity_type, entity_id=entity_id, details=details))


def next_lecturer_id(db: Session) -> str:
    row = db.execute(
        select(LecturerProfile.lecturer_id)
        .where(LecturerProfile.lecturer_id.is_not(None))
        .order_by(LecturerProfile.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    number = 1
    if row:
        suffix = row.rsplit("-", 1)[-1]
        if suffix.isdigit():
            number = int(suffix) + 1
    return f"SB-UNIZIK-LEC-{number:06d}"


@router.post("/lecturers", status_code=201)
def create_lecturer(
    request: Request,
    data: LecturerCreate,
    db: Session = Depends(get_db),
    admin: User = AdminUser,
):
    rate_limit(request, "lecturer_create", 30)
    email = checked_email(data.email)
    username = data.username.strip()
    staff_number = data.staff_number.strip()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="Email address is already in use.")
    if db.scalar(select(User).where(User.username == username)):
        raise HTTPException(status_code=409, detail="Username is already in use.")
    if db.scalar(select(LecturerProfile).where(LecturerProfile.staff_number == staff_number)):
        raise HTTPException(status_code=409, detail="Staff number is already in use.")
    department = db.get(Department, data.department_id)
    if not department:
        raise HTTPException(status_code=404, detail="Department not found.")
    if len(set(data.course_ids)) != len(data.course_ids):
        raise HTTPException(status_code=422, detail="Duplicate course assignments are not allowed.")
    for course_id in data.course_ids:
        course = db.get(Course, course_id)
        if not course or course.department_id != department.id:
            raise HTTPException(status_code=422, detail="One or more courses are not in the selected department.")

    user = User(
        full_name=data.full_name.strip(),
        email=email,
        username=username,
        password_hash=hash_password(secrets.token_urlsafe(48)),
        role=UserRole.LECTURER,
        email_verified=False,
        is_active=False,
    )
    db.add(user)
    db.flush()
    profile = LecturerProfile(
        user_id=user.id,
        lecturer_id=next_lecturer_id(db),
        staff_number=staff_number,
        department_id=department.id,
        title=data.title.strip() if data.title else None,
        phone=data.phone.strip() if data.phone else None,
        invitation_status="pending",
        invitation_expires_at=utc_now() + timedelta(days=7),
    )
    db.add(profile)
    db.flush()
    for course_id in set(data.course_ids):
        db.add(LecturerCourseAssignment(lecturer_profile_id=profile.id, course_id=course_id))

    token = create_auth_token(db, user, "lecturer_invite")
    record = db.scalar(select(AuthToken).where(AuthToken.token_hash == token_hash(token)))
    if record:
        record.expires_at = utc_now() + timedelta(days=7)
    link = invitation_url(token)
    try:
        send_email(
            user.email,
            "Activate your StudyBridge AI lecturer account",
            f"Open this link to set your password and activate your account: {link}\nThis invitation expires in 7 days.",
            f'<p>Open this link to activate your lecturer account.</p><p><a href="{link}">Activate lecturer account</a></p><p>Invitation expires in 7 days.</p>',
        )
    except EmailDeliveryError:
        db.rollback()
        raise HTTPException(status_code=502, detail="Lecturer invitation could not be sent. No account was created.")
    audit(db, admin, "lecturer.created", "lecturer", user.id, f"lecturer_id={profile.lecturer_id}; staff_number={staff_number}; department_id={department.id}")
    db.commit()
    db.refresh(profile)
    return {
        "id": user.id,
        "lecturer_id": profile.lecturer_id,
        "full_name": user.full_name,
        "username": user.username,
        "email": user.email,
        "staff_number": profile.staff_number,
        "department_id": profile.department_id,
        "invitation_status": profile.invitation_status,
        "email_verified": user.email_verified,
        "is_active": user.is_active,
        "development_invitation_url": link if __import__("app.core.config", fromlist=["settings"]).settings.EMAIL_MODE.lower() == "console" else None,
    }


@router.get("/lecturers")
def list_lecturers(
    search: str = "",
    department_id: int | None = None,
    status_filter: str | None = None,
    db: Session = Depends(get_db),
    _admin: User = AdminUser,
):
    users = db.query(User).join(LecturerProfile, LecturerProfile.user_id == User.id).filter(User.role == UserRole.LECTURER)
    if search.strip():
        term = f"%{search.strip()}%"
        users = users.filter(
            (User.full_name.ilike(term)) |
            (User.email.ilike(term)) |
            (User.username.ilike(term)) |
            (LecturerProfile.staff_number.ilike(term))
        )
    if department_id is not None:
        users = users.filter(LecturerProfile.department_id == department_id)
    if status_filter:
        if status_filter == "active":
            users = users.filter(User.is_active.is_(True))
        elif status_filter == "inactive":
            users = users.filter(User.is_active.is_(False))
        elif status_filter in ("pending", "accepted", "expired"):
            users = users.filter(LecturerProfile.invitation_status == status_filter)
    rows = users.order_by(User.full_name.asc()).all()
    result = []
    for user in rows:
        profile = db.scalar(select(LecturerProfile).where(LecturerProfile.user_id == user.id))
        assigned_course_ids = db.scalars(
            select(LecturerCourseAssignment.course_id).where(
                LecturerCourseAssignment.lecturer_profile_id == profile.id
            )
        ).all() if profile else []
        result.append({
            "id": user.id,
            "lecturer_id": profile.lecturer_id if profile else None,
            "full_name": user.full_name,
            "username": user.username,
            "email": user.email,
            "staff_number": profile.staff_number if profile else None,
            "department_id": profile.department_id if profile else None,
            "invitation_status": profile.invitation_status if profile else None,
            "assigned_course_ids": assigned_course_ids,
            "email_verified": user.email_verified,
            "is_active": user.is_active,
        })
    return {"items": result}


@router.post("/lecturers/{lecturer_id}/suspend")
def suspend_lecturer(
    lecturer_id: int,
    db: Session = Depends(get_db),
    admin: User = AdminUser,
):
    user = db.get(User, lecturer_id)
    if not user or user.role != UserRole.LECTURER:
        raise HTTPException(status_code=404, detail="Lecturer not found.")
    user.is_active = False
    db.execute(update(UserSession).where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None)).values(revoked_at=utc_now()))
    audit(db, admin, "lecturer.suspended", "lecturer", user.id, "is_active=false")
    db.commit()
    return {"message": "Lecturer suspended.", "is_active": False}


@router.post("/lecturers/{lecturer_id}/reactivate")
def reactivate_lecturer(
    lecturer_id: int,
    db: Session = Depends(get_db),
    admin: User = AdminUser,
):
    user = db.get(User, lecturer_id)
    if not user or user.role != UserRole.LECTURER:
        raise HTTPException(status_code=404, detail="Lecturer not found.")
    user.is_active = True
    audit(db, admin, "lecturer.reactivated", "lecturer", user.id, "is_active=true")
    db.commit()
    return {"message": "Lecturer reactivated.", "is_active": True}


@router.put("/lecturers/{lecturer_id}")
def update_lecturer(
    lecturer_id: int,
    data: LecturerUpdate,
    db: Session = Depends(get_db),
    admin: User = AdminUser,
):
    user = db.get(User, lecturer_id)
    if not user or user.role != UserRole.LECTURER:
        raise HTTPException(status_code=404, detail="Lecturer not found.")
    profile = db.scalar(select(LecturerProfile).where(LecturerProfile.user_id == user.id))
    department = db.get(Department, data.department_id)
    if not profile or not department:
        raise HTTPException(status_code=404, detail="Lecturer or department not found.")
    old_department = profile.department_id
    profile.department_id = department.id
    affiliation = db.scalar(
        select(AcademicAffiliation).where(AcademicAffiliation.user_id == user.id)
    )
    if affiliation and affiliation.department_id != department.id:
        affiliation.department_id = department.id
        affiliation.status = "pending"
        affiliation.submitted_at = utc_now()
        affiliation.verified_at = None
        affiliation.verified_by_id = None
        affiliation.review_note = None
    db.query(LecturerCourseAssignment).filter_by(lecturer_profile_id=profile.id).delete()
    for course_id in set(data.course_ids):
        course = db.get(Course, course_id)
        if not course or course.department_id != department.id:
            raise HTTPException(status_code=422, detail="All assigned courses must belong to the lecturer department.")
        db.add(LecturerCourseAssignment(lecturer_profile_id=profile.id, course_id=course_id))
    audit(db, admin, "lecturer.department_or_courses.updated", "lecturer", user.id,
          f"department_id={old_department}->{department.id}; course_ids={sorted(set(data.course_ids))}")
    db.commit()
    return {"message": "Lecturer department and course assignments updated."}


@router.post("/lecturers/{lecturer_id}/resend-invitation")
def resend_lecturer_invitation(
    request: Request,
    lecturer_id: int,
    db: Session = Depends(get_db),
    admin: User = AdminUser,
):
    rate_limit(request, "lecturer_invite_resend", 5)
    user = db.get(User, lecturer_id)
    if not user or user.role != UserRole.LECTURER:
        raise HTTPException(status_code=404, detail="Lecturer not found.")
    if user.email_verified:
        raise HTTPException(status_code=409, detail="This lecturer account is already activated.")
    profile = db.scalar(select(LecturerProfile).where(LecturerProfile.user_id == user.id))
    token = create_auth_token(db, user, "lecturer_invite")
    record = db.scalar(select(AuthToken).where(AuthToken.token_hash == token_hash(token)))
    if record:
        record.expires_at = utc_now() + timedelta(days=7)
    if profile:
        profile.invitation_status = "pending"
        profile.invitation_expires_at = utc_now() + timedelta(days=7)
    link = invitation_url(token)
    try:
        send_email(user.email, "Resend: activate your lecturer account",
                   f"Activate your account: {link}",
                   f'<p>Activate your lecturer account.</p><p><a href="{link}">Activate account</a></p>')
    except EmailDeliveryError:
        db.rollback()
        raise HTTPException(status_code=502, detail="Invitation email could not be sent.")
    audit(db, admin, "lecturer.invitation.resent", "lecturer", user.id, "previous invitation superseded")
    db.commit()
    return {
        "message": "Lecturer invitation resent.",
        "development_invitation_url": link if __import__("app.core.config", fromlist=["settings"]).settings.EMAIL_MODE.lower() == "console" else None,
    }


@router.post("/lecturers/{lecturer_id}/revoke-sessions")
def revoke_lecturer_sessions(
    lecturer_id: int,
    db: Session = Depends(get_db),
    admin: User = AdminUser,
):
    user = db.get(User, lecturer_id)
    if not user:
        raise HTTPException(status_code=404, detail="Lecturer not found.")
    db.execute(update(UserSession).where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None)).values(revoked_at=utc_now()))
    audit(db, admin, "lecturer.sessions.revoked", "lecturer", user.id, "all active sessions revoked")
    db.commit()
    return {"message": "Lecturer sessions revoked."}


@router.get("/students")
def list_students(
    db: Session = Depends(get_db),
    _admin: User = AdminUser,
):
    users = db.query(User).filter(User.role == UserRole.STUDENT).order_by(User.created_at.desc()).all()
    return {"items": [{
        "id": u.id, "full_name": u.full_name, "email": u.email,
        "email_verified": u.email_verified, "is_active": u.is_active, "created_at": u.created_at,
    } for u in users]}


@router.get("/academic-affiliations")
def list_academic_affiliations(
    status_filter: str = Query(default="pending", pattern="^(pending|verified|rejected|all)$"),
    db: Session = Depends(get_db),
    _admin: User = AdminUser,
):
    query = (
        db.query(AcademicAffiliation, User, Department)
        .join(User, User.id == AcademicAffiliation.user_id)
        .join(Department, Department.id == AcademicAffiliation.department_id)
    )
    if status_filter != "all":
        query = query.filter(AcademicAffiliation.status == status_filter)
    rows = query.order_by(AcademicAffiliation.submitted_at.desc()).all()
    result = []
    for affiliation, user, department in rows:
        programme = db.get(Programme, affiliation.programme_id) if affiliation.programme_id else None
        result.append({
            "id": affiliation.id,
            "user_id": user.id,
            "full_name": user.full_name,
            "email": user.email,
            "role": user.role.value,
            "status": affiliation.status,
            "department_id": department.id,
            "department_name": department.name,
            "faculty_name": department.faculty.name,
            "university_name": department.faculty.university.name,
            "programme_id": programme.id if programme else None,
            "programme_name": programme.name if programme else None,
            "level": affiliation.level,
            "submitted_at": affiliation.submitted_at,
            "verified_at": affiliation.verified_at,
            "review_note": affiliation.review_note,
        })
    return {"items": result}


@router.post("/academic-affiliations/{affiliation_id}/review")
def review_academic_affiliation(
    affiliation_id: int,
    data: AffiliationReview,
    db: Session = Depends(get_db),
    admin: User = AdminUser,
):
    affiliation = db.get(AcademicAffiliation, affiliation_id)
    if affiliation is None:
        raise HTTPException(status_code=404, detail="Academic affiliation not found.")
    if affiliation.status != "pending":
        raise HTTPException(status_code=409, detail="This affiliation has already been reviewed.")
    if data.decision == "rejected" and not (data.note and data.note.strip()):
        raise HTTPException(status_code=422, detail="A reason is required when rejecting an affiliation.")
    member = db.get(User, affiliation.user_id)
    if member is None or member.role == UserRole.ADMINISTRATOR:
        raise HTTPException(status_code=409, detail="This account cannot have an academic affiliation.")
    if data.decision == "verified":
        if member.role == UserRole.LECTURER:
            profile = db.scalar(select(LecturerProfile).where(LecturerProfile.user_id == member.id))
            if not profile or profile.department_id != affiliation.department_id:
                raise HTTPException(status_code=409, detail="The affiliation does not match the lecturer's assigned department.")
        if affiliation.programme_id:
            programme = db.get(Programme, affiliation.programme_id)
            if not programme or programme.department_id != affiliation.department_id:
                raise HTTPException(status_code=409, detail="The selected programme no longer matches the department.")
        if member.role == UserRole.STUDENT:
            profile = db.scalar(select(StudentProfile).where(StudentProfile.user_id == member.id))
            if profile is None:
                profile = StudentProfile(user_id=member.id)
                db.add(profile)
            profile.department_id = affiliation.department_id
            profile.level = affiliation.level
    affiliation.status = data.decision
    affiliation.verified_at = utc_now() if data.decision == "verified" else None
    affiliation.verified_by_id = admin.id
    affiliation.review_note = data.note.strip() if data.note else None
    audit(
        db, admin, f"academic.affiliation.{data.decision}", "academic_affiliation",
        affiliation.id, f"user_id={member.id}; department_id={affiliation.department_id}",
    )
    db.commit()
    return {"message": f"Academic affiliation {data.decision}."}


@router.get("/reviewer-assignments")
def list_reviewer_assignments(
    db: Session = Depends(get_db),
    _admin: User = AdminUser,
):
    rows = db.query(ReviewerAssignment).order_by(
        ReviewerAssignment.active.desc(), ReviewerAssignment.assigned_at.desc()
    ).all()
    return {"items": [{
        "id": row.id,
        "user_id": row.user_id,
        "reviewer_name": row.user.full_name,
        "reviewer_email": row.user.email,
        "department_id": row.department_id,
        "department_name": row.department.name if row.department else None,
        "course_id": row.course_id,
        "course_code": row.course.code if row.course else None,
        "course_title": row.course.title if row.course else None,
        "active": row.active,
        "assigned_at": row.assigned_at,
    } for row in rows]}


@router.post("/reviewer-assignments", status_code=201)
def create_reviewer_assignment(
    data: ReviewerAssignmentCreate,
    db: Session = Depends(get_db),
    admin: User = AdminUser,
):
    if (data.department_id is None) == (data.course_id is None):
        raise HTTPException(status_code=422, detail="Choose exactly one department or course scope.")
    reviewer = db.get(User, data.user_id)
    if reviewer is None or reviewer.role != UserRole.DEPARTMENT_REVIEWER or not reviewer.is_active:
        raise HTTPException(status_code=409, detail="Choose an active department reviewer account.")
    affiliation = db.scalar(
        select(AcademicAffiliation).where(AcademicAffiliation.user_id == reviewer.id)
    )
    if not affiliation or affiliation.status != "verified":
        raise HTTPException(status_code=409, detail="Verify the reviewer's academic affiliation before assigning a scope.")
    if data.department_id is not None:
        department = db.get(Department, data.department_id)
        if department is None:
            raise HTTPException(status_code=404, detail="Department not found.")
        if affiliation.department_id != department.id:
            raise HTTPException(status_code=403, detail="Reviewers can only be assigned within their verified department.")
    else:
        course = db.get(Course, data.course_id)
        if course is None:
            raise HTTPException(status_code=404, detail="Course not found.")
        if affiliation.department_id != course.department_id:
            raise HTTPException(status_code=403, detail="Course must belong to the reviewer's verified department.")
    query = db.query(ReviewerAssignment).filter(
        ReviewerAssignment.user_id == reviewer.id,
        ReviewerAssignment.department_id == data.department_id,
        ReviewerAssignment.course_id == data.course_id,
    )
    assignment = query.first()
    if assignment and assignment.active:
        raise HTTPException(status_code=409, detail="This reviewer already has that active scope.")
    if assignment:
        assignment.active = True
        assignment.assigned_by_id = admin.id
        assignment.assigned_at = utc_now()
    else:
        assignment = ReviewerAssignment(
            user_id=reviewer.id,
            department_id=data.department_id,
            course_id=data.course_id,
            assigned_by_id=admin.id,
        )
        db.add(assignment)
        db.flush()
    audit(
        db, admin, "reviewer.assignment.created", "reviewer_assignment",
        assignment.id, f"user_id={reviewer.id}; department_id={data.department_id}; course_id={data.course_id}",
    )
    db.commit()
    return {"id": assignment.id, "message": "Reviewer scope assigned."}


@router.post("/reviewer-assignments/{assignment_id}/revoke")
def revoke_reviewer_assignment(
    assignment_id: int,
    db: Session = Depends(get_db),
    admin: User = AdminUser,
):
    assignment = db.get(ReviewerAssignment, assignment_id)
    if assignment is None:
        raise HTTPException(status_code=404, detail="Reviewer assignment not found.")
    if not assignment.active:
        raise HTTPException(status_code=409, detail="Reviewer assignment is already inactive.")
    assignment.active = False
    audit(
        db, admin, "reviewer.assignment.revoked", "reviewer_assignment",
        assignment.id, f"user_id={assignment.user_id}",
    )
    db.commit()
    return {"message": "Reviewer scope revoked."}


@router.get("/audit")
def audit_activity(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    action: str | None = None,
    actor_id: int | None = Query(default=None, ge=1),
    archived: bool = False,
    db: Session = Depends(get_db),
    _admin: User = AdminUser,
):
    query = db.query(AuditLog)
    query = query.filter(AuditLog.archived_at.is_not(None) if archived else AuditLog.archived_at.is_(None))
    if action:
        query = query.filter(AuditLog.action.ilike(f"%{action.strip()}%"))
    if actor_id is not None:
        query = query.filter(AuditLog.user_id == actor_id)
    total = query.count()
    rows = query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).offset(skip).limit(limit).all()
    return {"items": [{
        "id": r.id, "user_id": r.user_id, "action": r.action,
        "entity_type": r.entity_type, "entity_id": r.entity_id,
        "details": r.details, "created_at": r.created_at,
        "archived_at": r.archived_at, "archived_by": r.archived_by,
    } for r in rows], "total": total, "skip": skip, "limit": limit}


@router.post("/audit/{activity_id}/archive")
def archive_audit_activity(
    activity_id: int,
    db: Session = Depends(get_db),
    admin: User = AdminUser,
):
    activity = db.get(AuditLog, activity_id)
    if not activity:
        raise HTTPException(status_code=404, detail="Activity record not found.")
    if activity.action in {"audit.activity.archived", "audit.activity.restored"}:
        raise HTTPException(status_code=409, detail="Audit archive history cannot itself be archived.")
    if activity.archived_at is not None:
        raise HTTPException(status_code=409, detail="Activity record is already archived.")

    activity.archived_at = utc_now()
    activity.archived_by = admin.id
    audit(db, admin, "audit.activity.archived", "audit_log", activity.id, f"action={activity.action}")
    db.commit()
    return {"message": "Activity record archived."}


@router.post("/audit/{activity_id}/restore")
def restore_audit_activity(
    activity_id: int,
    db: Session = Depends(get_db),
    admin: User = AdminUser,
):
    activity = db.get(AuditLog, activity_id)
    if not activity:
        raise HTTPException(status_code=404, detail="Activity record not found.")
    if activity.archived_at is None:
        raise HTTPException(status_code=409, detail="Activity record is not archived.")

    activity.archived_at = None
    activity.archived_by = None
    audit(db, admin, "audit.activity.restored", "audit_log", activity.id, f"action={activity.action}")
    db.commit()
    return {"message": "Activity record restored."}


@router.get("/members")
def list_members(
    search: str = "",
    role: UserRole | None = None,
    is_active: bool | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    _admin: User = AdminUser,
):
    query = db.query(User, LecturerProfile.id, AcademicAffiliation.status, AcademicAffiliation.department_id).outerjoin(
        LecturerProfile, LecturerProfile.user_id == User.id
    ).outerjoin(
        AcademicAffiliation, AcademicAffiliation.user_id == User.id
    ).filter(User.deleted_at.is_(None))
    if search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(
            User.full_name.ilike(term)
            | User.email.ilike(term)
            | User.username.ilike(term)
        )
    if role is not None:
        query = query.filter(User.role == role)
    if is_active is not None:
        query = query.filter(User.is_active.is_(is_active))
    total = query.count()
    users = query.order_by(User.created_at.desc(), User.id.desc()).offset(skip).limit(limit).all()
    return {
        "items": [{
            "id": u.id,
            "full_name": u.full_name,
            "username": u.username,
            "email": u.email,
            "role": u.role.value,
            "is_active": u.is_active,
            "email_verified": u.email_verified,
            "created_at": u.created_at,
            "has_lecturer_profile": lecturer_profile_id is not None,
            "academic_status": academic_status or "not_submitted",
            "academic_department_id": academic_department_id,
        } for u, lecturer_profile_id, academic_status, academic_department_id in users],
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.put("/members/{member_id}/role")
def update_member_role(
    member_id: int,
    data: MemberRoleUpdate,
    db: Session = Depends(get_db),
    admin: User = AdminUser,
):
    member = db.get(User, member_id)
    if not member or member.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Member not found.")
    if member.role == UserRole.ADMINISTRATOR or data.role == UserRole.ADMINISTRATOR:
        raise HTTPException(
            status_code=403,
            detail="Administrator role changes require the operator bootstrap process.",
        )
    if data.role == UserRole.LECTURER and not db.scalar(
        select(LecturerProfile).where(LecturerProfile.user_id == member.id)
    ):
        raise HTTPException(
            status_code=409,
            detail="Create a lecturer profile through lecturer invitations before assigning lecturer access.",
        )
    if data.role == UserRole.DEPARTMENT_REVIEWER:
        affiliation = db.scalar(
            select(AcademicAffiliation).where(AcademicAffiliation.user_id == member.id)
        )
        if not affiliation or affiliation.status != "verified":
            raise HTTPException(
                status_code=409,
                detail="Verify the member's academic affiliation before assigning reviewer access.",
            )
    previous_role = member.role.value
    member.role = data.role
    if previous_role == UserRole.DEPARTMENT_REVIEWER.value and data.role != UserRole.DEPARTMENT_REVIEWER:
        db.query(ReviewerAssignment).filter_by(user_id=member.id, active=True).update(
            {"active": False}, synchronize_session=False
        )
    db.execute(
        update(UserSession)
        .where(UserSession.user_id == member.id, UserSession.revoked_at.is_(None))
        .values(revoked_at=utc_now())
    )
    audit(
        db, admin, "member.role.updated", "user", member.id,
        f"role={previous_role}->{data.role.value}; active sessions revoked",
    )
    db.commit()
    return {"message": "Member role updated. They must sign in again.", "role": data.role.value}


@router.post("/members/{member_id}/suspend")
def suspend_member(
    member_id: int,
    data: MemberSuspendRequest,
    db: Session = Depends(get_db),
    admin: User = AdminUser,
):
    member = db.get(User, member_id)
    if not member or member.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Member not found.")
    if member.id == admin.id:
        raise HTTPException(status_code=409, detail="You cannot suspend your own administrator account.")
    if member.role == UserRole.ADMINISTRATOR:
        raise HTTPException(status_code=409, detail="Administrator accounts cannot be suspended here.")
    member.is_active = False
    db.execute(
        update(UserSession)
        .where(UserSession.user_id == member.id, UserSession.revoked_at.is_(None))
        .values(revoked_at=utc_now())
    )
    audit(
        db, admin, "member.suspended", "user", member.id,
        f"reason={data.reason.strip()}; sessions revoked; account data retained",
    )
    db.commit()
    return {"message": "Member access disabled; account records and audit history were retained."}


@router.post("/members/{member_id}/reactivate")
def reactivate_member(
    member_id: int,
    db: Session = Depends(get_db),
    admin: User = AdminUser,
):
    member = db.get(User, member_id)
    if not member or member.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Member not found.")
    if member.role == UserRole.ADMINISTRATOR:
        raise HTTPException(status_code=409, detail="Administrator accounts cannot be reactivated here.")
    member.is_active = True
    audit(db, admin, "member.reactivated", "user", member.id, "account access restored")
    db.commit()
    return {"message": "Member reactivated."}


@router.delete("/members/{member_id}")
def delete_member(
    member_id: int,
    db: Session = Depends(get_db),
    admin: User = AdminUser,
):
    member = db.get(User, member_id)
    if not member or member.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Member not found.")
    if member.id == admin.id or member.role == UserRole.ADMINISTRATOR:
        raise HTTPException(status_code=409, detail="Administrator accounts cannot be deleted here.")

    lecturer_profile = db.scalar(select(LecturerProfile).where(LecturerProfile.user_id == member.id))
    if lecturer_profile:
        db.query(LecturerCourseAssignment).filter_by(
            lecturer_profile_id=lecturer_profile.id
        ).delete(synchronize_session=False)
        db.delete(lecturer_profile)

    chat_session_ids = select(ChatSession.id).where(ChatSession.user_id == member.id)
    db.query(ChatMessage).filter(ChatMessage.session_id.in_(chat_session_ids)).delete(synchronize_session=False)
    db.query(ChatSession).filter(ChatSession.user_id == member.id).delete(synchronize_session=False)
    db.query(AuthToken).filter(AuthToken.user_id == member.id).delete(synchronize_session=False)
    db.query(UserSession).filter(UserSession.user_id == member.id).delete(synchronize_session=False)
    db.query(StudentProfile).filter(StudentProfile.user_id == member.id).delete(synchronize_session=False)
    db.query(AcademicAffiliation).filter(AcademicAffiliation.user_id == member.id).delete(synchronize_session=False)
    db.query(ProfileChangeRequest).filter(ProfileChangeRequest.user_id == member.id).delete(synchronize_session=False)
    db.query(StudentProgress).filter(StudentProgress.student_id == member.id).delete(synchronize_session=False)
    db.query(DocumentPermission).filter(DocumentPermission.user_id == member.id).delete(synchronize_session=False)
    db.query(ReviewerAssignment).filter(ReviewerAssignment.user_id == member.id).update(
        {"active": False}, synchronize_session=False
    )

    member.full_name = "Deleted account"
    member.email = f"deleted-{member.id}@deleted.invalid"
    member.username = None
    member.password_hash = hash_password(secrets.token_urlsafe(48))
    member.email_verified = False
    member.is_active = False
    member.deleted_at = utc_now()
    audit(
        db, admin, "member.account.deleted", "user", member.id,
        "Account identity removed and email released; uploaded documents and audit history retained.",
    )
    db.commit()
    return {"message": "Account identity removed and email released. Documents and audit history were retained with anonymized attribution."}


@router.get("/profile-change-requests")
def list_profile_change_requests(
    db: Session = Depends(get_db),
    _admin: User = AdminUser,
):
    rows = db.query(ProfileChangeRequest).order_by(ProfileChangeRequest.created_at.desc()).all()
    return {"items": [{
        "id": r.id,
        "user_id": r.user_id,
        "field_name": r.field_name,
        "requested_value": r.requested_value,
        "status": r.status,
        "reviewed_by_id": r.reviewed_by_id,
        "created_at": r.created_at,
    } for r in rows]}


@router.post("/profile-change-requests/{request_id}/approve")
def approve_profile_change_request(
    request_id: int,
    db: Session = Depends(get_db),
    admin: User = AdminUser,
):
    request_row = db.get(ProfileChangeRequest, request_id)
    if not request_row or request_row.status != "pending":
        raise HTTPException(status_code=404, detail="Pending profile change request not found.")
    lecturer = db.get(User, request_row.user_id)
    profile = db.scalar(select(LecturerProfile).where(LecturerProfile.user_id == request_row.user_id))
    if not lecturer or not profile:
        raise HTTPException(status_code=404, detail="Lecturer profile not found.")
    if request_row.field_name == "full_name":
        lecturer.full_name = request_row.requested_value
    elif request_row.field_name == "staff_number":
        profile.staff_number = request_row.requested_value
    elif request_row.field_name == "department_id":
        try:
            department_id = int(request_row.requested_value)
        except ValueError:
            raise HTTPException(status_code=422, detail="Requested department ID is invalid.")
        if not db.get(Department, department_id):
            raise HTTPException(status_code=404, detail="Requested department not found.")
        profile.department_id = department_id
    elif request_row.field_name == "course_assignments":
        raise HTTPException(status_code=422, detail="Course assignment changes must use the course assignment endpoint.")
    request_row.status = "approved"
    request_row.reviewed_by_id = admin.id
    audit(db, admin, "lecturer.profile_change.approved", "profile_change_request", request_row.id,
          f"field={request_row.field_name}")
    db.commit()
    return {"message": "Profile change request approved."}


@router.post("/profile-change-requests/{request_id}/reject")
def reject_profile_change_request(
    request_id: int,
    db: Session = Depends(get_db),
    admin: User = AdminUser,
):
    request_row = db.get(ProfileChangeRequest, request_id)
    if not request_row or request_row.status != "pending":
        raise HTTPException(status_code=404, detail="Pending profile change request not found.")
    request_row.status = "rejected"
    request_row.reviewed_by_id = admin.id
    audit(db, admin, "lecturer.profile_change.rejected", "profile_change_request", request_row.id,
          f"field={request_row.field_name}")
    db.commit()
    return {"message": "Profile change request rejected."}
