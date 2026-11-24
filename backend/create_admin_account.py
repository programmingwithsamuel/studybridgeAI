"""One-time operator-created administrator bootstrap.

Usage:
  c:\studybridgeAi\.venv\Scripts\python.exe c:\studybridgeAi\backend\create_admin_account.py

Requires explicit operator input for email and password. No credentials are
stored in source or command history by this script.
"""
import getpass
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))

from app.core.database import Base, SessionLocal, engine
from app.core.security import hash_password
from app.core.email_validation import validate_password
from app.models import User, UserRole


def main() -> None:
    Base.metadata.create_all(bind=engine)
    full_name = input("Administrator full name: ").strip()
    email = input("Administrator email: ").strip().lower()
    username = input("Administrator username: ").strip()
    password = getpass.getpass("Administrator password: ")
    if len(full_name) < 2 or len(email) < 5:
        raise SystemExit("Full name and email are required.")
    try:
        validate_password(password)
    except ValueError as exc:
        raise SystemExit(str(exc))

    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            if existing.role == UserRole.ADMINISTRATOR:
                raise SystemExit("An administrator account already exists for this email.")
            raise SystemExit("A non-administrator account already exists for this email.")
        db.add(User(
            full_name=full_name,
            email=email,
            username=username,
            password_hash=hash_password(password),
            role=UserRole.ADMINISTRATOR,
            email_verified=True,
            is_active=True,
        ))
        db.commit()
        print("Administrator account created.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
