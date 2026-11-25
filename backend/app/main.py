from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

from app.core.config import settings
from app.core.database import engine

from app.api.auth import router as auth_router
from app.api.documents import router as documents_router
from app.api.academic import router as academic_router
from app.api.admin import router as admin_router
from app.api.lecturers import router as lecturers_router
from app.api.chat import router as chat_router
from app.core.database import Base
from app import models as _models

app = FastAPI(
    title="StudyBridge AI",
    description="Independent academic learning platform prototype",
    version="0.1.0",
)

# Allow the local Vite development frontend to call this API.
# localhost and 127.0.0.1 are different browser origins.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    return response


@app.on_event("startup")
def migrate_auth_schema() -> None:
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    with engine.begin() as connection:
        if "users" in inspector.get_table_names():
            user_columns = {column["name"] for column in inspector.get_columns("users")}
            if "email_verified" not in user_columns:
                connection.execute(text(
                    "ALTER TABLE users ADD COLUMN email_verified BOOLEAN NOT NULL DEFAULT 0"
                ))
            if "username" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN username VARCHAR(80)"))
                connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_username ON users(username)"))
            if "deleted_at" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN deleted_at DATETIME"))

        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS auth_tokens (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                purpose VARCHAR(20) NOT NULL,
                token_hash VARCHAR(64) NOT NULL UNIQUE,
                expires_at DATETIME NOT NULL,
                used_at DATETIME,
                target_email VARCHAR(255),
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_auth_tokens_user_id ON auth_tokens(user_id)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_auth_tokens_purpose ON auth_tokens(purpose)"))
        connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_auth_tokens_token_hash ON auth_tokens(token_hash)"))
        token_columns = {row[1] for row in connection.execute(text("PRAGMA table_info(auth_tokens)"))}
        if "target_email" not in token_columns:
            connection.execute(text("ALTER TABLE auth_tokens ADD COLUMN target_email VARCHAR(255)"))

        if "lecturer_profiles" in inspector.get_table_names():
            lecturer_columns = {column["name"] for column in inspector.get_columns("lecturer_profiles")}
            lecturer_alters = {
                "lecturer_id": "VARCHAR(40)",
                "phone": "VARCHAR(30)",
                "biography": "TEXT",
                "qualifications": "TEXT",
                "office_location": "TEXT",
                "invitation_status": "VARCHAR(20)",
                "invitation_expires_at": "DATETIME",
            }
            for name, column_type in lecturer_alters.items():
                if name not in lecturer_columns:
                    default = " NOT NULL DEFAULT 'pending'" if name == "invitation_status" else ""
                    connection.execute(text(f"ALTER TABLE lecturer_profiles ADD COLUMN {name} {column_type}{default}"))
            connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_lecturer_profiles_lecturer_id ON lecturer_profiles(lecturer_id)"))

        if "audit_logs" in inspector.get_table_names():
            audit_columns = {column["name"] for column in inspector.get_columns("audit_logs")}
            if "archived_at" not in audit_columns:
                connection.execute(text("ALTER TABLE audit_logs ADD COLUMN archived_at DATETIME"))
            if "archived_by" not in audit_columns:
                connection.execute(text(
                    "ALTER TABLE audit_logs ADD COLUMN archived_by INTEGER REFERENCES users(id) ON DELETE SET NULL"
                ))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_audit_logs_archived_at ON audit_logs(archived_at)"))

        if "documents" in inspector.get_table_names():
            document_columns = {column["name"] for column in inspector.get_columns("documents")}
            if "withdrawn_at" not in document_columns:
                connection.execute(text("ALTER TABLE documents ADD COLUMN withdrawn_at DATETIME"))
            if "visibility" not in document_columns:
                connection.execute(text(
                    "ALTER TABLE documents ADD COLUMN visibility VARCHAR(20) NOT NULL DEFAULT 'course'"
                ))

        if "chat_messages" in inspector.get_table_names():
            message_columns = {column["name"] for column in inspector.get_columns("chat_messages")}
            if "sources_json" not in message_columns:
                connection.execute(text("ALTER TABLE chat_messages ADD COLUMN sources_json TEXT"))



app.include_router(auth_router)
app.include_router(documents_router)
app.include_router(academic_router)
app.include_router(admin_router)
app.include_router(lecturers_router)
app.include_router(chat_router)


@app.get("/")
def home():
    return {
        "message": "Welcome to StudyBridge AI",
        "status": "running",
    }


@app.get("/api/health")
def health():
    return {
        "status": "healthy",
        "application": "StudyBridge AI",
    }
