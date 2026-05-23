from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.db_utils import ensure_users_table_columns, engine
from app.settings import BASE_DIR, DATA_DIR, SECRET_KEY, UPLOADS_DIR
from models import Base
from routes.accounts import router as accounts_router
from routes.cloud import router as cloud_router
from routes.core import router as core_router
from routes.profile import router as profile_router
from routes.social import router as social_router

app = FastAPI(title="FBE cloud")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")

app.include_router(core_router)
app.include_router(accounts_router)
app.include_router(profile_router)
app.include_router(cloud_router)
app.include_router(social_router)


@app.on_event("startup")
def startup():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    ensure_users_table_columns()
