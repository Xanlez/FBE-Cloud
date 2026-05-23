from sqlalchemy.orm import Session

from models import CloudFile, Event, EventParticipant, Friendship, User


def load_user_files(db: Session, user_id: int):
    return (
        db.query(CloudFile)
        .filter(CloudFile.owner_user_id == user_id, CloudFile.visibility == "private")
        .order_by(CloudFile.id.desc())
        .all()
    )


def attach_file_authors(db: Session, files: list[CloudFile]) -> list[CloudFile]:
    if not files:
        return files
    owner_ids = {f.owner_user_id for f in files}
    names = {
        u.id: u.username
        for u in db.query(User).filter(User.id.in_(owner_ids)).all()
    }
    for row in files:
        row.author_username = names.get(row.owner_user_id, "—")
    return files


def load_user_files_for_page(db: Session, user_id: int) -> list[CloudFile]:
    return attach_file_authors(db, load_user_files(db, user_id))


def attach_event_creators(db: Session, events: list[Event]) -> list[Event]:
    if not events:
        return events
    creator_ids = {e.creator_user_id for e in events}
    names = {
        u.id: u.username
        for u in db.query(User).filter(User.id.in_(creator_ids)).all()
    }
    for row in events:
        row.creator_username = names.get(row.creator_user_id, "—")
    return events


def load_shared_files(db: Session) -> list[CloudFile]:
    return (
        db.query(CloudFile)
        .filter(CloudFile.visibility == "shared")
        .order_by(CloudFile.id.desc())
        .all()
    )


def get_friend_ids(db: Session, user_id: int):
    rows = db.query(Friendship).filter(Friendship.user_id == user_id).all()
    return [r.friend_id for r in rows]


def are_friends(db: Session, user_a: int, user_b: int) -> bool:
    row = (
        db.query(Friendship)
        .filter(Friendship.user_id == user_a, Friendship.friend_id == user_b)
        .first()
    )
    return row is not None


def can_access_event(db: Session, user_id: int, event: Event) -> bool:
    if not event.is_private:
        return True
    if event.creator_user_id == user_id:
        return True
    participant = (
        db.query(EventParticipant)
        .filter(EventParticipant.event_id == event.id, EventParticipant.user_id == user_id)
        .first()
    )
    return participant is not None
