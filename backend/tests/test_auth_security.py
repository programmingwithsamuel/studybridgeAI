import socket
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
import pymupdf
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import Base, get_db
from app.core.security import hash_password
from app.main import app
from app.services import document_storage
from app.models import (
    AcademicAffiliation, AuthToken, Course, Department, Document, DocumentStatus,
    DocumentVisibility, Faculty, LecturerCourseAssignment, LecturerProfile, Programme,
    ProgrammeCourse,
    ReviewerAssignment, University, User, UserRole,
)
import app.api.auth as auth_api


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture(autouse=True)
def reset_database(monkeypatch):
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(auth_api.settings, "EMAIL_MODE", "console")
    monkeypatch.setattr(auth_api, "send_email", lambda *args, **kwargs: None)
    auth_api._rate_entries.clear()
    yield
    Base.metadata.drop_all(bind=engine)


def override_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_db
client = TestClient(app)


def create_user(email="existing@example.com", verified=True, password="Existing123!", role=UserRole.STUDENT):
    db = TestingSessionLocal()
    user = User(
        full_name="Existing Student",
        email=email,
        password_hash=hash_password(password),
        role=role,
        email_verified=verified,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    db.close()
    return user


def create_academic_scope(db, suffix="A", course_level="100 Level"):
    university = University(name=f"University {suffix}")
    db.add(university)
    db.flush()
    faculty = Faculty(name=f"Faculty {suffix}", university_id=university.id)
    db.add(faculty)
    db.flush()
    department = Department(name=f"Department {suffix}", faculty_id=faculty.id)
    db.add(department)
    db.flush()
    programme = Programme(
        name=f"Programme {suffix}",
        code=f"PRG-{suffix}",
        department_id=department.id,
        level="100 Level",
        university_id=university.id,
    )
    course = Course(
        code=f"CRS-{suffix}",
        title=f"Course {suffix}",
        level=course_level,
        department_id=department.id,
    )
    db.add_all([programme, course])
    db.flush()
    return university, faculty, department, programme, course


def test_valid_registration_and_unverified_login():
    response = client.post("/api/auth/register", json={
        "full_name": "Valid Student",
        "email": "student@example.com",
        "password": "StudyBridge123!",
    })
    assert response.status_code == 201
    assert response.json()["email_verified"] is False
    assert response.json()["development_verification_url"].startswith("http://localhost:5173/verify-email?token=")

    login = client.post("/api/auth/login", json={
        "email": "student@example.com",
        "password": "StudyBridge123!",
    })
    assert login.status_code == 403


@pytest.mark.parametrize("email", ["not-an-email", "x@", "@example.com", "x@bad_domain.com"])
def test_invalid_email_syntax(email):
    response = client.post("/api/auth/register", json={
        "full_name": "Invalid Student",
        "email": email,
        "password": "StudyBridge123!",
    })
    assert response.status_code == 422


def test_common_typo_suggestion():
    response = client.post("/api/auth/register", json={
        "full_name": "Typo Student",
        "email": "student@gmial.com",
        "password": "StudyBridge123!",
    })
    assert response.status_code == 422
    assert response.json()["detail"]["suggested_email"] == "student@gmail.com"


def test_email_check_and_login_do_not_wait_for_dns(monkeypatch):
    def fail_if_dns_is_used(*args, **kwargs):
        raise AssertionError("Email validation should not perform DNS lookups.")

    monkeypatch.setattr(socket, "getaddrinfo", fail_if_dns_is_used)
    checked = client.post("/api/auth/email/check", json={"email": "existing@example.com"})
    assert checked.status_code == 200
    assert checked.json()["dns_reachable"] is None

    create_user()
    login = client.post("/api/auth/login", json={
        "email": "existing@example.com",
        "password": "Existing123!",
    })
    assert login.status_code == 200


def test_duplicate_email():
    create_user(email="duplicate@example.com")
    response = client.post("/api/auth/register", json={
        "full_name": "Duplicate Student",
        "email": "duplicate@example.com",
        "password": "StudyBridge123!",
    })
    assert response.status_code == 409


def test_successful_verification():
    registration = client.post("/api/auth/register", json={
        "full_name": "Verify Student",
        "email": "verify@example.com",
        "password": "StudyBridge123!",
    })
    link = registration.json()["development_verification_url"]
    token = parse_qs(urlparse(link).query)["token"][0]

    response = client.get("/api/auth/verify-email", params={"token": token})
    assert response.status_code == 200


def test_expired_verification_token():
    user = create_user(email="expiredverify@example.com", verified=False)
    db = TestingSessionLocal()
    token = "expired-verification-token-value"
    db.add(AuthToken(
        user_id=user.id,
        purpose="verify_email",
        token_hash=auth_api.token_hash(token),
        expires_at=datetime.utcnow() - timedelta(minutes=1),
    ))
    db.commit()
    db.close()
    response = client.get("/api/auth/verify-email", params={"token": token})
    assert response.status_code == 410


def test_invalid_verification_token():
    response = client.get("/api/auth/verify-email", params={"token": "invalid-verification-token-value"})
    assert response.status_code == 400


def test_resend_verification():
    create_user(email="resend@example.com", verified=False)
    response = client.post("/api/auth/verification/resend", json={"email": "resend@example.com"})
    assert response.status_code == 200
    assert response.json()["development_verification_url"].startswith("http://localhost:5173/verify-email?token=")


def test_forgot_password_existing_and_unknown_are_generic():
    create_user(email="forgot@example.com")
    existing = client.post("/api/auth/forgot-password", json={"email": "forgot@example.com"})
    unknown = client.post("/api/auth/forgot-password", json={"email": "unknown@example.com"})
    assert existing.status_code == 200
    assert unknown.status_code == 200
    assert existing.json()["message"] == unknown.json()["message"]


def test_reset_valid_expired_and_reused():
    user = create_user(email="reset@example.com")
    db = TestingSessionLocal()
    token = "valid-password-reset-token-value"
    db.add(AuthToken(
        user_id=user.id,
        purpose="password_reset",
        token_hash=auth_api.token_hash(token),
        expires_at=datetime.utcnow() + timedelta(minutes=30),
    ))
    db.commit()
    db.close()

    reset = client.post("/api/auth/reset-password", json={"token": token, "password": "NewPassword123!"})
    assert reset.status_code == 200
    reuse = client.post("/api/auth/reset-password", json={"token": token, "password": "AnotherPassword123!"})
    assert reuse.status_code == 400

    login = client.post("/api/auth/login", json={"email": "reset@example.com", "password": "NewPassword123!"})
    assert login.status_code == 200


def test_expired_reset_token():
    user = create_user(email="expiredreset@example.com")
    db = TestingSessionLocal()
    token = "expired-password-reset-token-value"
    db.add(AuthToken(
        user_id=user.id,
        purpose="password_reset",
        token_hash=auth_api.token_hash(token),
        expires_at=datetime.utcnow() - timedelta(minutes=1),
    ))
    db.commit()
    db.close()
    response = client.post("/api/auth/reset-password", json={"token": token, "password": "NewPassword123!"})
    assert response.status_code == 410


def test_registration_rate_limit():
    for index in range(5):
        response = client.post("/api/auth/register", json={
            "full_name": f"Student {index}",
            "email": f"student{index}@example.com",
            "password": "StudyBridge123!",
        })
        assert response.status_code == 201
    limited = client.post("/api/auth/register", json={
        "full_name": "Student Limited",
        "email": "limited@example.com",
        "password": "StudyBridge123!",
    })
    assert limited.status_code == 429


def test_lecturer_and_admin_routes_reject_students():
    create_user(email="studentrole@example.com", verified=True)
    login = client.post("/api/auth/login", json={
        "email": "studentrole@example.com",
        "password": "Existing123!",
    })
    token = login.json()["access_token"]
    lecturer = client.get("/api/lecturers/me", headers={"Authorization": f"Bearer {token}"})
    admin = client.get("/api/admin/lecturers", headers={"Authorization": f"Bearer {token}"})
    assert lecturer.status_code == 403
    assert admin.status_code == 403


def test_successful_verification_is_then_allowed_to_login():
    registration = client.post("/api/auth/register", json={
        "full_name": "Login Verify Student",
        "email": "loginverify@example.com",
        "password": "StudyBridge123!",
    })
    link = registration.json()["development_verification_url"]
    token = parse_qs(urlparse(link).query)["token"][0]
    assert client.get("/api/auth/verify-email", params={"token": token}).status_code == 200
    login = client.post("/api/auth/login", json={
        "email": "loginverify@example.com",
        "password": "StudyBridge123!",
    })
    assert login.status_code == 200


def test_students_cannot_upload_and_only_published_documents_are_listed():
    student = create_user(email="reader@example.com")
    login = client.post("/api/auth/login", json={"email": student.email, "password": "Existing123!"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    upload = client.post(
        "/api/documents/upload",
        headers=headers,
        data={"title": "Student upload"},
        files={"file": ("sample.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert upload.status_code == 403

    db = TestingSessionLocal()
    _, faculty, department, programme, course = create_academic_scope(db, course_level="100")
    other_department = Department(name="Department A2", faculty_id=faculty.id)
    db.add(other_department)
    db.flush()
    same_faculty_course = Course(
        code="CRS-A2", title="Same faculty course", level="100 Level",
        department_id=other_department.id,
    )
    other_level_course = Course(
        code="CRS-A200", title="Other level course", level="200 Level",
        department_id=department.id,
    )
    department_course = Course(
        code="CRS-AD", title="Same department course", level="100 Level",
        department_id=department.id,
    )
    other_faculty = Faculty(name="Faculty A2", university_id=faculty.university_id)
    db.add(other_faculty)
    db.flush()
    university_department = Department(name="Department A3", faculty_id=other_faculty.id)
    db.add(university_department)
    db.add_all([same_faculty_course, other_level_course, department_course])
    db.flush()
    university_course = Course(
        code="CRS-A3", title="Same university course", level="100 Level",
        department_id=university_department.id,
    )
    _, _, other_faculty_department, _, other_faculty_course = create_academic_scope(db, suffix="B")
    db.add(university_course)
    db.flush()
    db.add(ProgrammeCourse(programme_id=programme.id, course_id=course.id))
    uploader = User(
        full_name="Published material uploader",
        email="published.material.uploader@example.com",
        password_hash=hash_password("Existing123!"),
        role=UserRole.LECTURER,
        email_verified=True,
        is_active=True,
    )
    db.add(uploader)
    db.flush()
    db.add_all([
        AcademicAffiliation(user_id=uploader.id, department_id=department.id, status="verified"),
    ])
    db.add_all([
        Document(
            title="Published notes",
            original_filename="published.pdf",
            storage_path="missing-published.pdf",
            sha256="a" * 64,
            file_size=20,
            page_count=1,
            uploaded_by_id=uploader.id,
            course_id=course.id,
            status=DocumentStatus.VERIFIED,
        ),
        Document(
            title="Other level notes",
            original_filename="other-level.pdf",
            storage_path="missing-other-level.pdf",
            sha256="f" * 64,
            file_size=20,
            page_count=1,
            uploaded_by_id=uploader.id,
            course_id=other_level_course.id,
            visibility=DocumentVisibility.DEPARTMENT.value,
            status=DocumentStatus.VERIFIED,
        ),
        Document(
            title="Department notes",
            original_filename="department.pdf",
            storage_path="missing-department.pdf",
            sha256="4" * 64,
            file_size=20,
            page_count=1,
            uploaded_by_id=uploader.id,
            course_id=department_course.id,
            visibility=DocumentVisibility.DEPARTMENT.value,
            status=DocumentStatus.VERIFIED,
        ),
        Document(
            title="Faculty notes",
            original_filename="faculty.pdf",
            storage_path="missing-faculty.pdf",
            sha256="1" * 64,
            file_size=20,
            page_count=1,
            uploaded_by_id=uploader.id,
            course_id=same_faculty_course.id,
            visibility=DocumentVisibility.FACULTY.value,
            status=DocumentStatus.VERIFIED,
        ),
        Document(
            title="University notes",
            original_filename="university.pdf",
            storage_path="missing-university.pdf",
            sha256="3" * 64,
            file_size=20,
            page_count=1,
            uploaded_by_id=uploader.id,
            course_id=university_course.id,
            visibility=DocumentVisibility.UNIVERSITY.value,
            status=DocumentStatus.VERIFIED,
        ),
        Document(
            title="Other university notes",
            original_filename="other-university.pdf",
            storage_path="missing-other-university.pdf",
            sha256="2" * 64,
            file_size=20,
            page_count=1,
            uploaded_by_id=uploader.id,
            course_id=other_faculty_course.id,
            visibility=DocumentVisibility.UNIVERSITY.value,
            status=DocumentStatus.VERIFIED,
        ),
        Document(
            title="Pending notes",
            original_filename="pending.pdf",
            storage_path="missing-pending.pdf",
            sha256="b" * 64,
            file_size=20,
            page_count=1,
            uploaded_by_id=uploader.id,
            status=DocumentStatus.PENDING_REVIEW,
        ),
    ])
    db.commit()
    department_id = department.id
    programme_id = programme.id
    pending_document_id = db.query(Document).filter_by(title="Pending notes").one().id
    outside_document_id = db.query(Document).filter_by(title="Other university notes").one().id
    db.close()
    submitted = client.put(
        "/api/academic/affiliation/me",
        headers=headers,
        json={"department_id": department_id, "programme_id": programme_id, "level": "100 Level"},
    )
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "pending"
    db = TestingSessionLocal()
    affiliation_id = db.query(AcademicAffiliation).filter_by(user_id=student.id).one().id
    db.close()
    assert client.get("/api/documents/published", headers=headers).status_code == 403

    admin = create_user(email="affiliation.admin@example.com", role=UserRole.ADMINISTRATOR)
    admin_login = client.post("/api/auth/login", json={
        "email": admin.email,
        "password": "Existing123!",
    })
    admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}
    verified = client.post(
        f"/api/admin/academic-affiliations/{affiliation_id}/review",
        headers=admin_headers,
        json={"decision": "verified"},
    )
    assert verified.status_code == 200
    published = client.get("/api/documents/published", headers=headers)
    assert published.status_code == 200
    assert [doc["title"] for doc in published.json()] == [
        "Published notes", "Department notes", "Faculty notes", "University notes",
    ]
    assert [doc["relevance"] for doc in published.json()] == [
        "Your enrolled course", "Your department", "Your faculty", "Your university",
    ]
    visible_document_id = published.json()[0]["id"]
    assert client.get(f"/api/documents/{visible_document_id}", headers=headers).status_code == 200
    assert client.get(f"/api/documents/{outside_document_id}", headers=headers).status_code == 403
    assert client.get(f"/api/documents/{outside_document_id}/download", headers=headers).status_code == 403
    assert client.get(f"/api/documents/{visible_document_id}/download", headers=headers).status_code == 404
    hidden = client.get(f"/api/documents/{pending_document_id}", headers=headers)
    assert hidden.status_code == 403


def test_lecturer_cannot_publish_own_upload():
    lecturer = create_user(
        email="lecturer.publish@example.com",
        role=UserRole.LECTURER,
    )
    db = TestingSessionLocal()
    profile = LecturerProfile(user_id=lecturer.id, staff_number="STAFF-PUBLISH")
    db.add(profile)
    db.flush()
    document = Document(
        title="Lecturer notes",
        original_filename="lecture.pdf",
        storage_path="missing-lecture.pdf",
        sha256="c" * 64,
        file_size=20,
        page_count=1,
        uploaded_by_id=lecturer.id,
        status=DocumentStatus.PENDING_REVIEW,
    )
    db.add(document)
    db.commit()
    document_id = document.id
    db.close()

    login = client.post("/api/auth/login", json={
        "email": "lecturer.publish@example.com",
        "password": "Existing123!",
    })
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    published = client.post(f"/api/documents/{document_id}/publish", headers=headers)
    assert published.status_code == 404


def test_lecturer_upload_requires_verified_affiliation_and_assigned_course(monkeypatch, tmp_path):
    monkeypatch.setattr(document_storage, "DOCUMENT_STORAGE", tmp_path)
    lecturer = create_user(email="lecturer.upload@example.com", role=UserRole.LECTURER)
    db = TestingSessionLocal()
    _, _, department, _, course = create_academic_scope(db)
    profile = LecturerProfile(
        user_id=lecturer.id,
        staff_number="STAFF-UPLOAD",
        department_id=department.id,
    )
    affiliation = AcademicAffiliation(user_id=lecturer.id, department_id=department.id)
    db.add_all([profile, affiliation])
    db.commit()
    course_id = course.id
    profile_id = profile.id
    db.close()
    login = client.post("/api/auth/login", json={
        "email": lecturer.email,
        "password": "Existing123!",
    })
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    pdf = pymupdf.open()
    pdf.new_page()
    pdf_bytes = pdf.tobytes()
    pdf.close()
    form = {"title": "Course notes", "course_id": str(course_id)}
    unverified = client.post(
        "/api/documents/upload", headers=headers, data=form,
        files={"file": ("notes.pdf", pdf_bytes, "application/pdf")},
    )
    assert unverified.status_code == 403

    db = TestingSessionLocal()
    stored_affiliation = db.query(AcademicAffiliation).filter_by(user_id=lecturer.id).one()
    stored_affiliation.status = "verified"
    db.commit()
    db.close()
    unassigned = client.post(
        "/api/documents/upload", headers=headers, data=form,
        files={"file": ("notes.pdf", pdf_bytes, "application/pdf")},
    )
    assert unassigned.status_code == 403

    db = TestingSessionLocal()
    db.add(LecturerCourseAssignment(lecturer_profile_id=profile_id, course_id=course_id))
    db.commit()
    db.close()
    uploaded = client.post(
        "/api/documents/upload", headers=headers, data=form,
        files={"file": ("notes.pdf", pdf_bytes, "application/pdf")},
    )
    assert uploaded.status_code == 201
    assert uploaded.json()["course_id"] == course_id
    assert uploaded.json()["status"] == "pending_review"


def test_reviewer_assignment_limits_queue_and_blocks_self_review():
    admin = create_user(email="review.admin@example.com", role=UserRole.ADMINISTRATOR)
    uploader = create_user(email="review.uploader@example.com", role=UserRole.LECTURER)
    reviewer = create_user(email="review.assigned@example.com", role=UserRole.DEPARTMENT_REVIEWER)
    other_reviewer = create_user(email="review.unassigned@example.com", role=UserRole.DEPARTMENT_REVIEWER)
    db = TestingSessionLocal()
    _, _, department, _, course = create_academic_scope(db)
    _, _, other_department, _, _ = create_academic_scope(db, suffix="B")
    db.add(LecturerProfile(user_id=uploader.id, staff_number="STAFF-REVIEW", department_id=department.id))
    db.add_all([
        AcademicAffiliation(user_id=reviewer.id, department_id=department.id, status="verified"),
        AcademicAffiliation(user_id=other_reviewer.id, department_id=other_department.id, status="verified"),
        AcademicAffiliation(user_id=uploader.id, department_id=department.id, status="verified"),
    ])
    pending = Document(
        title="Scoped lecture",
        original_filename="scoped.pdf",
        storage_path="missing-scoped.pdf",
        sha256="d" * 64,
        file_size=20,
        page_count=1,
        uploaded_by_id=uploader.id,
        course_id=course.id,
        status=DocumentStatus.PENDING_REVIEW,
    )
    self_uploaded = Document(
        title="Reviewer upload",
        original_filename="reviewer.pdf",
        storage_path="missing-reviewer.pdf",
        sha256="e" * 64,
        file_size=20,
        page_count=1,
        uploaded_by_id=reviewer.id,
        course_id=course.id,
        status=DocumentStatus.PENDING_REVIEW,
    )
    db.add_all([pending, self_uploaded])
    db.commit()
    pending_id = pending.id
    self_uploaded_id = self_uploaded.id
    department_id = department.id
    db.close()

    admin_login = client.post("/api/auth/login", json={"email": admin.email, "password": "Existing123!"})
    admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}
    assigned = client.post(
        "/api/admin/reviewer-assignments",
        headers=admin_headers,
        json={"user_id": reviewer.id, "department_id": department_id},
    )
    assert assigned.status_code == 201
    assignment_id = assigned.json()["id"]

    reviewer_login = client.post("/api/auth/login", json={"email": reviewer.email, "password": "Existing123!"})
    reviewer_headers = {"Authorization": f"Bearer {reviewer_login.json()['access_token']}"}
    other_login = client.post("/api/auth/login", json={"email": other_reviewer.email, "password": "Existing123!"})
    other_headers = {"Authorization": f"Bearer {other_login.json()['access_token']}"}
    assert [row["id"] for row in client.get("/api/documents/review-queue", headers=reviewer_headers).json()] == [pending_id]
    assert client.get("/api/documents/review-queue", headers=other_headers).json() == []
    self_review = client.post(
        f"/api/documents/{self_uploaded_id}/review",
        headers=reviewer_headers,
        data={"action": "approve"},
    )
    assert self_review.status_code == 403
    approved = client.post(
        f"/api/documents/{pending_id}/review",
        headers=reviewer_headers,
        data={"action": "approve"},
    )
    assert approved.status_code == 200
    db = TestingSessionLocal()
    assert db.get(Document, pending_id).status == DocumentStatus.VERIFIED
    db.close()

    revoked = client.post(
        f"/api/admin/reviewer-assignments/{assignment_id}/revoke",
        headers=admin_headers,
    )
    assert revoked.status_code == 200
    assert client.get("/api/documents/review-queue", headers=reviewer_headers).json() == []


def test_admin_can_list_all_roles_and_suspend_account_without_deleting_it():
    admin = create_user(
        email="admin.members@example.com",
        role=UserRole.ADMINISTRATOR,
    )
    member = create_user(email="member.directory@example.com")
    login = client.post("/api/auth/login", json={
        "email": "admin.members@example.com",
        "password": "Existing123!",
    })
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    listed = client.get("/api/admin/members", headers=headers)
    assert listed.status_code == 200
    assert {row["role"] for row in listed.json()["items"]} >= {"student", "administrator"}

    suspended = client.post(
        f"/api/admin/members/{member.id}/suspend",
        headers=headers,
        json={"reason": "Suspicious registration"},
    )
    assert suspended.status_code == 200
    db = TestingSessionLocal()
    retained = db.get(User, member.id)
    assert retained is not None
    assert retained.is_active is False
    db.close()


def test_admin_activity_log_is_paginatable_and_searchable():
    admin = create_user(
        email="admin.audit@example.com",
        role=UserRole.ADMINISTRATOR,
    )
    db = TestingSessionLocal()
    from app.models import AuditLog
    db.add_all([
        AuditLog(user_id=admin.id, action="document.uploaded", entity_type="document", entity_id=1),
        AuditLog(user_id=admin.id, action="member.suspended", entity_type="user", entity_id=2),
    ])
    db.commit()
    db.close()
    login = client.post("/api/auth/login", json={
        "email": "admin.audit@example.com",
        "password": "Existing123!",
    })
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    result = client.get("/api/admin/audit?skip=0&limit=1&action=document", headers=headers)
    assert result.status_code == 200
    assert result.json()["total"] == 1
    assert result.json()["items"][0]["action"] == "document.uploaded"


def test_admin_can_archive_and_restore_activity_without_deleting_it():
    admin = create_user(email="admin.archive@example.com", role=UserRole.ADMINISTRATOR)
    db = TestingSessionLocal()
    from app.models import AuditLog
    activity = AuditLog(
        user_id=admin.id,
        action="document.uploaded",
        entity_type="document",
        entity_id=7,
    )
    db.add(activity)
    db.commit()
    activity_id = activity.id
    db.close()

    login = client.post("/api/auth/login", json={
        "email": "admin.archive@example.com",
        "password": "Existing123!",
    })
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    archived = client.post(f"/api/admin/audit/{activity_id}/archive", headers=headers)
    assert archived.status_code == 200
    active_rows = client.get("/api/admin/audit", headers=headers).json()["items"]
    assert activity_id not in {row["id"] for row in active_rows}
    archived_rows = client.get("/api/admin/audit?archived=true", headers=headers).json()["items"]
    assert any(row["id"] == activity_id and row["archived_at"] for row in archived_rows)

    restored = client.post(f"/api/admin/audit/{activity_id}/restore", headers=headers)
    assert restored.status_code == 200
    active_rows = client.get("/api/admin/audit", headers=headers).json()["items"]
    assert activity_id in {row["id"] for row in active_rows}
    db = TestingSessionLocal()
    assert db.get(AuditLog, activity_id) is not None
    db.close()


def test_admin_account_deletion_releases_email_and_preserves_documents():
    admin = create_user(email="admin.delete@example.com", role=UserRole.ADMINISTRATOR)
    member = create_user(email="reusable.email@example.com")
    db = TestingSessionLocal()
    document = Document(
        title="Retained academic resource",
        original_filename="resource.pdf",
        storage_path="documents/resource.pdf",
        sha256="d" * 64,
        file_size=20,
        uploaded_by_id=member.id,
        status=DocumentStatus.VERIFIED,
    )
    db.add(document)
    db.commit()
    document_id = document.id
    db.close()

    admin_login = client.post("/api/auth/login", json={
        "email": admin.email,
        "password": "Existing123!",
    })
    admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}
    member_login = client.post("/api/auth/login", json={
        "email": member.email,
        "password": "Existing123!",
    })
    member_headers = {"Authorization": f"Bearer {member_login.json()['access_token']}"}

    deleted = client.delete(f"/api/admin/members/{member.id}", headers=admin_headers)
    assert deleted.status_code == 200
    assert client.get("/api/auth/me", headers=member_headers).status_code == 401
    directory = client.get("/api/admin/members", headers=admin_headers).json()
    assert member.id not in {row["id"] for row in directory["items"]}

    db = TestingSessionLocal()
    anonymized = db.get(User, member.id)
    retained_document = db.get(Document, document_id)
    assert anonymized is not None
    assert anonymized.full_name == "Deleted account"
    assert anonymized.email == f"deleted-{member.id}@deleted.invalid"
    assert anonymized.deleted_at is not None
    assert retained_document is not None
    assert retained_document.uploaded_by_id == member.id
    db.close()

    recreated = client.post("/api/auth/register", json={
        "full_name": "New Account Owner",
        "email": "reusable.email@example.com",
        "password": "StudyBridge123!",
    })
    assert recreated.status_code == 201
