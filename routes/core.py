from fastapi import APIRouter, Request, status
from fastapi.responses import FileResponse, RedirectResponse

from app.admin_stats import load_admin_dashboard
from app.auth_utils import get_current_user, user_is_personnel
from app.db_utils import SessionLocal
from app.settings import BASE_DIR
from app.web import templates

router = APIRouter()


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
    db.close()
    return templates.TemplateResponse(
        request=request,
        name="core/admin.html",
        context={"user": user, **dashboard},
    )
