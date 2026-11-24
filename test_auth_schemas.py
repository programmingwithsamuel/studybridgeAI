import sys
sys.path.insert(0, "backend")
from app.schemas.auth import RegisterRequest, LoginRequest, TokenResponse
registration = RegisterRequest(
    full_name="Demo Student",
    email="student@example.com",
    password="StudyBridge123!"
)
login = LoginRequest(
    email="student@example.com",
    password="StudyBridge123!"
)
token = TokenResponse(access_token="demo-token")
print("REGISTRATION SCHEMA:", registration.full_name)
print("LOGIN SCHEMA:", login.email)
print("TOKEN TYPE:", token.token_type)
print("ROLE FIELD ACCEPTED:", "role" in RegisterRequest.model_fields)
