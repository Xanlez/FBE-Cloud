import hashlib
import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.settings import DATA_DIR
from app.upload_limits import MAX_FILE_SIZE_BYTES, max_file_size_mb, validate_upload_file_size
from models import CloudFile

CHUNK_SIZE = 1024 * 1024


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_upload_bytes(file_obj: UploadFile) -> tuple[bytes | None, str | None]:
    size_err = validate_upload_file_size(file_obj)
    if size_err:
        return None, size_err

    file_obj.file.seek(0)
    chunks = []
    total = 0
    while True:
        block = file_obj.file.read(CHUNK_SIZE)
        if not block:
            break
        total += len(block)
        if total > MAX_FILE_SIZE_BYTES:
            file_obj.file.seek(0)
            return None, f"Файл больше {max_file_size_mb()} МБ."
        chunks.append(block)
    file_obj.file.seek(0)
    content = b"".join(chunks)
    if not content:
        return None, "Файл пустой."
    return content, None


def existing_storage_for_fingerprint(db: Session, fingerprint: str) -> str | None:
    row = (
        db.query(CloudFile.storage_name)
        .filter(
            CloudFile.content_fingerprint == fingerprint,
            CloudFile.storage_name.isnot(None),
        )
        .first()
    )
    if not row or not row[0]:
        return None
    storage_name = row[0]
    if (DATA_DIR / storage_name).is_file():
        return storage_name
    return None


def save_upload(file_obj: UploadFile, db: Session) -> tuple[dict | None, str | None]:
    if not file_obj.filename:
        return None, "Выберите файл для загрузки."

    content, read_err = read_upload_bytes(file_obj)
    if read_err:
        return None, read_err

    fingerprint = sha256_bytes(content)
    storage_name = existing_storage_for_fingerprint(db, fingerprint)
    if not storage_name:
        ext = Path(file_obj.filename).suffix.lower()
        storage_name = f"{uuid.uuid4().hex}{ext}"
        target = DATA_DIR / storage_name
        target.write_bytes(content)

    return {
        "file_name": file_obj.filename,
        "mime_type": file_obj.content_type or "application/octet-stream",
        "size_bytes": len(content),
        "content_fingerprint": fingerprint,
        "storage_name": storage_name,
    }, None


def delete_blob_if_unused(db: Session, storage_name: str | None) -> None:
    if not storage_name:
        return
    refs = (
        db.query(CloudFile.id)
        .filter(CloudFile.storage_name == storage_name)
        .count()
    )
    if refs > 0:
        return
    path = DATA_DIR / storage_name
    if path.is_file():
        path.unlink()


def resolve_storage_path(storage_name: str) -> Path | None:
    if not storage_name:
        return None
    path = (DATA_DIR / storage_name).resolve()
    if DATA_DIR.resolve() not in path.parents and path != DATA_DIR.resolve():
        return None
    if path.is_file():
        return path
    return None
