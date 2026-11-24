from getpass import getpass

from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.core.email_validation import validate_password
from app.models import User, UserRole


def main() -> None:
    print("StudyBridge AI — one-time reviewer account setup")
    print("This creates a separate department_reviewer account. It does not modify existing users.\n")

    full_name = input("Reviewer full name: ").strip()
    email = input("Reviewer email: ").strip().lower()
    password = getpass("New password (hidden): ")
    confirm = getpass("Confirm password: ")

    if len(full_name) < 2:
        raise SystemExit("Name must contain at least 2 characters.")
    if password != confirm:
        raise SystemExit("Passwords do not match.")
    try:
        validate_password(password)
        from app.core.email_validation import validate_email
        normalized_email = validate_email(email).normalized
    except ValueError as exc:
        raise SystemExit(str(exc))

    db = SessionLocal()
    try:
        existing = db.scalar(select(User).where(User.email == normalized_email))
        if existing:
            raise SystemExit(
                f"An account already exists for {normalized_email}. No changes were made."
            )

        user = User(
            full_name=full_name,
            email=normalized_email,
            password_hash=hash_password(password),
            role=UserRole.DEPARTMENT_REVIEWER,
            is_active=True,
            # This account is created locally by the project owner, so it does not
            # need an emailed verification link to activate this bootstrap account.
            email_verified=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        print("\nReviewer account created successfully.")
        print(f"User ID: {user.id}")
        print(f"Email: {user.email}")
        print(f"Role: {user.role.value}")
        print("Email verified: yes (local bootstrap)")
        print("Keep the password private. Sign in through the normal StudyBridge AI login.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
