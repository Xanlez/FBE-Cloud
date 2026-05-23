from fastapi.templating import Jinja2Templates

from app.auth_utils import resolve_avatar_filename
from app.admin_stats import format_bytes
from app.event_dates import format_event_date_ru
from app.file_labels import format_file_type
from app.file_preview import can_preview_file, is_image_file
from app.upload_limits import upload_limit_hint
from app.settings import BASE_DIR

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.filters["file_type"] = format_file_type
templates.env.filters["avatar_file"] = resolve_avatar_filename
templates.env.filters["event_date_ru"] = format_event_date_ru
templates.env.filters["bytes_hr"] = format_bytes
templates.env.filters["can_preview_file"] = can_preview_file
templates.env.filters["is_image_file"] = is_image_file
templates.env.globals["upload_limit_hint"] = upload_limit_hint
