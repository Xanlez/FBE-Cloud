from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.file_storage import delete_blob_if_unused
from app.settings import UPLOADS_DIR
from app.file_reports import delete_reports_for_file, delete_reports_by_reporter
from models import (
    CloudFile,
    Event,
    EventParticipant,
    FriendRequest,
    Friendship,
    Message,
    User,
)


def delete_cloud_file_by_id(db: Session, file_id: int) -> str | None:
    row = db.query(CloudFile).filter(CloudFile.id == file_id).first()
    if not row:
        return None
    label = row.file_name
    db.query(Message).filter(Message.file_id == file_id).update(
        {Message.file_id: None},
        synchronize_session=False,
    )
    _delete_file_row(db, row)
    db.commit()
    return label


def _delete_file_row(db: Session, row: CloudFile) -> None:
    delete_reports_for_file(db, row.id)
    storage_name = row.storage_name
    db.delete(row)
    db.flush()
    delete_blob_if_unused(db, storage_name)


def _delete_event_completely(db: Session, event_id: int) -> None:
    files = db.query(CloudFile).filter(CloudFile.event_id == event_id).all()
    for row in files:
        _delete_file_row(db, row)
    db.query(EventParticipant).filter(EventParticipant.event_id == event_id).delete()
    db.query(Event).filter(Event.id == event_id).delete()


def delete_user_completely(db: Session, user_id: int) -> bool:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return False

    created_event_ids = [
        row[0]
        for row in db.query(Event.id).filter(Event.creator_user_id == user_id).all()
    ]
    for event_id in created_event_ids:
        _delete_event_completely(db, event_id)

    db.query(EventParticipant).filter(EventParticipant.user_id == user_id).delete()

    owned_files = db.query(CloudFile).filter(CloudFile.owner_user_id == user_id).all()
    for row in owned_files:
        _delete_file_row(db, row)

    db.query(Message).filter(
        or_(Message.sender_user_id == user_id, Message.receiver_user_id == user_id)
    ).delete(synchronize_session=False)

    db.query(FriendRequest).filter(
        or_(FriendRequest.from_user_id == user_id, FriendRequest.to_user_id == user_id)
    ).delete(synchronize_session=False)

    db.query(Friendship).filter(
        or_(Friendship.user_id == user_id, Friendship.friend_id == user_id)
    ).delete(synchronize_session=False)

    if user.avatar_filename:
        avatar_path = UPLOADS_DIR / user.avatar_filename
        if avatar_path.is_file():
            avatar_path.unlink()

    delete_reports_by_reporter(db, user_id)
    db.delete(user)
    db.commit()
    return True


def set_user_banned(db: Session, user_id: int, banned: bool) -> User | None:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return None
    user.is_banned = banned
    db.commit()
    db.refresh(user)
    return user


def set_user_personnel(db: Session, user_id: int, personnel: bool) -> User | None:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return None
    user.is_personnel = personnel
    db.commit()
    db.refresh(user)
    return user
