from sqlalchemy import Boolean, Column, Integer, String, UniqueConstraint
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(150), unique=True, nullable=False, index=True)
    email = Column(String(254), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    is_staff = Column(Boolean, default=False, nullable=False)
    is_personnel = Column(Boolean, default=False, nullable=False)
    is_banned = Column(Boolean, default=False, nullable=False)
    is_email_verified = Column(Boolean, default=False, nullable=False)
    email_code = Column(String(6), nullable=True)
    email_code_expires_at = Column(String(40), nullable=True)
    avatar_filename = Column(String(255), nullable=True)


class CloudFile(Base):
    __tablename__ = "cloud_files"

    id = Column(Integer, primary_key=True, index=True)
    owner_user_id = Column(Integer, nullable=False, index=True)
    file_name = Column(String(255), nullable=False)
    mime_type = Column(String(150), nullable=True)
    size_bytes = Column(Integer, nullable=False, default=0)
    content_fingerprint = Column(String(64), nullable=True, index=True)
    storage_name = Column(String(255), nullable=True, index=True)
    drive_file_id = Column(String(255), nullable=True, unique=True)
    web_view_link = Column(String(500), nullable=True)
    created_at = Column(String(40), nullable=False)
    visibility = Column(String(20), nullable=False, default="private")
    event_id = Column(Integer, nullable=True, index=True)


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(String(1000), nullable=True)
    creator_user_id = Column(Integer, nullable=False, index=True)
    created_at = Column(String(40), nullable=False)
    event_date = Column(String(10), nullable=True, index=True)
    is_private = Column(Boolean, nullable=False, default=False)


class EventParticipant(Base):
    __tablename__ = "event_participants"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, nullable=False, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    added_by_user_id = Column(Integer, nullable=False, index=True)
    created_at = Column(String(40), nullable=False)


class FriendRequest(Base):
    __tablename__ = "friend_requests"

    id = Column(Integer, primary_key=True, index=True)
    from_user_id = Column(Integer, nullable=False, index=True)
    to_user_id = Column(Integer, nullable=False, index=True)
    status = Column(String(20), nullable=False, default="pending")
    created_at = Column(String(40), nullable=False)


class Friendship(Base):
    __tablename__ = "friendships"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    friend_id = Column(Integer, nullable=False, index=True)
    created_at = Column(String(40), nullable=False)


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    sender_user_id = Column(Integer, nullable=False, index=True)
    receiver_user_id = Column(Integer, nullable=False, index=True)
    text = Column(String(2000), nullable=True)
    file_id = Column(Integer, nullable=True, index=True)
    created_at = Column(String(40), nullable=False)


class EventMessage(Base):
    __tablename__ = "event_messages"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, nullable=False, index=True)
    sender_user_id = Column(Integer, nullable=False, index=True)
    text = Column(String(2000), nullable=True)
    file_id = Column(Integer, nullable=True, index=True)
    created_at = Column(String(40), nullable=False)


class FileReport(Base):
    __tablename__ = "file_reports"
    __table_args__ = (
        UniqueConstraint("file_id", "reporter_user_id", name="uq_file_report_reporter"),
    )

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(Integer, nullable=False, index=True)
    reporter_user_id = Column(Integer, nullable=False, index=True)
    created_at = Column(String(40), nullable=False)
