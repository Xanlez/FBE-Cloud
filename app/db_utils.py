from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.settings import DATA_DIR, DB_URL, UPLOADS_DIR

engine = create_engine(DB_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_users_table_columns():
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with engine.connect() as conn:
        result = conn.execute(text("PRAGMA table_info(users)"))
        existing = {row[1] for row in result}
        if "is_email_verified" not in existing:
            conn.execute(
                text(
                    "ALTER TABLE users ADD COLUMN is_email_verified BOOLEAN NOT NULL DEFAULT 0"
                )
            )
        if "email_code" not in existing:
            conn.execute(text("ALTER TABLE users ADD COLUMN email_code VARCHAR(6)"))
        if "email_code_expires_at" not in existing:
            conn.execute(
                text("ALTER TABLE users ADD COLUMN email_code_expires_at VARCHAR(40)")
            )
        if "avatar_filename" not in existing:
            conn.execute(text("ALTER TABLE users ADD COLUMN avatar_filename VARCHAR(255)"))
        if "is_personnel" not in existing:
            conn.execute(
                text("ALTER TABLE users ADD COLUMN is_personnel BOOLEAN NOT NULL DEFAULT 0")
            )
        conn.execute(
            text("UPDATE users SET is_personnel = 1 WHERE lower(username) = 'xanlez'")
        )

        file_result = conn.execute(text("PRAGMA table_info(cloud_files)"))
        file_existing = {row[1] for row in file_result}
        if "visibility" not in file_existing:
            conn.execute(
                text(
                    "ALTER TABLE cloud_files ADD COLUMN visibility VARCHAR(20) NOT NULL DEFAULT 'private'"
                )
            )
        if "event_id" not in file_existing:
            conn.execute(text("ALTER TABLE cloud_files ADD COLUMN event_id INTEGER"))
        if "content_fingerprint" not in file_existing:
            conn.execute(
                text("ALTER TABLE cloud_files ADD COLUMN content_fingerprint VARCHAR(64)")
            )
        if "storage_name" not in file_existing:
            conn.execute(text("ALTER TABLE cloud_files ADD COLUMN storage_name VARCHAR(255)"))

        _migrate_cloud_files_nullable_legacy(conn)

        event_result = conn.execute(text("PRAGMA table_info(events)"))
        event_existing = {row[1] for row in event_result}
        if "is_private" not in event_existing:
            conn.execute(
                text("ALTER TABLE events ADD COLUMN is_private BOOLEAN NOT NULL DEFAULT 0")
            )
        if "event_date" not in event_existing:
            conn.execute(text("ALTER TABLE events ADD COLUMN event_date VARCHAR(10)"))
        conn.commit()


def _migrate_cloud_files_nullable_legacy(conn):
    """SQLite: старая схема требовала drive_file_id/web_view_link NOT NULL."""
    rows = list(conn.execute(text("PRAGMA table_info(cloud_files)")))
    if not rows:
        return

    columns = {row[1]: row for row in rows}
    drive_col = columns.get("drive_file_id")
    if not drive_col or drive_col[3] == 0:
        return

    conn.execute(
        text(
            """
            CREATE TABLE cloud_files_new (
                id INTEGER NOT NULL PRIMARY KEY,
                owner_user_id INTEGER NOT NULL,
                file_name VARCHAR(255) NOT NULL,
                mime_type VARCHAR(150),
                size_bytes INTEGER NOT NULL,
                content_fingerprint VARCHAR(64),
                storage_name VARCHAR(255),
                drive_file_id VARCHAR(255),
                web_view_link VARCHAR(500),
                created_at VARCHAR(40) NOT NULL,
                visibility VARCHAR(20) NOT NULL,
                event_id INTEGER,
                UNIQUE (drive_file_id)
            )
            """
        )
    )
    conn.execute(
        text(
            """
            INSERT INTO cloud_files_new (
                id, owner_user_id, file_name, mime_type, size_bytes,
                content_fingerprint, storage_name, drive_file_id, web_view_link,
                created_at, visibility, event_id
            )
            SELECT
                id, owner_user_id, file_name, mime_type, size_bytes,
                content_fingerprint, storage_name, drive_file_id, web_view_link,
                created_at, visibility, event_id
            FROM cloud_files
            """
        )
    )
    conn.execute(text("DROP TABLE cloud_files"))
    conn.execute(text("ALTER TABLE cloud_files_new RENAME TO cloud_files"))
