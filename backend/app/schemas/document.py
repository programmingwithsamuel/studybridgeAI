from datetime import datetime
from pydantic import BaseModel, ConfigDict


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    description: str | None
    original_filename: str
    sha256: str
    file_size: int
    page_count: int | None
    uploaded_by_id: int
    course_id: int | None
    status: str
    created_at: datetime
    updated_at: datetime
    relevance: str | None = None


class ReviewDecisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    document_id: int
    reviewer_id: int
    action: str
    comments: str | None
    created_at: datetime
