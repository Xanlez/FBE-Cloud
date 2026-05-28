from fastapi import APIRouter, Form, Request, status
from fastapi.responses import FileResponse, RedirectResponse

from app.admin_stats import load_admin_dashboard
from app.auth_utils import get_current_user, user_is_personnel
from app.db_utils import SessionLocal
from app.settings import BASE_DIR
from app.user_admin import (
    delete_cloud_file_by_id,
    delete_user_completely,
    set_user_banned,
    set_user_personnel,
)
from app.web import templates
from models import User

router = APIRouter()


def _admin_redirect(request: Request, message: str, *, anchor: str = "admin-users") -> RedirectResponse:
    request.session["admin_message"] = message
    return RedirectResponse(
        url=f"/admin/#{anchor}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


def _require_personnel(request: Request) -> tuple[User | None, RedirectResponse | None]:
    db = SessionLocal()
    try:
        user = get_current_user(request, db)
        if not user:
            return None, RedirectResponse(
                url="/accounts/login/", status_code=status.HTTP_303_SEE_OTHER
            )
        if not user_is_personnel(user):
            return None, RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
        return user, None
    finally:
        db.close()


def _admin_actor_and_target(
    request: Request,
    user_id: int,
    *,
    allow_self: bool = False,
    block_personnel: bool = False,
) -> tuple[int | None, int | None, str | None, RedirectResponse | None]:
    db = SessionLocal()
    try:
        actor = get_current_user(request, db)
        if not actor:
            return None, None, None, RedirectResponse(
                url="/accounts/login/", status_code=status.HTTP_303_SEE_OTHER
            )
        if not user_is_personnel(actor):
            return None, None, None, RedirectResponse(
                url="/", status_code=status.HTTP_303_SEE_OTHER
            )

        target = db.query(User).filter(User.id == user_id).first()
        if not target:
            return actor.id, None, None, _admin_redirect(request, "Пользователь не найден.")

        if not allow_self and actor.id == target.id:
            return actor.id, target.id, target.username, _admin_redirect(
                request, "Нельзя применить действие к своему аккаунту."
            )

        if block_personnel and target.is_personnel:
            return actor.id, target.id, target.username, _admin_redirect(
                request, "Нельзя применить действие к аккаунту персонала."
            )

        return actor.id, target.id, target.username, None
    finally:
        db.close()


@router.get("/", name="home")
def home(request: Request):
    db = SessionLocal()
    user = get_current_user(request, db)
    db.close()
    return templates.TemplateResponse(
        request=request,
        name="core/home.html",
        context={"user": user},
    )


@router.get("/assets/logo-fbe.png", name="logo_fbe")
def logo():
    return FileResponse(BASE_DIR / "logo_FBE.png")


@router.get("/admin/", name="admin")
def admin_panel(request: Request):
    db = SessionLocal()
    user = get_current_user(request, db)
    if not user:
        db.close()
        return RedirectResponse(url="/accounts/login/", status_code=status.HTTP_303_SEE_OTHER)
    if not user_is_personnel(user):
        db.close()
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    dashboard = load_admin_dashboard(db)
    admin_message = request.session.pop("admin_message", None)
    db.close()
    return templates.TemplateResponse(
        request=request,
        name="core/admin.html",
        context={"user": user, "admin_message": admin_message, **dashboard},
    )


@router.post("/admin/", name="admin_action")
def admin_action(
    request: Request,
    action: str = Form(...),
    user_id: int = Form(...),
):
    if action in ("grant_personnel", "revoke_personnel"):
        _actor_id, target_id, username, redirect = _admin_actor_and_target(
            request, user_id, allow_self=False, block_personnel=False,
        )
        if redirect:
            return redirect

        db = SessionLocal()
        target = db.query(User).filter(User.id == target_id).first()
        if action == "grant_personnel":
            if target.is_personnel:
                db.close()
                return _admin_redirect(request, f"{username} уже в персонале.")
            set_user_personnel(db, target_id, True)
            db.close()
            return _admin_redirect(request, f"{username} добавлен в персонал.")

        if not target.is_personnel:
            db.close()
            return _admin_redirect(request, f"{username} не в персонале.")
        set_user_personnel(db, target_id, False)
        db.close()
        return _admin_redirect(request, f"{username} исключён из персонала.")

    _actor_id, target_id, username, redirect = _admin_actor_and_target(
        request, user_id, allow_self=False, block_personnel=True,
    )
    if redirect:
        return redirect

    if action == "ban":
        db = SessionLocal()
        set_user_banned(db, target_id, True)
        db.close()
        if request.session.get("user_id") == target_id:
            request.session.pop("user_id", None)
        return _admin_redirect(request, f"Пользователь {username} заблокирован.")

    if action == "unban":
        db = SessionLocal()
        set_user_banned(db, target_id, False)
        db.close()
        return _admin_redirect(request, f"Пользователь {username} разблокирован.")

    if action == "delete":
        db = SessionLocal()
        delete_user_completely(db, target_id)
        db.close()
        if request.session.get("user_id") == target_id:
            request.session.clear()
        return _admin_redirect(request, f"Пользователь {username} удалён из базы.")

    return _admin_redirect(request, "Неизвестное действие.")


# Старые URL (на случай закладок)
@router.post("/admin/users/{user_id}/ban/", name="admin_user_ban")
def admin_user_ban(request: Request, user_id: int):
    return admin_action(request, action="ban", user_id=user_id)


@router.post("/admin/users/{user_id}/unban/", name="admin_user_unban")
def admin_user_unban(request: Request, user_id: int):
    return admin_action(request, action="unban", user_id=user_id)


@router.post("/admin/users/{user_id}/delete/", name="admin_user_delete")
def admin_user_delete(request: Request, user_id: int):
    return admin_action(request, action="delete", user_id=user_id)


@router.post("/admin/files/{file_id}/delete/", name="admin_file_delete")
def admin_file_delete(request: Request, file_id: int):
    _actor, redirect = _require_personnel(request)
    if redirect:
        return redirect

    db = SessionLocal()
    label = delete_cloud_file_by_id(db, file_id)
    db.close()
    if not label:
        return _admin_redirect(request, "Файл не найден.", anchor="admin-files")
    return _admin_redirect(
        request,
        f"Файл «{label}» удалён.",
        anchor="admin-files",
    )
