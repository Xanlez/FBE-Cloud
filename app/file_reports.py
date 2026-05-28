from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth_utils import utc_now
from models import FileReport


def create_file_report(db: Session, file_id: int, reporter_user_id: int) -> tuple[bool, str]:
    existing = (
        db.query(FileReport)
        .filter(
            FileReport.file_id == file_id,
            FileReport.reporter_user_id == reporter_user_id,
        )
        .first()
    )
    if existing:
        return False, "Вы уже отправляли жалобу на этот файл."

    db.add(
        FileReport(
            file_id=file_id,
            reporter_user_id=reporter_user_id,
            created_at=utc_now(),
        )
    )
    db.commit()
    return True, "Жалоба отправлена. Персонал проверит файл."


def report_counts_by_file_ids(db: Session, file_ids: list[int]) -> dict[int, int]:
    if not file_ids:
        return {}
    rows = (
        db.query(FileReport.file_id, func.count(FileReport.id))
        .filter(FileReport.file_id.in_(file_ids))
        .group_by(FileReport.file_id)
        .all()
    )
    return {file_id: count for file_id, count in rows}


def delete_reports_for_file(db: Session, file_id: int) -> None:
    db.query(FileReport).filter(FileReport.file_id == file_id).delete(
        synchronize_session=False
    )


def delete_reports_by_reporter(db: Session, reporter_user_id: int) -> None:
    db.query(FileReport).filter(FileReport.reporter_user_id == reporter_user_id).delete(
        synchronize_session=False
    )
