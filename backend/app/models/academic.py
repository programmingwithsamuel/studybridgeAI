from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class University(Base):
    __tablename__ = "universities"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    faculties: Mapped[list["Faculty"]] = relationship(back_populates="university")


class Faculty(Base):
    __tablename__ = "faculties"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    university_id: Mapped[int] = mapped_column(ForeignKey("universities.id", ondelete="RESTRICT"), nullable=False, index=True)
    university: Mapped["University"] = relationship(back_populates="faculties")
    departments: Mapped[list["Department"]] = relationship(back_populates="faculty")
    __table_args__ = (UniqueConstraint("university_id", "name", name="uq_faculty_university_name"),)


class Department(Base):
    __tablename__ = "departments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    faculty_id: Mapped[int] = mapped_column(ForeignKey("faculties.id", ondelete="RESTRICT"), nullable=False, index=True)
    faculty: Mapped["Faculty"] = relationship(back_populates="departments")
    courses: Mapped[list["Course"]] = relationship(back_populates="department")
    __table_args__ = (UniqueConstraint("faculty_id", "name", name="uq_department_faculty_name"),)


class Course(Base):
    __tablename__ = "courses"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    semester: Mapped[str | None] = mapped_column(String(20), nullable=True)
    credit_units: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lecture_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    practical_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    verification_status: Mapped[str] = mapped_column(String(30), nullable=False, default="unverified")
    source: Mapped[str | None] = mapped_column(String(500), nullable=True)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id", ondelete="RESTRICT"), nullable=False, index=True)
    department_assignment_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="unverified"
    )
    department: Mapped["Department"] = relationship(back_populates="courses")
    topics: Mapped[list["CourseTopic"]] = relationship(back_populates="course", cascade="all, delete-orphan")
    __table_args__ = (UniqueConstraint("department_id", "code", name="uq_course_department_code"),)
