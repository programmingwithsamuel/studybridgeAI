from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class Programme(Base):
    __tablename__ = "programmes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    department_id: Mapped[int] = mapped_column(
        ForeignKey("departments.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    level: Mapped[str] = mapped_column(String(20), nullable=False, default="100 Level")
    university_id: Mapped[int] = mapped_column(
        ForeignKey("universities.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    department: Mapped["Department"] = relationship()
    university: Mapped["University"] = relationship()
    curriculum_items: Mapped[list["ProgrammeCourse"]] = relationship(
        back_populates="programme", cascade="all, delete-orphan"
    )


class ProgrammeCourse(Base):
    __tablename__ = "programme_courses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    programme_id: Mapped[int] = mapped_column(
        ForeignKey("programmes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    academic_year: Mapped[str | None] = mapped_column(String(30), nullable=True)
    semester: Mapped[str | None] = mapped_column(String(20), nullable=True)
    requirement_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="required"
    )
    source: Mapped[str | None] = mapped_column(String(500), nullable=True)
    verification_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="unverified"
    )

    programme: Mapped["Programme"] = relationship(back_populates="curriculum_items")
    course: Mapped["Course"] = relationship()

    __table_args__ = (
        UniqueConstraint("programme_id", "course_id", name="uq_programme_course"),
    )
