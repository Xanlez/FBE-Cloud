import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DB_URL = os.environ.get("DATABASE_URL", f"sqlite:///{BASE_DIR / 'db.sqlite3'}")
SECRET_KEY = os.environ.get(
    "APP_SECRET_KEY", "dev-only-change-me-in-production-not-for-production-use"
)

SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USER or "no-reply@fbe-cloud.local")

UPLOADS_DIR = BASE_DIR / "static" / "uploads"
DATA_DIR = BASE_DIR / "data"
ALLOWED_AVATAR_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

GOOGLE_DRIVE_FOLDER_ID = os.environ.get(
    "GOOGLE_DRIVE_FOLDER_ID", "1Q4Vm9mRkqAFcIQ_yLOwPeGSl1IHUWNjc"
)
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
GOOGLE_DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.file"]
