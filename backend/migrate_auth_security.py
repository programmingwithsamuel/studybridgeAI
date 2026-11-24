import sys

sys.path.insert(0, "backend")

from sqlalchemy import inspect, text

from app.core.database import engine


def migrate():
    inspector = inspect(engine)
    with engine.begin() as connection:
        if "users" not in inspector.get_table_names():
            raise RuntimeError("The users table does not exist.")

        user_columns = {column["name"] for column in inspector.get_columns("users")}
        if "email_verified" not in user_columns:
            # Existing accounts are not assumed verified. They must complete re-verification.
            connection.execute(text(
                "ALTER TABLE users ADD COLUMN email_verified BOOLEAN NOT NULL DEFAULT 0"
            ))
            print("ADDED: users.email_verified")
        else:
            print("ALREADY EXISTS: users.email_verified")

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

    print("AUTH SECURITY DATABASE MIGRATION COMPLETED.")


if __name__ == "__main__":
    migrate()
