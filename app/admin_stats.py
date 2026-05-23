from pathlib import Path

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.settings import DATA_DIR
from models import (
    CloudFile,
    Event,
    EventParticipant,
    FriendRequest,
    Friendship,
    Message,
    User,
)

VISIBILITY_LABELS = {
    "private": "Личный",
    "shared": "Общее облако",
    "event": "Событие",
}


def format_bytes(size: int) -> str:
    if size >= 1073741824:
        return f"{size / 1073741824:.2f} ГБ"
    if size >= 1048576:
        return f"{size / 1048576:.1f} МБ"
    if size >= 1024:
        return f"{size / 1024:.1f} КБ"
    return f"{size} Б"


def _disk_usage_bytes(root: Path) -> int:
    if not root.is_dir():
        return 0
    total = 0
    for path in root.rglob("*"):
        if path.is_file():
            try:
                total += path.stat().st_size
            except OSError:
                pass
    return total


def load_admin_dashboard(db: Session) -> dict:
    users = db.query(User).order_by(User.id.desc()).all()
    files = db.query(CloudFile).order_by(CloudFile.id.desc()).all()
    events = db.query(Event).order_by(Event.id.desc()).all()

    usernames = {u.id: u.username for u in users}
    event_titles = {e.id: e.title for e in events}

    for row in files:
        row.owner_username = usernames.get(row.owner_user_id, "—")
        row.visibility_label = VISIBILITY_LABELS.get(row.visibility, row.visibility)
        if row.event_id:
            row.event_title = event_titles.get(row.event_id, f"#{row.event_id}")
        else:
            row.event_title = "—"

    for row in events:
        row.creator_username = usernames.get(row.creator_user_id, "—")

    files_total_bytes = sum(f.size_bytes for f in files)
    vis_rows = (
        db.query(CloudFile.visibility, func.count(CloudFile.id))
        .group_by(CloudFile.visibility)
        .all()
    )
    files_by_visibility = {
        VISIBILITY_LABELS.get(vis, vis): count for vis, count in vis_rows
    }

    pending_requests = (
        db.query(FriendRequest)
        .filter(FriendRequest.status == "pending")
        .order_by(FriendRequest.id.desc())
        .limit(50)
        .all()
    )
    for req in pending_requests:
        req.from_username = usernames.get(req.from_user_id, "—")
        req.to_username = usernames.get(req.to_user_id, "—")

    stats = {
        "users_count": len(users),
        "users_verified": sum(1 for u in users if u.is_email_verified),
        "users_personnel": sum(1 for u in users if u.is_personnel),
        "files_count": len(files),
        "files_total_bytes": files_total_bytes,
        "files_disk_bytes": _disk_usage_bytes(DATA_DIR),
        "files_by_visibility": files_by_visibility,
        "events_count": db.query(Event).count(),
        "events_private": db.query(Event).filter(Event.is_private.is_(True)).count(),
        "event_participants_count": db.query(EventParticipant).count(),
        "messages_count": db.query(Message).count(),
        "friendships_count": db.query(Friendship).count(),
        "friend_requests_pending": db.query(FriendRequest)
        .filter(FriendRequest.status == "pending")
        .count(),
    }

    return {
        "stats": stats,
        "users": users,
        "files": files,
        "events": events,
        "pending_requests": pending_requests,
    }
