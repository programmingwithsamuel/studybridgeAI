from pydantic import BaseModel, ConfigDict


class CourseTopicResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    description: str | None
    position: int
    verification_status: str
    source: str | None


class CourseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    title: str
    level: str | None
    semester: str | None
    credit_units: int | None
    lecture_hours: int | None
    practical_hours: int | None
    verification_status: str
    source: str | None
    department_id: int
    department_assignment_status: str
    topics: list[CourseTopicResponse]


class CourseDetailResponse(CourseResponse):
    pass


class CourseListResponse(BaseModel):
    total: int
    skip: int
    limit: int
    items: list[CourseResponse]


class DepartmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    faculty_id: int


class ProgrammeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    code: str
    department_id: int
    level: str
    university_id: int


class ProgrammeCourseResponse(BaseModel):
    id: int
    course_id: int
    code: str
    title: str
    semester: str | None
    credit_units: int | None
    requirement_type: str
    verification_status: str
    source: str | None


class ProgrammeCurriculumResponse(BaseModel):
    programme: ProgrammeResponse
    total: int
    items: list[ProgrammeCourseResponse]
