from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.auth import get_current_user, token_hash, utc_now
from app.api.dependencies import require_roles
from app.core.database import get_db
from app.core.security import hash_password
from app.core.email_validation import validate_password
from app.models import (
    AuditLog, AuthToken, LecturerCourseAssignment, LecturerProfile,
    ProfileChangeRequest, User, UserRole, UserSession,
)

router = APIRouter(prefix="/api/lecturers", tags=["Lecturers"])
LecturerUser = Depends(require_roles(UserRole.LECTURER))


class LecturerActivate(BaseModel):
    token: str = Field(min_length=20, max_length=512)
    password: str = Field(min_length=8, max_length=128)


class LecturerProfileUpdate(BaseModel):
    phone: str | None = Field(default=None, max_length=30)
    biography: str | None = Field(default=None, max_length=5000)
    qualifications: str | None = Field(default=None, max_length=5000)
    office_location: str | None = Field(default=None, max_length=500)


class ProfileRequest(BaseModel):
    field_name: str = Field(pattern="^(full_name|staff_number|department_id|course_assignments)$")
    requested_value: str = Field(min_length=1, max_length=2000)


def lecturer_audit(db: Session, user: User, action: str, details: str) -> None:
    db.add(AuditLog(user_id=user.id, action=action, entity_type="lecturer_profile", entity_id=user.id, details=details))


@router.post("/activate")
def activate_lecturer(data: LecturerActivate, db: Session = Depends(get_db)):
    try:
        validate_password(data.password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    record = db.scalar(select(AuthToken).where(
        AuthToken.purpose == "lecturer_invite",
        AuthToken.token_hash == token_hash(data.token),
    ))
    if not record or record.used_at is not None:
        raise HTTPException(status_code=400, detail="Invalid or already-used invitation.")
    if record.expires_at <= utc_now():
        raise HTTPException(status_code=410, detail="Lecturer invitation has expired.")
    user = db.get(User, record.user_id)
    if not user or user.role != UserRole.LECTURER:
        raise HTTPException(status_code=400, detail="Invalid lecturer invitation.")
    user.password_hash = hash_password(data.password)
    user.email_verified = True
    user.is_active = True
    record.used_at = utc_now()
    db.execute(update(AuthToken).where(
        AuthToken.user_id == user.id,
        AuthToken.purpose == "lecturer_invite",
        AuthToken.used_at.is_(None),
    ).values(used_at=utc_now()))
    profile = db.scalar(select(LecturerProfile).where(LecturerProfile.user_id == user.id))
    if profile:
        profile.invitation_status = "accepted"
    lecturer_audit(db, user, "lecturer.account.activated", "invitation accepted; password set")
    db.commit()
    return {"message": "Lecturer account activated. You can now sign in."}


@router.get("/me")
def lecturer_profile(
    db: Session = Depends(get_db),
    user: User = LecturerUser,
):
    profile = db.scalar(select(LecturerProfile).where(LecturerProfile.user_id == user.id))
    if not profile:
        raise HTTPException(status_code=404, detail="Lecturer profile not found.")
    assignments = db.query(LecturerCourseAssignment).filter_by(lecturer_profile_id=profile.id).all()
    course_ids = [assignment.course_id for assignment in assignments]
    return {
        "lecturer_id": profile.lecturer_id,
        "official_name": user.full_name,
        "staff_number": profile.staff_number,
        "username": user.username,
        "email": user.email,
        "phone": profile.phone,
        "department_id": profile.department_id,
        "title": profile.title,
        "biography": profile.biography,
        "qualifications": profile.qualifications,
        "office_location": profile.office_location,
        "assigned_course_ids": course_ids,
        "email_verified": user.email_verified,
        "is_active": user.is_active,
        "invitation_status": profile.invitation_status,
    }


@router.put("/me")
def update_lecturer_profile(
    data: LecturerProfileUpdate,
    db: Session = Depends(get_db),
    user: User = LecturerUser,
):
    profile = db.scalar(select(LecturerProfile).where(LecturerProfile.user_id == user.id))
    if not profile:
        raise HTTPException(status_code=404, detail="Lecturer profile not found.")
    before = {
        "phone": profile.phone,
        "biography": profile.biography,
        "qualifications": profile.qualifications,
        "office_location": profile.office_location,
    }
    profile.phone = data.phone.strip() if data.phone else None
    profile.biography = data.biography.strip() if data.biography else None
    profile.qualifications = data.qualifications.strip() if data.qualifications else None
    profile.office_location = data.office_location.strip() if data.office_location else None
    after = {
        "phone": profile.phone,
        "biography": profile.biography,
        "qualifications": profile.qualifications,
        "office_location": profile.office_location,
    }
    changed_fields = [field for field in before if before[field] != after[field]]
    lecturer_audit(db, user, "lecturer.profile.updated", f"fields={','.join(changed_fields)}")
    db.commit()
    return {"message": "Lecturer profile updated."}


@router.post("/change-request", status_code=201)
def request_profile_change(
    data: ProfileRequest,
    db: Session = Depends(get_db),
    user: User = LecturerUser,
):
    db.add(ProfileChangeRequest(
        user_id=user.id,
        field_name=data.field_name,
        requested_value=data.requested_value.strip(),
        status="pending",
        created_at=utc_now(),
    ))
    lecturer_audit(db, user, "lecturer.profile_change.requested",
                   f"field={data.field_name}; status=pending")
    db.commit()
    return {"message": "Change request submitted for administrator approval."}


@router.get("/sessions")
def list_sessions(
    db: Session = Depends(get_db),
    user: User = LecturerUser,
):
    rows = db.query(UserSession).filter(
        UserSession.user_id == user.id,
        UserSession.revoked_at.is_(None),
        UserSession.expires_at > utc_now(),
    ).order_by(UserSession.created_at.desc()).all()
    return {"items": [{
        "id": r.id,
        "created_at": r.created_at,
        "expires_at": r.expires_at,
        "last_seen_at": r.last_seen_at,
    } for r in rows]}


@router.post("/sessions/{session_id}/revoke")
def revoke_session(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = LecturerUser,
):
    record = db.get(UserSession, session_id)
    if not record or record.user_id != user.id:
        raise HTTPException(status_code=404, detail="Session not found.")
    record.revoked_at = utc_now()
    lecturer_audit(db, user, "lecturer.session.revoked", f"session_id={session_id}")
    db.commit()
    return {"message": "Session revoked."}
