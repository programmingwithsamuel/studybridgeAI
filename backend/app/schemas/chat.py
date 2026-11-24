from pydantic import BaseModel, Field


class ChatSessionCreate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)


class ChatMessageCreate(BaseModel):
    message: str = Field(min_length=1, max_length=6000)


class ChatSourceResponse(BaseModel):
    document_id: int
    document_title: str
    page_number: int
    excerpt: str
    course_code: str | None = None
    university: str | None = None
    faculty: str | None = None
    department: str | None = None


class ChatMessageResponse(BaseModel):
    id: int
    role: str
    content: str
    created_at: str
    sources: list[ChatSourceResponse] = Field(default_factory=list)


class ChatSessionResponse(BaseModel):
    id: int
    title: str | None
    created_at: str
    message_count: int


class ChatSessionDetailResponse(ChatSessionResponse):
    messages: list[ChatMessageResponse]
