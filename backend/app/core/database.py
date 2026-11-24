from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
# Store the database inside the backend directory.
BASE_DIR = Path(__file__).resolve().parents[2]
DATABASE_PATH = BASE_DIR / "studybridge.db"
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
