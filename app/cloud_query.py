from dataclasses import dataclass
from urllib.parse import urlencode

from fastapi import Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.file_labels import MIME_TO_EXT, extension_from_name
from app.social_utils import attach_file_authors
from models import CloudFile, User

SORT_OPTIONS = {
    "date_desc": ("Дата (новые)", lambda: CloudFile.id.desc()),
    "date_asc": ("Дата (старые)", lambda: CloudFile.id.asc()),
    "name_asc": ("Имя (А–Я)", lambda: CloudFile.file_name.asc()),
    "name_desc": ("Имя (Я–А)", lambda: CloudFile.file_name.desc()),
    "author_asc": ("Автор (А–Я)", None),
    "size_desc": ("Размер (больше)", lambda: CloudFile.size_bytes.desc()),
    "size_asc": ("Размер (меньше)", lambda: CloudFile.size_bytes.asc()),
}


@dataclass
class SharedFilters:
    q: str = ""
    author: str = ""
    date: str = ""
    ext: str = ""
    sort: str = "date_desc"

    def active(self) -> bool:
        return bool(self.q or self.author or self.date or self.ext)

    def query_string(self) -> str:
        params = {
            "q": self.q,
            "author": self.author,
            "date": self.date,
            "ext": self.ext,
            "sort": self.sort if self.sort != "date_desc" else "",
        }
        clean = {k: v for k, v in params.items() if v}
        return urlencode(clean)


def parse_shared_filters(request: Request) -> SharedFilters:
    sort = request.query_params.get("sort", "date_desc").strip()
    if sort not in SORT_OPTIONS:
        sort = "date_desc"
    date = request.query_params.get("date", "").strip()
    if not date:
        date = request.query_params.get("date_from", "").strip()
    return SharedFilters(
        q=request.query_params.get("q", "").strip(),
        author=request.query_params.get("author", "").strip(),
        date=date,
        ext=request.query_params.get("ext", "").strip().lstrip(".").lower(),
        sort=sort,
    )


def parse_shared_filters_from_form(
    q: str = "",
    author: str = "",
    date: str = "",
    ext: str = "",
    sort: str = "date_desc",
) -> SharedFilters:
    filters = SharedFilters(
        q=q.strip(),
        author=author.strip(),
        date=date.strip(),
        ext=ext.strip().lstrip(".").lower(),
        sort=sort.strip() if sort.strip() in SORT_OPTIONS else "date_desc",
    )
    return filters


def shared_cloud_url(request: Request, filters: SharedFilters) -> str:
    base = str(request.url_for("shared_cloud"))
    qs = filters.query_string()
    return f"{base}?{qs}" if qs else base


def _matches_ext(row: CloudFile, ext: str) -> bool:
    if not ext:
        return True
    name_ext = extension_from_name(row.file_name)
    if name_ext == ext:
        return True
    if row.mime_type:
        mapped = MIME_TO_EXT.get(row.mime_type.strip().lower())
        if mapped == ext:
            return True
    return False


def _matches_published_date(row: CloudFile, date: str) -> bool:
    if not date:
        return True
    return row.created_at[:10] == date


def _sort_rows(rows: list[CloudFile], sort: str) -> list[CloudFile]:
    if sort == "author_asc":
        return sorted(rows, key=lambda r: (getattr(r, "author_username", ""), r.file_name.lower()))
    if sort == "name_asc":
        return sorted(rows, key=lambda r: r.file_name.lower())
    if sort == "name_desc":
        return sorted(rows, key=lambda r: r.file_name.lower(), reverse=True)
    if sort == "date_asc":
        return sorted(rows, key=lambda r: (r.created_at, r.id))
    if sort == "size_asc":
        return sorted(rows, key=lambda r: r.size_bytes)
    if sort == "size_desc":
        return sorted(rows, key=lambda r: r.size_bytes, reverse=True)
    return sorted(rows, key=lambda r: r.id, reverse=True)


def query_shared_files(db: Session, filters: SharedFilters) -> tuple[list[CloudFile], int]:
    total = db.query(CloudFile).filter(CloudFile.visibility == "shared").count()

    query = db.query(CloudFile).filter(CloudFile.visibility == "shared")

    if filters.author:
        query = query.join(User, CloudFile.owner_user_id == User.id).filter(
            func.lower(User.username).like(f"%{filters.author.lower()}%")
        )

    if filters.q:
        query = query.filter(
            func.lower(CloudFile.file_name).like(f"%{filters.q.lower()}%")
        )

    order = SORT_OPTIONS.get(filters.sort, SORT_OPTIONS["date_desc"])[1]
    if order is not None and filters.sort not in ("author_asc", "name_asc", "name_desc"):
        query = query.order_by(order())
    else:
        query = query.order_by(CloudFile.id.desc())

    rows = query.all()
    attach_file_authors(db, rows)

    if filters.ext:
        rows = [r for r in rows if _matches_ext(r, filters.ext)]
    if filters.date:
        rows = [r for r in rows if _matches_published_date(r, filters.date)]

    if filters.sort in ("author_asc", "name_asc", "name_desc", "date_asc", "size_asc", "size_desc"):
        rows = _sort_rows(rows, filters.sort)

    return rows, total


def list_shared_authors(db: Session) -> list[str]:
    rows = (
        db.query(User.username)
        .join(CloudFile, CloudFile.owner_user_id == User.id)
        .filter(CloudFile.visibility == "shared")
        .distinct()
        .order_by(User.username.asc())
        .all()
    )
    return [r[0] for r in rows]
