from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.social_utils import can_access_event
from models import CloudFile, Event, Message


def user_can_access_file(db: Session, user_id: int, row: CloudFile) -> bool:
    if row.owner_user_id == user_id:
        return True
    if row.visibility == "shared":
        return True
    if row.visibility == "event" and row.event_id:
        event = db.query(Event).filter(Event.id == row.event_id).first()
        if event and can_access_event(db, user_id, event):
            return True
    in_chat = (
        db.query(Message.id)
        .filter(
            Message.file_id == row.id,
            or_(
                Message.sender_user_id == user_id,
                Message.receiver_user_id == user_id,
            ),
        )
        .first()
    )
    if in_chat:
        return True
    return False
