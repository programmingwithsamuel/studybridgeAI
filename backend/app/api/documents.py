from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.auth import get_current_user
from app.api.dependencies import require_roles
from app.core.database import get_db
from app.models import (
    AcademicAffiliation, AuditLog, Course, Department, Document, DocumentPermission,
    DocumentStatus, DocumentVersion, DocumentVisibility, Faculty, LecturerCourseAssignment,
    LecturerProfile, PermissionLevel, Programme, ProgrammeCourse, ReviewerAssignment,
    ReviewAction, ReviewDecision,
    University, User, UserRole,
)
from app.schemas.document import DocumentResponse, ReviewDecisionResponse
from app.services.document_indexing import process_approved_document, remove_document_from_index
from app.services.document_storage import save_pdf

router = APIRouter(prefix="/api/documents", tags=["Documents"])
REVIEWER_ROLES = (UserRole.DEPARTMENT_REVIEWER, UserRole.ADMINISTRATOR)
UPLOAD_ROLES = (UserRole.LECTURER,)


def _audit(db: Session, user: User, action: str, document: Document, details: str | None = None):
    db.add(AuditLog(user_id=user.id, action=action, entity_type="document", entity_id=document.id, details=details))


def _get_document(db: Session, document_id: int) -> Document:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return document


def _verified_affiliation(db: Session, user: User) -> AcademicAffiliation | None:
    return db.scalar(
        select(AcademicAffiliation).where(
            AcademicAffiliation.user_id == user.id,
            AcademicAffiliation.status == "verified",
        )
    )


def _has_reviewer_scope(db: Session, document: Document, user: User) -> bool:
    if user.role != UserRole.DEPARTMENT_REVIEWER or document.course_id is None:
        return False
    affiliation = _verified_affiliation(db, user)
    if affiliation is None:
        return False
    course = db.get(Course, document.course_id)
    if course is None or course.department_id != affiliation.department_id:
        return False
    return db.scalar(
        select(ReviewerAssignment.id).where(
            ReviewerAssignment.user_id == user.id,
            ReviewerAssignment.active.is_(True),
            (
                (ReviewerAssignment.course_id == course.id)
                | (
                    (ReviewerAssignment.course_id.is_(None))
                    & (ReviewerAssignment.department_id == course.department_id)
                )
            ),
        ).limit(1)
    ) is not None


def _can_review(db: Session, document: Document, user: User) -> bool:
    if document.uploaded_by_id == user.id:
        return False
    if user.role == UserRole.ADMINISTRATOR:
        return True
    return _has_reviewer_scope(db, document, user)


def _academic_scope_rank(
    db: Session,
    document: Document,
    user: User,
    affiliation: AcademicAffiliation | None = None,
) -> int:
    if document.course_id is None:
        return 0
    affiliation = affiliation or _verified_affiliation(db, user)
    if affiliation is None:
        return 0

    course = db.get(Course, document.course_id)
    if course is None:
        return 0
    department = db.get(Department, course.department_id)
    student_department = db.get(Department, affiliation.department_id)
    if department is None or student_department is None:
        return 0
    faculty = db.get(Faculty, department.faculty_id)
    student_faculty = db.get(Faculty, student_department.faculty_id)
    if faculty is None or student_faculty is None:
        return 0
    university = db.get(University, faculty.university_id)
    student_university = db.get(University, student_faculty.university_id)
    if university is None or student_university is None:
        return 0

    if user.role == UserRole.STUDENT and course.level:
        if _normalized_level(course.level) != _normalized_level(affiliation.level):
            return 0

    visibility = document.visibility
    if visibility == DocumentVisibility.COURSE.value:
        if user.role == UserRole.STUDENT:
            if affiliation.department_id != course.department_id or affiliation.programme_id is None:
                return 0
            programme = db.get(Programme, affiliation.programme_id)
            if programme is None or programme.department_id != affiliation.department_id:
                return 0
            enrolled = db.scalar(
                select(ProgrammeCourse.id).where(
                    ProgrammeCourse.programme_id == programme.id,
                    ProgrammeCourse.course_id == course.id,
                ).limit(1)
            )
            return 4 if enrolled is not None else 0
        if user.role == UserRole.LECTURER:
            profile = db.scalar(
                select(LecturerProfile).where(LecturerProfile.user_id == user.id)
            )
            if profile is None or profile.department_id != course.department_id:
                return 0
            assigned = db.scalar(
                select(LecturerCourseAssignment.course_id).where(
                    LecturerCourseAssignment.lecturer_profile_id == profile.id,
                    LecturerCourseAssignment.course_id == course.id,
                ).limit(1)
            )
            return 4 if assigned is not None else 0
        return 0

    if visibility == DocumentVisibility.DEPARTMENT.value:
        return 3 if affiliation.department_id == course.department_id else 0
    if visibility == DocumentVisibility.FACULTY.value:
        return 2 if student_faculty.id == faculty.id else 0
    if visibility == DocumentVisibility.UNIVERSITY.value:
        return 1 if student_university.id == university.id else 0
    return 0


def _can_view(db: Session, document: Document, user: User) -> bool:
    if user.role == UserRole.ADMINISTRATOR or document.uploaded_by_id == user.id:
        return True
    if _can_review(db, document, user):
        return True
    if document.withdrawn_at is not None or document.status != DocumentStatus.VERIFIED:
        return False
    permission = db.scalar(
        select(DocumentPermission).where(
            DocumentPermission.document_id == document.id,
            DocumentPermission.user_id == user.id,
        ).limit(1)
    )
    if permission is not None:
        return True
    return _academic_scope_rank(db, document, user) > 0


def _normalized_level(value: str | None) -> str:
    if not value:
        return ""
    return "".join(character for character in value.casefold().replace("level", "") if character.isalnum())


def _can_download(db: Session, document: Document, user: User) -> bool:
    if not _can_view(db, document, user):
        return False
    if (
        user.role == UserRole.ADMINISTRATOR
        or document.uploaded_by_id == user.id
        or _can_review(db, document, user)
    ):
        return True
    permission = db.scalar(
        select(DocumentPermission).where(
            DocumentPermission.document_id == document.id,
            DocumentPermission.user_id == user.id,
        ).limit(1)
    )
    if permission is not None:
        return permission.permission in (PermissionLevel.DOWNLOAD, PermissionLevel.EDIT)
    return document.status == DocumentStatus.VERIFIED and document.withdrawn_at is None


@router.post("/upload", response_model=DocumentResponse, status_code=201)
async def upload_document(
    title: str = Form(min_length=2, max_length=200),
    description: str | None = Form(default=None),
    course_id: int = Form(...),
    visibility: DocumentVisibility = Form(DocumentVisibility.COURSE),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*UPLOAD_ROLES)),
):
    affiliation = _verified_affiliation(db, current_user)
    if affiliation is None:
        raise HTTPException(status_code=403, detail="Verify your academic affiliation before uploading documents.")
    course = db.get(Course, course_id)
    if course is None:
        await file.close()
        raise HTTPException(status_code=404, detail="Course not found.")
    if current_user.role == UserRole.LECTURER:
        profile = db.query(LecturerProfile).filter_by(user_id=current_user.id).first()
        if not profile or profile.department_id != course.department_id:
            await file.close()
            raise HTTPException(status_code=403, detail="You may upload only to courses in your verified department.")
        assignment = (
            db.query(LecturerCourseAssignment)
            .filter_by(lecturer_profile_id=profile.id, course_id=course_id)
            .first()
            if profile else None
        )
        if not assignment:
            await file.close()
            raise HTTPException(status_code=403, detail="You may upload only to courses assigned to you.")
    try:
        file_data = await save_pdf(file)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    document = Document(
        title=title.strip(), description=description.strip() if description else None,
        original_filename=file_data["original_filename"], storage_path=file_data["storage_path"],
        sha256=file_data["sha256"], file_size=file_data["file_size"], page_count=file_data["page_count"],
        uploaded_by_id=current_user.id, course_id=course_id, visibility=visibility.value,
        status=DocumentStatus.DRAFT if current_user.role == UserRole.STUDENT else DocumentStatus.PENDING_REVIEW,
    )
    db.add(document)
    try:
        db.flush()
        _audit(db, current_user, "document.uploaded", document)
        db.commit()
        db.refresh(document)
    except Exception:
        db.rollback()
        Path(file_data["storage_path"]).unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="Could not save document information.")
    return document


@router.get("/mine", response_model=list[DocumentResponse])
def list_my_documents(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.role == UserRole.STUDENT:
        return []
    return db.query(Document).filter(Document.uploaded_by_id == current_user.id).order_by(Document.created_at.desc()).all()


@router.get("/published", response_model=list[DocumentResponse])
def list_published_documents(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    statement = (
        select(Document)
        .options(selectinload(Document.course).selectinload(Course.department))
        .where(
            Document.status == DocumentStatus.VERIFIED,
            Document.withdrawn_at.is_(None),
        )
    )
    affiliation = _verified_affiliation(db, current_user) if current_user.role == UserRole.STUDENT else None
    if current_user.role == UserRole.STUDENT:
        if affiliation is None:
            raise HTTPException(status_code=403, detail="Verify your academic affiliation to browse approved materials.")
    statement = statement.order_by(Document.updated_at.desc())
    documents = [
        document
        for document in db.scalars(statement).all()
        if _can_view(db, document, current_user)
    ]
    documents.sort(
        key=lambda document: (
            _academic_scope_rank(db, document, current_user, affiliation)
            if current_user.role == UserRole.STUDENT else 0,
            document.updated_at,
        ),
        reverse=True,
    )
    result = []
    for document in documents:
        relevance_rank = (
            _academic_scope_rank(db, document, current_user, affiliation)
            if current_user.role == UserRole.STUDENT else 0
        )
        relevance = {
            4: "Your enrolled course",
            3: "Your department",
            2: "Your faculty",
            1: "Your university",
            0: "Shared with you",
        }[relevance_rank]
        item = DocumentResponse.model_validate(document).model_dump()
        item["relevance"] = relevance
        result.append(item)
    return result


@router.get("/review-queue", response_model=list[DocumentResponse])
def review_queue(db: Session = Depends(get_db), current_user: User = Depends(require_roles(*REVIEWER_ROLES))):
    documents = db.query(Document).filter(Document.status == DocumentStatus.PENDING_REVIEW).order_by(Document.created_at.asc()).all()
    if current_user.role == UserRole.ADMINISTRATOR:
        return documents
    return [document for document in documents if _can_review(db, document, current_user)]


@router.get("/{document_id}", response_model=DocumentResponse)
def document_details(document_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    document = _get_document(db, document_id)
    if not _can_view(db, document, current_user):
        raise HTTPException(status_code=403, detail="You do not have access to this document.")
    return document


@router.post("/{document_id}/submit", response_model=DocumentResponse)
def submit_for_review(document_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_roles(*UPLOAD_ROLES))):
    if _verified_affiliation(db, current_user) is None:
        raise HTTPException(status_code=403, detail="Verify your academic affiliation before submitting documents.")
    document = _get_document(db, document_id)
    if document.uploaded_by_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only submit your own documents.")
    if document.status not in (DocumentStatus.DRAFT, DocumentStatus.REJECTED):
        raise HTTPException(status_code=409, detail="This document cannot be submitted in its current status.")
    document.status = DocumentStatus.PENDING_REVIEW
    _audit(db, current_user, "document.submitted_for_review", document)
    db.commit(); db.refresh(document)
    return document


@router.post("/{document_id}/review", response_model=ReviewDecisionResponse)
def review_document(
    document_id: int,
    background_tasks: BackgroundTasks,
    action: ReviewAction = Form(...),
    comments: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REVIEWER_ROLES)),
):
    document = _get_document(db, document_id)
    if document.status != DocumentStatus.PENDING_REVIEW:
        raise HTTPException(status_code=409, detail="Only pending documents can be reviewed.")
    if not _can_review(db, document, current_user):
        raise HTTPException(status_code=403, detail="You are not assigned to review this document, or cannot review your own upload.")
    if action in (ReviewAction.REJECT, ReviewAction.REQUEST_CORRECTION) and not (comments and comments.strip()):
        raise HTTPException(status_code=422, detail="Comments are required when rejecting or requesting corrections.")
    decision = ReviewDecision(document_id=document.id, reviewer_id=current_user.id, action=action, comments=comments.strip() if comments else None)
    if action == ReviewAction.APPROVE:
        document.status = DocumentStatus.VERIFIED
    elif action == ReviewAction.REJECT:
        document.status = DocumentStatus.REJECTED
    else:
        document.status = DocumentStatus.DRAFT
    db.add(decision)
    _audit(db, current_user, f"document.review.{action.value}", document, decision.comments)
    db.commit(); db.refresh(decision)
    if action == ReviewAction.APPROVE:
        background_tasks.add_task(process_approved_document, document.id)
    return decision


@router.get("/{document_id}/reviews", response_model=list[ReviewDecisionResponse])
def review_history(document_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    document = _get_document(db, document_id)
    if not _can_view(db, document, current_user):
        raise HTTPException(status_code=403, detail="You do not have access to this document.")
    return db.query(ReviewDecision).filter_by(document_id=document.id).order_by(ReviewDecision.created_at.desc()).all()


@router.post("/{document_id}/permissions", status_code=201)
def grant_permission(
    document_id: int,
    user_id: int = Form(...),
    permission: PermissionLevel = Form(PermissionLevel.VIEW),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REVIEWER_ROLES)),
):
    document = _get_document(db, document_id)
    if current_user.role != UserRole.ADMINISTRATOR and not _can_review(db, document, current_user):
        raise HTTPException(status_code=403, detail="You are not assigned to this document's academic scope.")
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found.")
    existing = db.query(DocumentPermission).filter_by(document_id=document.id, user_id=user_id).first()
    if existing:
        existing.permission = permission
        existing.granted_by_id = current_user.id
        record = existing
    else:
        record = DocumentPermission(document_id=document.id, user_id=user_id, permission=permission, granted_by_id=current_user.id)
        db.add(record)
    _audit(db, current_user, "document.permission.granted", document, f"user_id={user_id}; permission={permission.value}")
    db.commit()
    return {"message": "Permission saved.", "document_id": document.id, "user_id": user_id, "permission": permission.value}


@router.get("/{document_id}/download")
def download_document(document_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    document = _get_document(db, document_id)
    if not _can_download(db, document, current_user):
        raise HTTPException(status_code=403, detail="You do not have permission to download this document.")
    path = Path(document.storage_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Stored document file is missing.")
    _audit(db, current_user, "document.downloaded", document)
    db.commit()
    return FileResponse(path, media_type="application/pdf", filename=document.original_filename)


@router.delete("/{document_id}")
def withdraw_document(
    document_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    document = _get_document(db, document_id)
    is_owner = document.uploaded_by_id == current_user.id
    is_admin = current_user.role == UserRole.ADMINISTRATOR
    if not (is_owner or is_admin or _can_review(db, document, current_user)):
        raise HTTPException(status_code=403, detail="You may not withdraw this document.")
    if document.withdrawn_at is not None:
        raise HTTPException(status_code=409, detail="Document is already withdrawn.")
    document.withdrawn_at = datetime.now(timezone.utc)
    _audit(db, current_user, "document.withdrawn", document, "Removed from active document and AI retrieval.")
    db.commit()
    background_tasks.add_task(remove_document_from_index, document.id)
    return {"message": "Document withdrawn from active access and AI retrieval. The stored PDF was retained."}


@router.post("/{document_id}/versions", response_model=DocumentResponse, status_code=201)
async def upload_new_version(document_id: int, file: UploadFile = File(...), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    document = _get_document(db, document_id)
    if current_user.role not in UPLOAD_ROLES and current_user.role not in REVIEWER_ROLES:
        await file.close()
        raise HTTPException(status_code=403, detail="Your account cannot upload document versions.")
    if document.uploaded_by_id != current_user.id and current_user.role not in REVIEWER_ROLES:
        raise HTTPException(status_code=403, detail="You cannot create a version of this document.")
    if current_user.role == UserRole.DEPARTMENT_REVIEWER and not _can_review(db, document, current_user):
        await file.close()
        raise HTTPException(status_code=403, detail="You are not assigned to this document's academic scope.")
    if current_user.role == UserRole.LECTURER and _verified_affiliation(db, current_user) is None:
        await file.close()
        raise HTTPException(status_code=403, detail="Verify your academic affiliation before uploading versions.")
    if current_user.role == UserRole.LECTURER and document.course_id is not None:
        profile = db.query(LecturerProfile).filter_by(user_id=current_user.id).first()
        assignment = (
            db.query(LecturerCourseAssignment)
            .filter_by(lecturer_profile_id=profile.id, course_id=document.course_id)
            .first()
            if profile else None
        )
        if not assignment:
            await file.close()
            raise HTTPException(status_code=403, detail="You may create versions only for courses assigned to you.")
    try:
        data = await save_pdf(file)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    previous_versions = db.query(DocumentVersion).filter_by(document_id=document.id).count()
    db.add(DocumentVersion(document_id=document.id, version_number=previous_versions + 1, storage_path=document.storage_path, sha256=document.sha256, file_size=document.file_size, uploaded_by_id=current_user.id))
    document.storage_path = data["storage_path"]
    document.sha256 = data["sha256"]
    document.file_size = data["file_size"]
    document.page_count = data["page_count"]
    document.original_filename = data["original_filename"]
    document.status = DocumentStatus.PENDING_REVIEW
    _audit(db, current_user, "document.version.uploaded", document, f"version={previous_versions + 1}")
    try:
        db.commit(); db.refresh(document)
    except Exception:
        db.rollback(); Path(data["storage_path"]).unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="Could not save document version.")
    return document
