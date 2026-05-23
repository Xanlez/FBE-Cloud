import re
from datetime import date

_EVENT_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_MONTHS_RU = (
    "",
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)


def parse_event_date(raw: str) -> str | None:
    value = (raw or "").strip()
    if not value:
        return None
    if not _EVENT_DATE_RE.match(value):
        return None
    try:
        date.fromisoformat(value)
    except ValueError:
        return None
    return value


def format_event_date_ru(iso: str | None) -> str:
    if not iso:
        return "Дата не указана"
    try:
        d = date.fromisoformat(iso)
    except ValueError:
        return iso
    return f"{d.day} {_MONTHS_RU[d.month]} {d.year}"
