from fastapi import Request
from sqlalchemy import or_
from sqlalchemy.orm import Session

from models import CloudFile, Message, User


def load_chat_messages(
    db: Session, request: Request, user_id: int, friend_id: int
) -> list[dict]:
    if friend_id == user_id:
        rows = (
            db.query(Message)
            .filter(
                Message.sender_user_id == user_id,
                Message.receiver_user_id == user_id,
            )
            .order_by(Message.id.asc())
            .all()
        )
    else:
        rows = (
            db.query(Message)
            .filter(
                or_(
                    ((Message.sender_user_id == user_id) & (Message.receiver_user_id == friend_id)),
                    ((Message.sender_user_id == friend_id) & (Message.receiver_user_id == user_id)),
                )
            )
            .order_by(Message.id.asc())
            .all()
        )
    file_ids = [m.file_id for m in rows if m.file_id]
    file_map = {}
    if file_ids:
        files = db.query(CloudFile).filter(CloudFile.id.in_(file_ids)).all()
        file_map = {f.id: f for f in files}

    messages = []
    for m in rows:
        file_row = file_map.get(m.file_id) if m.file_id else None
        messages.append(
            {
                "sender_user_id": m.sender_user_id,
                "text": m.text or "",
                "created_at": m.created_at,
                "file_name": file_row.file_name if file_row else None,
                "file_link": (
                    str(request.url_for("cloud_file_download", file_id=file_row.id))
                    if file_row and file_row.storage_name
                    else (file_row.web_view_link if file_row else None)
                ),
            }
        )
    return messages


def load_own_files_for_chat(db: Session, user_id: int, limit: int = 100) -> list[CloudFile]:
    return (
        db.query(CloudFile)
        .filter(CloudFile.owner_user_id == user_id)
        .order_by(CloudFile.id.desc())
        .limit(limit)
        .all()
    )
