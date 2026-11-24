
import sys

sys.path.insert(0, "backend")

from sqlalchemy import inspect

from app.core.database import engine


NEW_COLUMNS = {
    "semester": "VARCHAR(20)",
    "credit_units": "INTEGER",
    "lecture_hours": "INTEGER",
    "practical_hours": "INTEGER",
    "verification_status": (
        "VARCHAR(30) NOT NULL DEFAULT 'unverified'"
    ),
    "source": "VARCHAR(500)",
}


def migrate():
    inspector = inspect(engine)

    if "courses" not in inspector.get_table_names():
        raise RuntimeError("The courses table does not exist.")

    existing_columns = {
        column["name"]
        for column in inspector.get_columns("courses")
    }

    with engine.begin() as connection:
        for column_name, column_type in NEW_COLUMNS.items():
            if column_name not in existing_columns:
                connection.exec_driver_sql(
                    f"ALTER TABLE courses "
                    f"ADD COLUMN {column_name} {column_type}"
                )
                print("ADDED:", column_name)
            else:
                print("ALREADY EXISTS:", column_name)

    print("\nCOURSE DATABASE MIGRATION COMPLETED.")


if __name__ == "__main__":
    migrate()
