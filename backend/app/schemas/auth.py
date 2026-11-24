from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
class RegisterRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=150)
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    allow_email_typo: bool = False
class LoginRequest(BaseModel):
    email: str
    password: str
    allow_email_typo: bool = False
class ForgotPasswordRequest(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    allow_email_typo: bool = False
class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=20, max_length=512)
    password: str = Field(min_length=8, max_length=128)
class ResendVerificationRequest(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    allow_email_typo: bool = False
class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=20, max_length=512)
class EmailCheckRequest(BaseModel):
    email: str = Field(min_length=5, max_length=255)
class EmailChangeRequest(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    allow_email_typo: bool = False
class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    full_name: str
    email: str
    role: str
    is_active: bool
    email_verified: bool
    created_at: datetime
class RegistrationResponse(UserResponse):
    development_verification_url: str | None = None
