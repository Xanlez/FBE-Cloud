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
from app.integrations import send_verification_email
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
    send_verification_email(new_user.email, new_user.email_code or "")
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


@router.get("/accounts/verify-email/", name="verify_email")
def verify_email_page(request: Request):
    pending_id = request.session.get("pending_verify_user_id")
    if not pending_id:
        return RedirectResponse(url="/accounts/login/", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request=request,
        name="core/verify_email.html",
        context={"error": None, "email_hint": None, "user": None},
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
            context={
                "error": "Неверный или просроченный код. Запросите новый.",
                "email_hint": user.email,
                "user": None,
            },
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
    db.close()

    message = (
        "Новый код отправлен на почту."
        if sent
        else "SMTP не настроен. Код не отправлен."
    )
    return templates.TemplateResponse(
        request=request,
        name="core/verify_email.html",
        context={"error": message, "email_hint": user.email, "user": None},
    )
