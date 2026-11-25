from app.models.user import User, UserRole
from app.models.auth_token import AuthToken
from app.models.audit import AuditLog
from app.models.academic import University, Faculty, Department, Course
from app.models.course_topic import CourseTopic
from app.models.programme import Programme, ProgrammeCourse
from app.models.profiles import (
    StudentProfile, LecturerProfile, LecturerCourseAssignment,
    ProfileChangeRequest, UserSession, AcademicAffiliation, ReviewerAssignment,
)
from app.models.document import (
    Document, DocumentVersion, DocumentStatus, DocumentVisibility, DocumentIndexStatus,
)
from app.models.review import DocumentPermission, ReviewDecision, PermissionLevel, ReviewAction
from app.models.chat import ChatSession, ChatMessage
from app.models.practice import PracticeQuestion, StudentProgress

__all__ = [
    "User", "UserRole", "AuthToken", "AuditLog", "University", "Faculty", "Department",
    "Course", "CourseTopic", "Programme", "ProgrammeCourse", "StudentProfile",
    "LecturerProfile", "LecturerCourseAssignment", "ProfileChangeRequest", "UserSession",
    "AcademicAffiliation", "ReviewerAssignment",
    "Document", "DocumentVersion", "DocumentStatus", "DocumentVisibility", "DocumentIndexStatus",
    "DocumentPermission", "ReviewDecision", "PermissionLevel", "ReviewAction",
    "ChatSession", "ChatMessage", "PracticeQuestion", "StudentProgress",
]
