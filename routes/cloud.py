import uuid

from fastapi import APIRouter, File, Form, Request, UploadFile, status
from sqlalchemy import func
from fastapi.responses import FileResponse, RedirectResponse

from app.auth_utils import get_current_user, utc_now
from app.cloud_file_access import user_can_access_file
from app.db_utils import SessionLocal
from app.cloud_query import (
    SORT_OPTIONS,
    SharedFilters,
    list_shared_authors,
    parse_shared_filters,
    parse_shared_filters_from_form,
    query_shared_files,
    shared_cloud_url,
)
from app.event_dates import parse_event_date
from app.flash import apply_flash, redirect_with_flash
from app.file_storage import delete_blob_if_unused, resolve_storage_path, save_upload
from app.upload_limits import (
    check_can_add_files,
    collect_upload_files,
    files_remaining,
    upload_limit_hint,
    validate_upload_file_size,
)
from models import CloudFile, Event, EventParticipant, User
from app.social_utils import (
    are_friends,
    attach_event_creators,
    attach_file_authors,
    can_access_event,
    get_friend_ids,
    load_user_files,
    load_user_files_for_page,
)
from app.web import templates

router = APIRouter()


def _local_drive_file_id() -> str:
    return f"local-{uuid.uuid4().hex}"


def _create_cloud_file(db, user_id: int, meta: dict, visibility: str, event_id: int | None = None):
    row = CloudFile(
        owner_user_id=user_id,
        file_name=meta["file_name"],
        mime_type=meta["mime_type"],
        size_bytes=meta["size_bytes"],
        content_fingerprint=meta["content_fingerprint"],
        storage_name=meta["storage_name"],
        drive_file_id=_local_drive_file_id(),
        web_view_link=None,
        created_at=utc_now().isoformat(),
        visibility=visibility,
        event_id=event_id,
    )
    db.add(row)
    db.commit()
    return row


@router.get("/cloud/download/{file_id}/", name="cloud_file_download")
def cloud_file_download(request: Request, file_id: int):
    db = SessionLocal()
    user = get_current_user(request, db)
    if not user:
        db.close()
        return RedirectResponse(url="/accounts/login/", status_code=status.HTTP_303_SEE_OTHER)

    row = db.query(CloudFile).filter(CloudFile.id == file_id).first()
    if not row or not user_can_access_file(db, user.id, row):
        db.close()
        return RedirectResponse(url="/files/", status_code=status.HTTP_303_SEE_OTHER)

    if row.web_view_link and not row.storage_name:
        db.close()
        return RedirectResponse(url=row.web_view_link, status_code=status.HTTP_303_SEE_OTHER)

    file_name = row.file_name
    mime_type = row.mime_type
    storage_name = row.storage_name or ""
    db.close()

    path = resolve_storage_path(storage_name)
    if not path:
        return RedirectResponse(url="/files/", status_code=status.HTTP_404_NOT_FOUND)

    return FileResponse(
        path,
        filename=file_name,
        media_type=mime_type or "application/octet-stream",
    )


@router.get("/cloud/preview/{file_id}/", name="cloud_file_preview")
def cloud_file_preview(request: Request, file_id: int):
    db = SessionLocal()
    user = get_current_user(request, db)
    if not user:
        db.close()
        return RedirectResponse(url="/accounts/login/", status_code=status.HTTP_303_SEE_OTHER)

    row = db.query(CloudFile).filter(CloudFile.id == file_id).first()
    if not row or not user_can_access_file(db, user.id, row):
        db.close()
        return RedirectResponse(url="/files/", status_code=status.HTTP_303_SEE_OTHER)

    if row.web_view_link and not row.storage_name:
        db.close()
        return RedirectResponse(url=row.web_view_link, status_code=status.HTTP_303_SEE_OTHER)

    file_name = row.file_name
    mime_type = row.mime_type or "application/octet-stream"
    storage_name = row.storage_name or ""
    db.close()

    path = resolve_storage_path(storage_name)
    if not path:
        return RedirectResponse(url="/files/", status_code=status.HTTP_404_NOT_FOUND)

    return FileResponse(
        path,
        filename=file_name,
        media_type=mime_type,
        content_disposition_type="inline",
    )


def _get_owned_shared_file(db, user_id: int, file_id: int) -> CloudFile | None:
    return (
        db.query(CloudFile)
        .filter(
            CloudFile.id == file_id,
            CloudFile.owner_user_id == user_id,
            CloudFile.visibility == "shared",
        )
        .first()
    )


def _get_owned_private_file(db, user_id: int, file_id: int) -> CloudFile | None:
    return (
        db.query(CloudFile)
        .filter(
            CloudFile.id == file_id,
            CloudFile.owner_user_id == user_id,
            CloudFile.visibility == "private",
        )
        .first()
    )


@router.post("/files/{file_id}/rename/", name="files_rename")
def files_rename(request: Request, file_id: int, file_name: str = Form(...)):
    db = SessionLocal()
    user = get_current_user(request, db)
    if not user:
        db.close()
        return RedirectResponse(url="/accounts/login/", status_code=status.HTTP_303_SEE_OTHER)

    row = _get_owned_private_file(db, user.id, file_id)
    new_name = file_name.strip()
    if not row:
        db.close()
        return RedirectResponse(url="/files/", status_code=status.HTTP_303_SEE_OTHER)
    if not new_name:
        db.close()
        return redirect_with_flash(
            "/files/",
            request,
            error="Имя файла не может быть пустым.",
        )
    if len(new_name) > 255:
        new_name = new_name[:255]

    row.file_name = new_name
    db.commit()
    db.close()
    return redirect_with_flash(
        "/files/",
        request,
        success=f"Файл переименован в «{new_name}».",
    )


@router.post("/files/{file_id}/delete/", name="files_delete")
def files_delete(request: Request, file_id: int):
    db = SessionLocal()
    user = get_current_user(request, db)
    if not user:
        db.close()
        return RedirectResponse(url="/accounts/login/", status_code=status.HTTP_303_SEE_OTHER)

    row = _get_owned_private_file(db, user.id, file_id)
    if not row:
        db.close()
        return RedirectResponse(url="/files/", status_code=status.HTTP_303_SEE_OTHER)

    storage_name = row.storage_name
    file_label = row.file_name
    db.delete(row)
    db.commit()
    delete_blob_if_unused(db, storage_name)
    db.close()
    return redirect_with_flash(
        "/files/",
        request,
        success=f"Файл «{file_label}» удалён.",
    )


def _event_detail_url(event_id: int) -> str:
    return f"/cloud/events/{event_id}/"


@router.get("/files/", name="files")
def files_page(request: Request):
    return _files_page_response(request)


def _files_page_response(request: Request, error=None, success=None, status_code=200):
    error, success = apply_flash(request, error, success)
    db = SessionLocal()
    user = get_current_user(request, db)
    if not user:
        db.close()
        return RedirectResponse(url="/accounts/login/", status_code=status.HTTP_303_SEE_OTHER)
    items = load_user_files_for_page(db, user.id)
    limits = {
        "upload_limit_hint": upload_limit_hint(),
        "files_remaining": files_remaining(db, user.id),
    }
    db.close()
    return templates.TemplateResponse(
        request=request,
        name="core/files.html",
        context={
            "user": user,
            "items": items,
            "error": error,
            "success": success,
            **limits,
        },
        status_code=status_code,
    )


@router.post("/files/upload/", name="files_upload")
async def files_upload(request: Request, files: list[UploadFile] = File(default=[])):
    db = SessionLocal()
    user = get_current_user(request, db)
    if not user:
        db.close()
        return RedirectResponse(url="/accounts/login/", status_code=status.HTTP_303_SEE_OTHER)

    if not files:
        form = await request.form()
        single = form.get("file")
        if isinstance(single, UploadFile) and single.filename:
            files = [single]

    uploads = collect_upload_files(files)
    if not uploads:
        db.close()
        return redirect_with_flash(
            "/files/",
            request,
            error="Выберите файл для загрузки.",
        )
    quota_err = check_can_add_files(db, user.id, len(uploads))
    if quota_err:
        db.close()
        return redirect_with_flash("/files/", request, error=quota_err)

    saved = 0
    errors: list[str] = []
    for upload in uploads:
        quota_err = check_can_add_files(db, user.id, 1)
        if quota_err:
            errors.append(quota_err)
            break
        size_err = validate_upload_file_size(upload)
        if size_err:
            errors.append(f"{upload.filename}: {size_err}")
            continue
        meta, error = save_upload(upload, db)
        if error:
            errors.append(f"{upload.filename}: {error}")
            continue
        _create_cloud_file(db, user.id, meta, visibility="private")
        saved += 1

    db.close()
    if saved == 0:
        return redirect_with_flash(
            "/files/",
            request,
            error=errors[0] if len(errors) == 1 else "; ".join(errors),
        )

    if saved == 1:
        success = "Файл загружен."
    else:
        success = f"Загружено файлов: {saved}."
    if errors:
        success += f" Ошибки: {'; '.join(errors)}"
    return redirect_with_flash("/files/", request, success=success)


def _shared_page_response(
    request: Request,
    filters: SharedFilters,
    error=None,
    success=None,
    status_code=200,
):
    error, success = apply_flash(request, error, success)
    db = SessionLocal()
    user = get_current_user(request, db)
    if not user:
        db.close()
        return RedirectResponse(url="/accounts/login/", status_code=status.HTTP_303_SEE_OTHER)
    items, total_count, authors = _shared_page_data(db, filters)
    limits = {
        "upload_limit_hint": upload_limit_hint(),
        "files_remaining": files_remaining(db, user.id),
    }
    db.close()
    return templates.TemplateResponse(
        request=request,
        name="core/shared_cloud.html",
        context={
            "user": user,
            "items": items,
            "filters": filters,
            "total_count": total_count,
            "authors": authors,
            "sort_options": SORT_OPTIONS,
            "error": error,
            "success": success,
            **limits,
        },
        status_code=status_code,
    )


def _shared_page_data(db, filters: SharedFilters):
    items, total = query_shared_files(db, filters)
    authors = list_shared_authors(db)
    return items, total, authors


@router.get("/cloud/shared/", name="shared_cloud")
def shared_cloud_page(request: Request):
    filters = parse_shared_filters(request)
    return _shared_page_response(request, filters)


@router.post("/cloud/shared/{file_id}/rename/", name="shared_cloud_rename")
def shared_cloud_rename(
    request: Request,
    file_id: int,
    file_name: str = Form(...),
    q: str = Form(""),
    author: str = Form(""),
    date: str = Form(""),
    ext: str = Form(""),
    sort: str = Form("date_desc"),
):
    db = SessionLocal()
    user = get_current_user(request, db)
    if not user:
        db.close()
        return RedirectResponse(url="/accounts/login/", status_code=status.HTTP_303_SEE_OTHER)

    filters = parse_shared_filters_from_form(q, author, date, ext, sort)
    row = _get_owned_shared_file(db, user.id, file_id)
    new_name = file_name.strip()
    if not row:
        db.close()
        return RedirectResponse(url=shared_cloud_url(request, filters), status_code=status.HTTP_303_SEE_OTHER)
    if not new_name:
        db.close()
        return redirect_with_flash(
            shared_cloud_url(request, filters),
            request,
            error="Имя файла не может быть пустым.",
        )
    if len(new_name) > 255:
        new_name = new_name[:255]
    row.file_name = new_name
    db.commit()
    db.close()
    return redirect_with_flash(
        shared_cloud_url(request, filters),
        request,
        success=f"Файл переименован в «{new_name}».",
    )


@router.post("/cloud/shared/{file_id}/delete/", name="shared_cloud_delete")
def shared_cloud_delete(
    request: Request,
    file_id: int,
    q: str = Form(""),
    author: str = Form(""),
    date: str = Form(""),
    ext: str = Form(""),
    sort: str = Form("date_desc"),
):
    db = SessionLocal()
    user = get_current_user(request, db)
    if not user:
        db.close()
        return RedirectResponse(url="/accounts/login/", status_code=status.HTTP_303_SEE_OTHER)

    filters = parse_shared_filters_from_form(q, author, date, ext, sort)
    row = _get_owned_shared_file(db, user.id, file_id)
    if not row:
        db.close()
        return RedirectResponse(url=shared_cloud_url(request, filters), status_code=status.HTTP_303_SEE_OTHER)

    storage_name = row.storage_name
    file_label = row.file_name
    db.delete(row)
    db.commit()
    delete_blob_if_unused(db, storage_name)
    db.close()
    return redirect_with_flash(
        shared_cloud_url(request, filters),
        request,
        success=f"Файл «{file_label}» удалён.",
    )


@router.post("/cloud/shared/upload/", name="shared_cloud_upload")
async def shared_cloud_upload(
    request: Request,
    files: list[UploadFile] = File(default=[]),
    q: str = Form(""),
    author: str = Form(""),
    date: str = Form(""),
    ext: str = Form(""),
    sort: str = Form("date_desc"),
):
    db = SessionLocal()
    user = get_current_user(request, db)
    if not user:
        db.close()
        return RedirectResponse(url="/accounts/login/", status_code=status.HTTP_303_SEE_OTHER)

    filters = parse_shared_filters_from_form(q, author, date, ext, sort)

    if not files:
        form = await request.form()
        single = form.get("file")
        if isinstance(single, UploadFile) and single.filename:
            files = [single]

    uploads = collect_upload_files(files)
    redirect_url = shared_cloud_url(request, filters)
    if not uploads:
        db.close()
        return redirect_with_flash(
            redirect_url,
            request,
            error="Выберите файл для загрузки.",
        )
    quota_err = check_can_add_files(db, user.id, len(uploads))
    if quota_err:
        db.close()
        return redirect_with_flash(redirect_url, request, error=quota_err)

    saved = 0
    errors: list[str] = []
    for upload in uploads:
        quota_err = check_can_add_files(db, user.id, 1)
        if quota_err:
            errors.append(quota_err)
            break
        size_err = validate_upload_file_size(upload)
        if size_err:
            errors.append(f"{upload.filename}: {size_err}")
            continue
        meta, error = save_upload(upload, db)
        if error:
            errors.append(f"{upload.filename}: {error}")
            continue
        _create_cloud_file(db, user.id, meta, visibility="shared")
        saved += 1

    db.close()
    if saved == 0:
        return redirect_with_flash(
            redirect_url,
            request,
            error=errors[0] if len(errors) == 1 else "; ".join(errors),
        )

    if saved == 1:
        success = "Файл добавлен в общее облако."
    else:
        success = f"Загружено файлов: {saved}."
    if errors:
        success += f" Ошибки: {'; '.join(errors)}"
    return redirect_with_flash(redirect_url, request, success=success)


@router.get("/cloud/events/", name="events_cloud")
def events_cloud_page(request: Request):
    db = SessionLocal()
    user = get_current_user(request, db)
    if not user:
        db.close()
        return RedirectResponse(url="/accounts/login/", status_code=status.HTTP_303_SEE_OTHER)
    all_events = db.query(Event).all()
    events = sorted(
        [e for e in all_events if can_access_event(db, user.id, e)],
        key=lambda e: (e.event_date is None, e.event_date or "9999-12-31", -e.id),
    )
    attach_event_creators(db, events)
    db.close()
    return templates.TemplateResponse(
        request=request,
        name="core/events_cloud.html",
        context={"user": user, "events": events, "error": None, "success": None},
    )


@router.post("/cloud/events/create/", name="events_cloud_create")
def events_cloud_create(
    request: Request,
    title: str = Form(...),
    description: str = Form(""),
    event_date: str = Form(...),
    is_private: str = Form("0"),
):
    db = SessionLocal()
    user = get_current_user(request, db)
    if not user:
        db.close()
        return RedirectResponse(url="/accounts/login/", status_code=status.HTTP_303_SEE_OTHER)

    title_clean = title.strip()
    parsed_date = parse_event_date(event_date)
    if not title_clean or not parsed_date:
        all_events = db.query(Event).all()
        events = sorted(
            [e for e in all_events if can_access_event(db, user.id, e)],
            key=lambda e: (e.event_date is None, e.event_date or "9999-12-31", -e.id),
        )
        attach_event_creators(db, events)
        error = "Введите название события." if not title_clean else "Выберите дату в календаре."
        db.close()
        return templates.TemplateResponse(
            request=request,
            name="core/events_cloud.html",
            context={
                "user": user,
                "events": events,
                "error": error,
                "success": None,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    new_event = Event(
        title=title_clean,
        description=description.strip(),
        event_date=parsed_date,
        creator_user_id=user.id,
        created_at=utc_now().isoformat(),
        is_private=is_private == "1",
    )
    db.add(new_event)
    db.commit()
    db.refresh(new_event)
    participant = EventParticipant(
        event_id=new_event.id,
        user_id=user.id,
        added_by_user_id=user.id,
        created_at=utc_now().isoformat(),
    )
    db.add(participant)
    db.commit()
    event_id = new_event.id
    db.close()
    return RedirectResponse(url=f"/cloud/events/{event_id}/", status_code=status.HTTP_303_SEE_OTHER)


def _load_event_items(db, event_id: int) -> list[CloudFile]:
    items = (
        db.query(CloudFile)
        .filter(CloudFile.event_id == event_id, CloudFile.visibility == "event")
        .order_by(CloudFile.id.desc())
        .all()
    )
    return attach_file_authors(db, items)


def _get_event_file(db, event_id: int, file_id: int) -> CloudFile | None:
    return (
        db.query(CloudFile)
        .filter(
            CloudFile.id == file_id,
            CloudFile.event_id == event_id,
            CloudFile.visibility == "event",
        )
        .first()
    )


def _user_can_manage_event_file(db, user_id: int, row: CloudFile, event: Event) -> bool:
    if row.visibility != "event" or row.event_id != event.id:
        return False
    if not can_access_event(db, user_id, event):
        return False
    return event.creator_user_id == user_id or row.owner_user_id == user_id


def _event_detail_context(
    db,
    user: User,
    event: Event,
    event_id: int,
    error=None,
    success=None,
    show_edit: bool = False,
):
    items = _load_event_items(db, event_id)
    friend_ids = get_friend_ids(db, user.id)
    friends = (
        db.query(User).filter(User.id.in_(friend_ids)).order_by(User.username.asc()).all()
        if friend_ids
        else []
    )
    participant_rows = (
        db.query(EventParticipant).filter(EventParticipant.event_id == event_id).all()
    )
    participant_ids = {p.user_id for p in participant_rows}
    participant_user_ids = list(participant_ids)
    participants = (
        db.query(User).filter(User.id.in_(participant_user_ids)).order_by(User.username.asc()).all()
        if participant_user_ids
        else []
    )
    attachable_files = load_user_files(db, user.id)
    addable_friends = [f for f in friends if f.id not in participant_ids]
    return {
        "user": user,
        "event": event,
        "is_creator": event.creator_user_id == user.id,
        "items": items,
        "friends": friends,
        "addable_friends": addable_friends,
        "participants": participants,
        "participant_ids": participant_ids,
        "attachable_files": attachable_files,
        "error": error,
        "success": success,
        "show_edit": show_edit,
        "upload_limit_hint": upload_limit_hint(),
        "files_remaining": files_remaining(db, user.id),
    }


def _get_event_if_creator(db, user_id: int, event_id: int) -> Event | None:
    return (
        db.query(Event)
        .filter(Event.id == event_id, Event.creator_user_id == user_id)
        .first()
    )


def _delete_event_completely(db, event_id: int) -> None:
    files = db.query(CloudFile).filter(CloudFile.event_id == event_id).all()
    for row in files:
        storage_name = row.storage_name
        db.delete(row)
        db.flush()
        delete_blob_if_unused(db, storage_name)
    db.query(EventParticipant).filter(EventParticipant.event_id == event_id).delete()
    db.query(Event).filter(Event.id == event_id).delete()
    db.commit()


def _event_detail_response(
    request: Request,
    event_id: int,
    error=None,
    success=None,
    status_code=200,
    show_edit: bool | None = None,
):
    error, success = apply_flash(request, error, success)
    db = SessionLocal()
    user = get_current_user(request, db)
    if not user:
        db.close()
        return RedirectResponse(url="/accounts/login/", status_code=status.HTTP_303_SEE_OTHER)
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        db.close()
        return RedirectResponse(url="/cloud/events/", status_code=status.HTTP_303_SEE_OTHER)
    if not can_access_event(db, user.id, event):
        db.close()
        return RedirectResponse(url="/cloud/events/", status_code=status.HTTP_303_SEE_OTHER)
    if show_edit is None:
        show_edit = request.query_params.get("edit") == "1"
    if error and event.creator_user_id == user.id:
        show_edit = True
    ctx = _event_detail_context(
        db, user, event, event_id, error=error, success=success, show_edit=show_edit
    )
    db.close()
    return templates.TemplateResponse(
        request=request,
        name="core/event_detail.html",
        context=ctx,
        status_code=status_code,
    )


@router.get("/cloud/events/{event_id}/", name="event_detail")
def event_detail_page(request: Request, event_id: int):
    return _event_detail_response(request, event_id)


@router.post("/cloud/events/{event_id}/upload/", name="event_upload")
async def event_upload(request: Request, event_id: int, files: list[UploadFile] = File(default=[])):
    db = SessionLocal()
    user = get_current_user(request, db)
    if not user:
        db.close()
        return RedirectResponse(url="/accounts/login/", status_code=status.HTTP_303_SEE_OTHER)
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        db.close()
        return RedirectResponse(url="/cloud/events/", status_code=status.HTTP_303_SEE_OTHER)
    if not can_access_event(db, user.id, event):
        db.close()
        return RedirectResponse(url="/cloud/events/", status_code=status.HTTP_303_SEE_OTHER)

    if not files:
        form = await request.form()
        single = form.get("file")
        if isinstance(single, UploadFile) and single.filename:
            files = [single]

    uploads = collect_upload_files(files)
    event_url = _event_detail_url(event_id)
    if not uploads:
        db.close()
        return redirect_with_flash(event_url, request, error="Выберите файл.")
    quota_err = check_can_add_files(db, user.id, len(uploads))
    if quota_err:
        db.close()
        return redirect_with_flash(event_url, request, error=quota_err)

    saved = 0
    errors: list[str] = []
    for upload in uploads:
        quota_err = check_can_add_files(db, user.id, 1)
        if quota_err:
            errors.append(quota_err)
            break
        size_err = validate_upload_file_size(upload)
        if size_err:
            errors.append(f"{upload.filename}: {size_err}")
            continue
        meta, err = save_upload(upload, db)
        if err:
            errors.append(f"{upload.filename}: {err}")
            continue
        _create_cloud_file(db, user.id, meta, visibility="event", event_id=event_id)
        saved += 1

    db.close()
    if saved == 0:
        return redirect_with_flash(
            event_url,
            request,
            error=errors[0] if len(errors) == 1 else "; ".join(errors),
        )

    if saved == 1:
        success = "Файл загружен."
    else:
        success = f"Загружено файлов: {saved}."
    if errors:
        success += f" Ошибки: {'; '.join(errors)}"
    return redirect_with_flash(event_url, request, success=success)


@router.post("/cloud/events/{event_id}/attach-existing/", name="event_attach_existing")
def event_attach_existing(request: Request, event_id: int, file_id: int = Form(...)):
    db = SessionLocal()
    user = get_current_user(request, db)
    if not user:
        db.close()
        return RedirectResponse(url="/accounts/login/", status_code=status.HTTP_303_SEE_OTHER)
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event or not can_access_event(db, user.id, event):
        db.close()
        return RedirectResponse(url="/cloud/events/", status_code=status.HTTP_303_SEE_OTHER)
    source = (
        db.query(CloudFile)
        .filter(CloudFile.id == file_id, CloudFile.owner_user_id == user.id)
        .first()
    )
    quota_err = check_can_add_files(db, user.id, 1)
    if quota_err:
        db.close()
        return redirect_with_flash(_event_detail_url(event_id), request, error=quota_err)
    if source and (source.storage_name or source.web_view_link):
        row = CloudFile(
            owner_user_id=user.id,
            file_name=source.file_name,
            mime_type=source.mime_type,
            size_bytes=source.size_bytes,
            content_fingerprint=source.content_fingerprint,
            storage_name=source.storage_name,
            drive_file_id=_local_drive_file_id() if source.storage_name else source.drive_file_id,
            web_view_link=source.web_view_link if not source.storage_name else None,
            created_at=utc_now().isoformat(),
            visibility="event",
            event_id=event_id,
        )
        db.add(row)
        db.commit()
    db.close()
    return RedirectResponse(url=f"/cloud/events/{event_id}/", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/cloud/events/{event_id}/files/{file_id}/rename/", name="event_file_rename")
def event_file_rename(
    request: Request,
    event_id: int,
    file_id: int,
    file_name: str = Form(...),
):
    db = SessionLocal()
    user = get_current_user(request, db)
    if not user:
        db.close()
        return RedirectResponse(url="/accounts/login/", status_code=status.HTTP_303_SEE_OTHER)

    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        db.close()
        return RedirectResponse(url="/cloud/events/", status_code=status.HTTP_303_SEE_OTHER)

    row = _get_event_file(db, event_id, file_id)
    new_name = file_name.strip()
    event_url = _event_detail_url(event_id)
    if not row or not _user_can_manage_event_file(db, user.id, row, event):
        db.close()
        return redirect_with_flash(
            event_url,
            request,
            error="Нельзя переименовать этот файл.",
        )
    if not new_name:
        db.close()
        return redirect_with_flash(
            event_url,
            request,
            error="Имя файла не может быть пустым.",
        )

    row.file_name = new_name[:255]
    db.commit()
    db.close()
    return redirect_with_flash(
        event_url,
        request,
        success=f"Файл переименован в «{new_name[:255]}».",
    )


@router.post("/cloud/events/{event_id}/files/{file_id}/delete/", name="event_file_delete")
def event_file_delete(request: Request, event_id: int, file_id: int):
    db = SessionLocal()
    user = get_current_user(request, db)
    if not user:
        db.close()
        return RedirectResponse(url="/accounts/login/", status_code=status.HTTP_303_SEE_OTHER)

    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        db.close()
        return RedirectResponse(url="/cloud/events/", status_code=status.HTTP_303_SEE_OTHER)

    row = _get_event_file(db, event_id, file_id)
    event_url = _event_detail_url(event_id)
    if not row or not _user_can_manage_event_file(db, user.id, row, event):
        db.close()
        return redirect_with_flash(
            event_url,
            request,
            error="Нельзя удалить этот файл.",
        )

    file_label = row.file_name
    storage_name = row.storage_name
    db.delete(row)
    db.commit()
    delete_blob_if_unused(db, storage_name)
    db.close()
    return redirect_with_flash(
        event_url,
        request,
        success=f"Файл «{file_label}» удалён из события.",
    )


@router.post("/cloud/events/{event_id}/add-participant/", name="event_add_participant")
def event_add_participant(
    request: Request,
    event_id: int,
    friend_id: str = Form(""),
    username: str = Form(""),
):
    db = SessionLocal()
    user = get_current_user(request, db)
    if not user:
        db.close()
        return RedirectResponse(url="/accounts/login/", status_code=status.HTTP_303_SEE_OTHER)

    event = db.query(Event).filter(Event.id == event_id).first()
    if not event or event.creator_user_id != user.id:
        db.close()
        return RedirectResponse(url="/cloud/events/", status_code=status.HTTP_303_SEE_OTHER)
    event_url = _event_detail_url(event_id)
    if not event.is_private:
        db.close()
        return redirect_with_flash(
            event_url,
            request,
            error="Участников можно добавлять только в закрытые события.",
        )

    target: User | None = None
    friend_raw = friend_id.strip()
    username_clean = username.strip()

    if friend_raw:
        try:
            friend_pk = int(friend_raw)
        except ValueError:
            db.close()
            return redirect_with_flash(
                event_url,
                request,
                error="Некорректный выбор из списка друзей.",
            )
        if not are_friends(db, user.id, friend_pk):
            db.close()
            return redirect_with_flash(
                event_url,
                request,
                error="Из списка можно добавить только друзей.",
            )
        target = db.query(User).filter(User.id == friend_pk).first()
    elif username_clean:
        target = (
            db.query(User)
            .filter(func.lower(User.username) == username_clean.lower())
            .first()
        )
        if not target:
            db.close()
            return redirect_with_flash(
                event_url,
                request,
                error=f"Пользователь «{username_clean}» не найден.",
            )
    else:
        db.close()
        return redirect_with_flash(
            event_url,
            request,
            error="Выберите друга из списка или введите логин пользователя.",
        )

    if target.id in {
        p.user_id
        for p in db.query(EventParticipant).filter(EventParticipant.event_id == event_id).all()
    }:
        db.close()
        return redirect_with_flash(
            event_url,
            request,
            error=f"«{target.username}» уже в списке участников.",
        )

    db.add(
        EventParticipant(
            event_id=event_id,
            user_id=target.id,
            added_by_user_id=user.id,
            created_at=utc_now().isoformat(),
        )
    )
    added_username = target.username
    db.commit()
    db.close()
    return redirect_with_flash(
        event_url,
        request,
        success=f"«{added_username}» добавлен в участники.",
    )


@router.post("/cloud/events/{event_id}/rename/", name="event_rename")
def event_rename(
    request: Request,
    event_id: int,
    title: str = Form(...),
    description: str = Form(""),
    event_date: str = Form(...),
):
    db = SessionLocal()
    user = get_current_user(request, db)
    if not user:
        db.close()
        return RedirectResponse(url="/accounts/login/", status_code=status.HTTP_303_SEE_OTHER)

    event = _get_event_if_creator(db, user.id, event_id)
    if not event:
        db.close()
        return RedirectResponse(url="/cloud/events/", status_code=status.HTTP_303_SEE_OTHER)

    title_clean = title.strip()
    parsed_date = parse_event_date(event_date)
    event_url = _event_detail_url(event_id)
    if not title_clean or not parsed_date:
        error = "Название не может быть пустым." if not title_clean else "Выберите дату в календаре."
        db.close()
        return redirect_with_flash(event_url, request, error=error)

    event.title = title_clean[:255]
    event.description = description.strip()[:1000]
    event.event_date = parsed_date
    db.commit()
    db.close()
    return redirect_with_flash(event_url, request, success="Событие обновлено.")


@router.post("/cloud/events/{event_id}/delete/", name="event_delete")
def event_delete(request: Request, event_id: int):
    db = SessionLocal()
    user = get_current_user(request, db)
    if not user:
        db.close()
        return RedirectResponse(url="/accounts/login/", status_code=status.HTTP_303_SEE_OTHER)

    event = _get_event_if_creator(db, user.id, event_id)
    if not event:
        db.close()
        return RedirectResponse(url="/cloud/events/", status_code=status.HTTP_303_SEE_OTHER)

    _delete_event_completely(db, event_id)
    db.close()
    return RedirectResponse(url="/cloud/events/", status_code=status.HTTP_303_SEE_OTHER)
