import json
import logging
import smtplib
from email.message import EmailMessage

from starlette.datastructures import UploadFile as StarletteUploadFile

from app.settings import (
    GOOGLE_DRIVE_FOLDER_ID,
    GOOGLE_DRIVE_SCOPES,
    GOOGLE_SERVICE_ACCOUNT_JSON,
    SMTP_FROM,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USER,
)

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseUpload
except ImportError:
    service_account = None
    build = None
    MediaIoBaseUpload = None

logger = logging.getLogger(__name__)


def send_verification_email(email_to: str, code: str) -> bool:
    if not SMTP_HOST or not SMTP_USER or not SMTP_PASSWORD:
        logger.warning(
            "SMTP не настроен (SMTP_HOST/SMTP_USER/SMTP_PASSWORD в .env). "
            "Код для %s: %s",
            email_to,
            code,
        )
        return False

    msg = EmailMessage()
    msg["Subject"] = "Код подтверждения FBE cloud"
    msg["From"] = SMTP_FROM
    msg["To"] = email_to
    msg.set_content(
        f"Ваш код подтверждения: {code}\n\nКод действует 10 минут.\nЕсли это не вы, просто проигнорируйте письмо."
    )

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as smtp:
            smtp.starttls()
            smtp.login(SMTP_USER, SMTP_PASSWORD)
            smtp.send_message(msg)
    except Exception:
        logger.exception("Не удалось отправить письмо на %s", email_to)
        return False

    logger.info("Код подтверждения отправлен на %s", email_to)
    return True


def send_password_reset_email(email_to: str, code: str) -> bool:
    if not SMTP_HOST or not SMTP_USER or not SMTP_PASSWORD:
        logger.warning(
            "SMTP не настроен (SMTP_HOST/SMTP_USER/SMTP_PASSWORD в .env). "
            "Код сброса пароля для %s: %s",
            email_to,
            code,
        )
        return False

    msg = EmailMessage()
    msg["Subject"] = "Сброс пароля FBE cloud"
    msg["From"] = SMTP_FROM
    msg["To"] = email_to
    msg.set_content(
        f"Код для сброса пароля: {code}\n\n"
        f"Код действует 10 минут.\n"
        f"Если вы не запрашивали сброс, просто проигнорируйте письмо."
    )

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as smtp:
            smtp.starttls()
            smtp.login(SMTP_USER, SMTP_PASSWORD)
            smtp.send_message(msg)
    except Exception:
        logger.exception("Не удалось отправить письмо сброса пароля на %s", email_to)
        return False

    logger.info("Код сброса пароля отправлен на %s", email_to)
    return True


def get_drive_service():
    if not GOOGLE_SERVICE_ACCOUNT_JSON:
        return None, "Не настроен GOOGLE_SERVICE_ACCOUNT_JSON в .env."
    if service_account is None or build is None or MediaIoBaseUpload is None:
        return None, "Не установлены пакеты Google API."

    try:
        info = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=GOOGLE_DRIVE_SCOPES
        )
        return build("drive", "v3", credentials=creds), None
    except Exception as exc:
        return None, f"Ошибка инициализации Google Drive API: {exc}"


def upload_to_drive(file_obj: StarletteUploadFile):
    service, error = get_drive_service()
    if error:
        return None, error

    media = MediaIoBaseUpload(
        file_obj.file,
        mimetype=file_obj.content_type or "application/octet-stream",
        resumable=False,
    )
    metadata = {"name": file_obj.filename, "parents": [GOOGLE_DRIVE_FOLDER_ID]}
    created = (
        service.files()
        .create(
            body=metadata,
            media_body=media,
            fields="id,name,mimeType,size,webViewLink",
        )
        .execute()
    )
    service.permissions().create(
        fileId=created["id"],
        body={"role": "reader", "type": "anyone"},
    ).execute()

    if not created.get("webViewLink"):
        created = (
            service.files()
            .get(fileId=created["id"], fields="id,name,mimeType,size,webViewLink")
            .execute()
        )
    return created, None
