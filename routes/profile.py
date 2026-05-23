import uuid
from datetime import timedelta
from pathlib import Path

from fastapi import APIRouter, File, Form, Request, UploadFile, status
from fastapi.responses import RedirectResponse

from app.auth_utils import (
    generate_email_code,
    get_current_user,
    get_password_hash,
    parse_dt,
    utc_now,
)
from app.db_utils import SessionLocal
from app.integrations import send_verification_email
from app.settings import ALLOWED_AVATAR_EXTENSIONS, UPLOADS_DIR
from app.web import templates

router = APIRouter()


@router.get("/account/profile/", name="profile")
def profile_page(request: Request):
    db = SessionLocal()
    user = get_current_user(request, db)
    db.close()
    if not user:
        return RedirectResponse(url="/accounts/login/", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request=request,
        name="core/profile.html",
        context={"user": user, "error": None, "success": None},
    )


@router.post("/account/avatar/", name="profile_upload_avatar")
def profile_upload_avatar(request: Request, avatar: UploadFile = File(...)):
    db = SessionLocal()
    user = get_current_user(request, db)
    if not user:
        db.close()
        return RedirectResponse(url="/accounts/login/", status_code=status.HTTP_303_SEE_OTHER)

    suffix = Path(avatar.filename or "").suffix.lower()
    if suffix not in ALLOWED_AVATAR_EXTENSIONS:
        db.close()
        return templates.TemplateResponse(
            request=request,
            name="core/profile.html",
            context={
                "user": user,
                "error": "Разрешены только PNG, JPG, JPEG, WEBP и GIF.",
                "success": None,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    filename = f"{user.id}_{uuid.uuid4().hex}{suffix}"
    target = UPLOADS_DIR / filename
    content = avatar.file.read()
    if len(content) > 2 * 1024 * 1024:
        db.close()
        return templates.TemplateResponse(
            request=request,
            name="core/profile.html",
            context={
                "user": user,
                "error": "Файл слишком большой. Максимум 2MB.",
                "success": None,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    target.write_bytes(content)

    old = user.avatar_filename
    user.avatar_filename = filename
    db.commit()
    db.refresh(user)
    if old:
        old_file = UPLOADS_DIR / old
        if old_file.exists():
            old_file.unlink()
    db.close()
    return templates.TemplateResponse(
        request=request,
        name="core/profile.html",
        context={"user": user, "error": None, "success": "Аватар обновлен."},
    )


@router.get("/account/password/", name="profile_password")
def profile_password_page(request: Request):
    db = SessionLocal()
    user = get_current_user(request, db)
    db.close()
    if not user:
        return RedirectResponse(url="/accounts/login/", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request=request,
        name="core/change_password.html",
        context={"user": user, "error": None, "success": None},
    )


@router.post("/account/password/send-code/", name="profile_send_code")
def profile_send_password_code(request: Request):
    db = SessionLocal()
    user = get_current_user(request, db)
    if not user:
        db.close()
        return RedirectResponse(url="/accounts/login/", status_code=status.HTTP_303_SEE_OTHER)

    user.email_code = generate_email_code()
    user.email_code_expires_at = (utc_now() + timedelta(minutes=10)).isoformat()
    db.commit()
    sent = send_verification_email(user.email, user.email_code)
    db.refresh(user)
    db.close()

    message = (
        "Код отправлен на вашу почту."
        if sent
        else "SMTP не настроен. Код не отправлен."
    )
    return templates.TemplateResponse(
        request=request,
        name="core/change_password.html",
        context={"user": user, "error": None, "success": message},
    )


@router.post("/account/password/update/", name="profile_update_password")
def profile_update_password(
    request: Request,
    code: str = Form(...),
    new_password1: str = Form(...),
    new_password2: str = Form(...),
):
    db = SessionLocal()
    user = get_current_user(request, db)
    if not user:
        db.close()
        return RedirectResponse(url="/accounts/login/", status_code=status.HTTP_303_SEE_OTHER)

    if new_password1 != new_password2:
        db.close()
        return templates.TemplateResponse(
            request=request,
            name="core/change_password.html",
            context={"user": user, "error": "Пароли не совпадают.", "success": None},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if len(new_password1) < 8:
        db.close()
        return templates.TemplateResponse(
            request=request,
            name="core/change_password.html",
            context={
                "user": user,
                "error": "Новый пароль должен быть не короче 8 символов.",
                "success": None,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    expires_at = parse_dt(user.email_code_expires_at)
    if code.strip() != (user.email_code or "") or not expires_at or expires_at < utc_now():
        db.close()
        return templates.TemplateResponse(
            request=request,
            name="core/change_password.html",
            context={
                "user": user,
                "error": "Неверный или просроченный код подтверждения.",
                "success": None,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    user.password_hash = get_password_hash(new_password1)
    user.email_code = None
    user.email_code_expires_at = None
    db.commit()
    db.refresh(user)
    db.close()
    return templates.TemplateResponse(
        request=request,
        name="core/change_password.html",
        context={"user": user, "error": None, "success": "Пароль успешно изменен."},
    )
