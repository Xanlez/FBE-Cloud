from datetime import timedelta

from fastapi import APIRouter, Form, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import or_

from app.auth_utils import (
    generate_email_code,
    get_current_user,
    get_password_hash,
    parse_dt,
    utc_now,
    verify_password,
)
from app.db_utils import SessionLocal
from app.integrations import send_password_reset_email, send_verification_email
from models import User
from app.web import templates

router = APIRouter()


@router.get("/accounts/register/", name="register")
def register_page(request: Request):
    db = SessionLocal()
    user = get_current_user(request, db)
    db.close()
    if user:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request=request,
        name="core/register.html",
        context={"errors": {}, "values": {}, "user": None},
    )


@router.post("/accounts/register/", name="register_post")
def register(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password1: str = Form(...),
    password2: str = Form(...),
):
    db = SessionLocal()
    errors = {}
    values = {"username": username, "email": email}

    username = username.strip()
    email = email.strip().lower()

    if not username:
        errors["username"] = "Введите имя пользователя."
    if "@" not in email:
        errors["email"] = "Введите корректный email."
    if password1 != password2:
        errors["password2"] = "Пароли не совпадают."
    if len(password1) < 8:
        errors["password1"] = "Пароль должен быть не короче 8 символов."
    if db.query(User).filter(User.username == username).first():
        errors["username"] = "Пользователь с таким логином уже существует."
    if db.query(User).filter(User.email == email).first():
        errors["email"] = "Пользователь с таким email уже существует."

    if errors:
        db.close()
        return templates.TemplateResponse(
            request=request,
            name="core/register.html",
            context={"errors": errors, "values": values, "user": None},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    new_user = User(
        username=username,
        email=email,
        password_hash=get_password_hash(password1),
        is_staff=False,
        is_personnel=False,
        is_email_verified=False,
        email_code=generate_email_code(),
        email_code_expires_at=(utc_now() + timedelta(minutes=10)).isoformat(),
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    request.session["pending_verify_user_id"] = new_user.id
    sent = send_verification_email(new_user.email, new_user.email_code or "")
    request.session["verify_email_sent"] = sent
    db.close()
    return RedirectResponse(
        url="/accounts/verify-email/",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/accounts/login/", name="login")
def login_page(request: Request):
    db = SessionLocal()
    user = get_current_user(request, db)
    db.close()
    if user:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request=request,
        name="core/login.html",
        context={"error": None, "value": "", "user": None},
    )


@router.post("/accounts/login/", name="login_post")
def login(
    request: Request,
    identifier: str = Form(...),
    password: str = Form(...),
):
    db = SessionLocal()
    value = identifier.strip()
    email_or_login = value.lower()
    user = (
        db.query(User)
        .filter(or_(User.username == value, User.email == email_or_login))
        .first()
    )

    if not user or not verify_password(password, user.password_hash):
        db.close()
        return templates.TemplateResponse(
            request=request,
            name="core/login.html",
            context={
                "error": "Неверный логин/email или пароль.",
                "value": value,
                "user": None,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if user.is_banned:
        db.close()
        return templates.TemplateResponse(
            request=request,
            name="core/login.html",
            context={
                "error": "Аккаунт заблокирован администратором.",
                "value": value,
                "user": None,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if not user.is_email_verified:
        request.session["pending_verify_user_id"] = user.id
        db.close()
        return templates.TemplateResponse(
            request=request,
            name="core/login.html",
            context={
                "error": "Подтвердите почту кодом из письма перед входом.",
                "value": value,
                "user": None,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    request.session["user_id"] = user.id
    db.close()
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/accounts/logout/", name="logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


def _reset_password_context(request: Request, *, error=None, email_hint=None):
    pending_id = request.session.get("pending_reset_user_id")
    info = None
    dev_code = None
    sent_flag = request.session.pop("reset_email_sent", None)
    if sent_flag is True:
        info = "Код отправлен на почту. Проверьте входящие и папку «Спам»."
    elif sent_flag is False:
        info = "Письмо не отправлено: SMTP не настроен в файле .env на сервере."

    if pending_id and email_hint is None:
        db = SessionLocal()
        user = db.query(User).filter(User.id == pending_id).first()
        db.close()
        if user:
            email_hint = user.email
            if sent_flag is False:
                dev_code = user.email_code

    return {
        "error": error,
        "info": info,
        "email_hint": email_hint,
        "dev_code": dev_code,
        "user": None,
    }


@router.get("/accounts/forgot-password/", name="forgot_password")
def forgot_password_page(request: Request):
    db = SessionLocal()
    user = get_current_user(request, db)
    db.close()
    if user:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request=request,
        name="core/forgot_password.html",
        context={"error": None, "info": None, "value": "", "user": None},
    )


@router.post("/accounts/forgot-password/", name="forgot_password_post")
def forgot_password(request: Request, email: str = Form(...)):
    db = SessionLocal()
    user = get_current_user(request, db)
    if user:
        db.close()
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    email_clean = email.strip().lower()
    if "@" not in email_clean:
        db.close()
        return templates.TemplateResponse(
            request=request,
            name="core/forgot_password.html",
            context={
                "error": "Введите корректный email.",
                "info": None,
                "value": email,
                "user": None,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    account = db.query(User).filter(User.email == email_clean).first()
    if account and not account.is_banned:
        account.email_code = generate_email_code()
        account.email_code_expires_at = (utc_now() + timedelta(minutes=10)).isoformat()
        db.commit()
        sent = send_password_reset_email(account.email, account.email_code or "")
        request.session["pending_reset_user_id"] = account.id
        request.session["reset_email_sent"] = sent
        db.close()
        return RedirectResponse(
            url="/accounts/reset-password/",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    db.close()
    return templates.TemplateResponse(
        request=request,
        name="core/forgot_password.html",
        context={
            "error": None,
            "info": "Если аккаунт с такой почтой существует, мы отправили код для сброса пароля.",
            "value": email,
            "user": None,
        },
    )


@router.get("/accounts/reset-password/", name="reset_password")
def reset_password_page(request: Request):
    pending_id = request.session.get("pending_reset_user_id")
    if not pending_id:
        return RedirectResponse(
            url="/accounts/forgot-password/",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return templates.TemplateResponse(
        request=request,
        name="core/reset_password.html",
        context=_reset_password_context(request),
    )


@router.post("/accounts/reset-password/", name="reset_password_post")
def reset_password(
    request: Request,
    code: str = Form(...),
    new_password1: str = Form(...),
    new_password2: str = Form(...),
):
    pending_id = request.session.get("pending_reset_user_id")
    if not pending_id:
        return RedirectResponse(
            url="/accounts/forgot-password/",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    db = SessionLocal()
    user = db.query(User).filter(User.id == pending_id).first()
    if not user:
        db.close()
        request.session.pop("pending_reset_user_id", None)
        return RedirectResponse(
            url="/accounts/forgot-password/",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    if user.is_banned:
        db.close()
        request.session.pop("pending_reset_user_id", None)
        return templates.TemplateResponse(
            request=request,
            name="core/reset_password.html",
            context=_reset_password_context(
                request,
                error="Аккаунт заблокирован. Сброс пароля недоступен.",
                email_hint=user.email,
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if new_password1 != new_password2:
        db.close()
        return templates.TemplateResponse(
            request=request,
            name="core/reset_password.html",
            context=_reset_password_context(
                request,
                error="Пароли не совпадают.",
                email_hint=user.email,
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if len(new_password1) < 8:
        db.close()
        return templates.TemplateResponse(
            request=request,
            name="core/reset_password.html",
            context=_reset_password_context(
                request,
                error="Пароль должен быть не короче 8 символов.",
                email_hint=user.email,
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    expires_at = parse_dt(user.email_code_expires_at)
    entered = code.strip()
    if entered != (user.email_code or "") or not expires_at or expires_at < utc_now():
        db.close()
        return templates.TemplateResponse(
            request=request,
            name="core/reset_password.html",
            context=_reset_password_context(
                request,
                error="Неверный или просроченный код. Запросите новый.",
                email_hint=user.email,
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    user.password_hash = get_password_hash(new_password1)
    user.email_code = None
    user.email_code_expires_at = None
    db.commit()
    db.close()
    request.session.pop("pending_reset_user_id", None)
    request.session["user_id"] = user.id
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/accounts/reset-password/resend/", name="reset_password_resend")
def reset_password_resend(request: Request):
    pending_id = request.session.get("pending_reset_user_id")
    if not pending_id:
        return RedirectResponse(
            url="/accounts/forgot-password/",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    db = SessionLocal()
    user = db.query(User).filter(User.id == pending_id).first()
    if not user:
        db.close()
        request.session.pop("pending_reset_user_id", None)
        return RedirectResponse(
            url="/accounts/forgot-password/",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    user.email_code = generate_email_code()
    user.email_code_expires_at = (utc_now() + timedelta(minutes=10)).isoformat()
    db.commit()
    sent = send_password_reset_email(user.email, user.email_code)
    email_hint = user.email
    dev_code = None if sent else user.email_code
    db.close()

    return templates.TemplateResponse(
        request=request,
        name="core/reset_password.html",
        context={
            "error": None,
            "info": (
                "Новый код отправлен на почту."
                if sent
                else "SMTP не настроен. Письмо не отправлено."
            ),
            "email_hint": email_hint,
            "dev_code": dev_code,
            "user": None,
        },
    )


def _verify_email_context(request: Request, *, error=None, email_hint=None):
    pending_id = request.session.get("pending_verify_user_id")
    info = None
    dev_code = None
    sent_flag = request.session.pop("verify_email_sent", None)
    if sent_flag is True:
        info = "Код отправлен на почту. Проверьте входящие и папку «Спам»."
    elif sent_flag is False:
        info = "Письмо не отправлено: SMTP не настроен в файле .env на сервере."

    if pending_id and email_hint is None:
        db = SessionLocal()
        user = db.query(User).filter(User.id == pending_id).first()
        db.close()
        if user:
            email_hint = user.email
            if sent_flag is False:
                dev_code = user.email_code

    return {
        "error": error,
        "info": info,
        "email_hint": email_hint,
        "dev_code": dev_code,
        "user": None,
    }


@router.get("/accounts/verify-email/", name="verify_email")
def verify_email_page(request: Request):
    pending_id = request.session.get("pending_verify_user_id")
    if not pending_id:
        return RedirectResponse(url="/accounts/login/", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request=request,
        name="core/verify_email.html",
        context=_verify_email_context(request),
    )


@router.post("/accounts/verify-email/", name="verify_email_post")
def verify_email(request: Request, code: str = Form(...)):
    pending_id = request.session.get("pending_verify_user_id")
    if not pending_id:
        return RedirectResponse(url="/accounts/login/", status_code=status.HTTP_303_SEE_OTHER)

    db = SessionLocal()
    user = db.query(User).filter(User.id == pending_id).first()
    if not user:
        db.close()
        request.session.pop("pending_verify_user_id", None)
        return RedirectResponse(url="/accounts/register/", status_code=status.HTTP_303_SEE_OTHER)

    expires_at = parse_dt(user.email_code_expires_at)
    entered = code.strip()
    if entered != (user.email_code or "") or not expires_at or expires_at < utc_now():
        db.close()
        return templates.TemplateResponse(
            request=request,
            name="core/verify_email.html",
            context=_verify_email_context(
                request,
                error="Неверный или просроченный код. Запросите новый.",
                email_hint=user.email,
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    user.is_email_verified = True
    user.email_code = None
    user.email_code_expires_at = None
    db.commit()
    request.session["user_id"] = user.id
    request.session.pop("pending_verify_user_id", None)
    db.close()
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/accounts/verify-email/resend/", name="verify_email_resend")
def resend_verify_email(request: Request):
    pending_id = request.session.get("pending_verify_user_id")
    if not pending_id:
        return RedirectResponse(url="/accounts/login/", status_code=status.HTTP_303_SEE_OTHER)

    db = SessionLocal()
    user = db.query(User).filter(User.id == pending_id).first()
    if not user:
        db.close()
        request.session.pop("pending_verify_user_id", None)
        return RedirectResponse(url="/accounts/register/", status_code=status.HTTP_303_SEE_OTHER)

    user.email_code = generate_email_code()
    user.email_code_expires_at = (utc_now() + timedelta(minutes=10)).isoformat()
    db.commit()
    sent = send_verification_email(user.email, user.email_code)
    email_hint = user.email
    dev_code = None if sent else user.email_code
    db.close()

    return templates.TemplateResponse(
        request=request,
        name="core/verify_email.html",
        context={
            "error": None,
            "info": (
                "Новый код отправлен на почту."
                if sent
                else "SMTP не настроен. Письмо не отправлено."
            ),
            "email_hint": email_hint,
            "dev_code": dev_code,
            "user": None,
        },
    )
