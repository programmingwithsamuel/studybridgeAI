
import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


# Store the database locally by default.
# Northflank can override this using DATABASE_PATH=/data/studybridge.db.
BASE_DIR = Path(__file__).resolve().parents[2]

DATABASE_PATH = Path(
    os.getenv("DATABASE_PATH", str(BASE_DIR / "studybridge.db"))
).expanduser()

# Ensure the database directory exists.
DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)


# SQLite database connection.
DATABASE_URL = f"sqlite:///{DATABASE_PATH.as_posix()}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)


# Reusable database sessions.
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


# Base class for all database models.
class Base(DeclarativeBase):
    pass


# Database dependency for FastAPI routes.
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
