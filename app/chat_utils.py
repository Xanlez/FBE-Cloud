from fastapi import Request
from sqlalchemy import or_
from sqlalchemy.orm import Session

from models import CloudFile, EventMessage, Message, User


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
                    request.app.url_path_for(
                        "cloud_file_download", file_id=file_row.id
                    )
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


def _message_file_link(request: Request, file_row: CloudFile | None) -> str | None:
    if not file_row:
        return None
    if file_row.storage_name:
        return request.app.url_path_for("cloud_file_download", file_id=file_row.id)
    return file_row.web_view_link


def load_event_chat_messages(
    db: Session, request: Request, event_id: int
) -> list[dict]:
    rows = (
        db.query(EventMessage)
        .filter(EventMessage.event_id == event_id)
        .order_by(EventMessage.id.asc())
        .all()
    )
    file_ids = [m.file_id for m in rows if m.file_id]
    file_map: dict[int, CloudFile] = {}
    if file_ids:
        files = db.query(CloudFile).filter(CloudFile.id.in_(file_ids)).all()
        file_map = {f.id: f for f in files}

    sender_ids = {m.sender_user_id for m in rows}
    sender_names: dict[int, str] = {}
    if sender_ids:
        users = db.query(User).filter(User.id.in_(sender_ids)).all()
        sender_names = {u.id: u.username for u in users}

    messages = []
    for m in rows:
        file_row = file_map.get(m.file_id) if m.file_id else None
        messages.append(
            {
                "sender_user_id": m.sender_user_id,
                "sender_username": sender_names.get(m.sender_user_id, "—"),
                "text": m.text or "",
                "created_at": m.created_at,
                "file_name": file_row.file_name if file_row else None,
                "file_link": _message_file_link(request, file_row),
            }
        )
    return messages


def load_event_chat_attachable_files(
    db: Session, user_id: int, event_id: int, limit: int = 100
) -> list[CloudFile]:
    own = (
        db.query(CloudFile)
        .filter(CloudFile.owner_user_id == user_id, CloudFile.visibility == "private")
        .order_by(CloudFile.id.desc())
        .limit(limit)
        .all()
    )
    event_files = (
        db.query(CloudFile)
        .filter(
            CloudFile.event_id == event_id,
            CloudFile.visibility == "event",
        )
        .order_by(CloudFile.id.desc())
        .all()
    )
    seen: set[int] = set()
    combined: list[CloudFile] = []
    for row in own + event_files:
        if row.id in seen:
            continue
        seen.add(row.id)
        combined.append(row)
    return combined[:limit]
