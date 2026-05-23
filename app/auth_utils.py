import random
from datetime import datetime, timezone

from fastapi import Request
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.settings import UPLOADS_DIR
from models import User

pwd_context = CryptContext(schemes=["pbkdf2_sha256", "bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def resolve_avatar_filename(user: User | None) -> str | None:
    if not user or not user.avatar_filename:
        return None
    path = UPLOADS_DIR / user.avatar_filename
    if path.is_file():
        return user.avatar_filename
    return None


def user_is_personnel(user: User | None) -> bool:
    return bool(user and user.is_personnel)


def get_current_user(request: Request, db: Session) -> User | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.query(User).filter(User.id == user_id).first()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def generate_email_code() -> str:
    return f"{random.randint(0, 999999):06d}"


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
