from fastapi import UploadFile
from sqlalchemy.orm import Session

from models import CloudFile

MAX_FILES_PER_ACCOUNT = 10
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024
MAX_FILES_PER_UPLOAD = 10


def max_file_size_mb() -> int:
    return MAX_FILE_SIZE_BYTES // (1024 * 1024)


def upload_limit_hint() -> str:
    return (
        f"Лимит: до {MAX_FILES_PER_ACCOUNT} файлов на аккаунт, "
        f"каждый до {max_file_size_mb()} МБ"
    )


def count_account_files(db: Session, user_id: int) -> int:
    return db.query(CloudFile).filter(CloudFile.owner_user_id == user_id).count()


def files_remaining(db: Session, user_id: int) -> int:
    return max(0, MAX_FILES_PER_ACCOUNT - count_account_files(db, user_id))


def check_can_add_files(db: Session, user_id: int, count: int) -> str | None:
    if count <= 0:
        return None
    if count > MAX_FILES_PER_UPLOAD:
        return f"За раз можно загрузить не более {MAX_FILES_PER_UPLOAD} файлов."
    remaining = files_remaining(db, user_id)
    if count > remaining:
        if remaining == 0:
            return (
                f"Достигнут лимит: не более {MAX_FILES_PER_ACCOUNT} файлов на аккаунт."
            )
        return (
            f"Можно добавить ещё {remaining} из {MAX_FILES_PER_ACCOUNT} файлов на аккаунт."
        )
    return None


def validate_upload_file_size(file_obj: UploadFile) -> str | None:
    size = getattr(file_obj, "size", None)
    if size is not None and size > MAX_FILE_SIZE_BYTES:
        return f"Размер больше {max_file_size_mb()} МБ."
    return None


def collect_upload_files(files: list[UploadFile]) -> list[UploadFile]:
    return [f for f in files if f.filename]
