from fastapi import APIRouter, Form, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import or_

from app.auth_utils import get_current_user, utc_now
from app.chat_utils import load_chat_messages, load_own_files_for_chat
from app.db_utils import SessionLocal
from models import CloudFile, FriendRequest, Friendship, Message, User
from app.social_utils import are_friends, get_friend_ids
from app.web import templates

router = APIRouter()


def _social_context(
    db,
    request: Request,
    user: User,
    q: str = "",
    chat_id: int | None = None,
):
    friend_ids = get_friend_ids(db, user.id)
    friends = (
        db.query(User).filter(User.id.in_(friend_ids)).order_by(User.username.asc()).all()
        if friend_ids
        else []
    )
    incoming = (
        db.query(FriendRequest)
        .filter(FriendRequest.to_user_id == user.id, FriendRequest.status == "pending")
        .order_by(FriendRequest.id.desc())
        .all()
    )
    incoming_users = {}
    if incoming:
        from_ids = [r.from_user_id for r in incoming]
        users = db.query(User).filter(User.id.in_(from_ids)).all()
        incoming_users = {u.id: u for u in users}

    search_results = []
    if q.strip():
        query_text = q.strip()
        candidates = (
            db.query(User)
            .filter(User.id != user.id, User.username.like(f"%{query_text}%"))
            .order_by(User.username.asc())
            .limit(20)
            .all()
        )
        outgoing_rows = (
            db.query(FriendRequest)
            .filter(FriendRequest.from_user_id == user.id, FriendRequest.status == "pending")
            .all()
        )
        outgoing_set = {r.to_user_id for r in outgoing_rows}
        incoming_set = {r.from_user_id for r in incoming}
        friend_set = set(friend_ids)
        for candidate in candidates:
            status_label = "none"
            if candidate.id in friend_set:
                status_label = "friend"
            elif candidate.id in outgoing_set:
                status_label = "sent"
            elif candidate.id in incoming_set:
                status_label = "incoming"
            search_results.append({"user": candidate, "status": status_label})

    active_friend = None
    messages = []
    own_files = []
    is_saved_chat = False
    active_chat_id = None

    if chat_id == user.id:
        is_saved_chat = True
        active_friend = user
        active_chat_id = user.id
        messages = load_chat_messages(db, request, user.id, user.id)
        own_files = load_own_files_for_chat(db, user.id)
    elif chat_id and chat_id in friend_ids:
        active_friend = db.query(User).filter(User.id == chat_id).first()
        if active_friend:
            active_chat_id = chat_id
            messages = load_chat_messages(db, request, user.id, chat_id)
            own_files = load_own_files_for_chat(db, user.id)

    return {
        "user": user,
        "friends": friends,
        "incoming": incoming,
        "incoming_users": incoming_users,
        "search_results": search_results,
        "query": q,
        "active_friend": active_friend,
        "active_chat_id": active_chat_id,
        "is_saved_chat": is_saved_chat,
        "messages": messages,
        "own_files": own_files,
        "error": None,
        "success": None,
    }


@router.get("/social/", name="social")
def social_page(request: Request, q: str = "", chat: int | None = None):
    db = SessionLocal()
    user = get_current_user(request, db)
    if not user:
        db.close()
        return RedirectResponse(url="/accounts/login/", status_code=status.HTTP_303_SEE_OTHER)

    context = _social_context(db, request, user, q=q, chat_id=chat)
    db.close()
    return templates.TemplateResponse(
        request=request,
        name="core/social.html",
        context=context,
    )


@router.get("/social/chat/{friend_id}/", name="social_chat")
def social_chat_redirect(request: Request, friend_id: int):
    return RedirectResponse(
        url=f"/social/?chat={friend_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/favorites/", name="favorites_redirect")
@router.get("/favorites")
def favorites_redirect(request: Request):
    db = SessionLocal()
    user = get_current_user(request, db)
    db.close()
    if not user:
        return RedirectResponse(url="/accounts/login/", status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(
        url=f"/social/?chat={user.id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/social/friends/request/{target_user_id}", name="social_request_friend")
def social_request_friend(request: Request, target_user_id: int):
    db = SessionLocal()
    user = get_current_user(request, db)
    if not user:
        db.close()
        return RedirectResponse(url="/accounts/login/", status_code=status.HTTP_303_SEE_OTHER)
    if target_user_id == user.id or are_friends(db, user.id, target_user_id):
        db.close()
        return RedirectResponse(url="/social/", status_code=status.HTTP_303_SEE_OTHER)

    existing = (
        db.query(FriendRequest)
        .filter(
            FriendRequest.status == "pending",
            or_(
                ((FriendRequest.from_user_id == user.id) & (FriendRequest.to_user_id == target_user_id)),
                ((FriendRequest.from_user_id == target_user_id) & (FriendRequest.to_user_id == user.id)),
            ),
        )
        .first()
    )
    if not existing:
        db.add(
            FriendRequest(
                from_user_id=user.id,
                to_user_id=target_user_id,
                status="pending",
                created_at=utc_now().isoformat(),
            )
        )
        db.commit()
    db.close()
    return RedirectResponse(url="/social/", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/social/friends/accept/{request_id}", name="social_accept_friend")
def social_accept_friend(request: Request, request_id: int):
    db = SessionLocal()
    user = get_current_user(request, db)
    if not user:
        db.close()
        return RedirectResponse(url="/accounts/login/", status_code=status.HTTP_303_SEE_OTHER)

    req = (
        db.query(FriendRequest)
        .filter(
            FriendRequest.id == request_id,
            FriendRequest.to_user_id == user.id,
            FriendRequest.status == "pending",
        )
        .first()
    )
    if not req:
        db.close()
        return RedirectResponse(url="/social/", status_code=status.HTTP_303_SEE_OTHER)

    req.status = "accepted"
    if not are_friends(db, req.from_user_id, req.to_user_id):
        db.add(Friendship(user_id=req.from_user_id, friend_id=req.to_user_id, created_at=utc_now().isoformat()))
    if not are_friends(db, req.to_user_id, req.from_user_id):
        db.add(Friendship(user_id=req.to_user_id, friend_id=req.from_user_id, created_at=utc_now().isoformat()))
    db.commit()
    db.close()
    return RedirectResponse(url="/social/", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/social/chat/{friend_id}/send/", name="social_chat_send")
def social_chat_send(
    request: Request,
    friend_id: int,
    text_message: str = Form(""),
    file_id: str = Form(""),
):
    db = SessionLocal()
    user = get_current_user(request, db)
    if not user:
        db.close()
        return RedirectResponse(url="/accounts/login/", status_code=status.HTTP_303_SEE_OTHER)
    if friend_id != user.id and not are_friends(db, user.id, friend_id):
        db.close()
        return RedirectResponse(url="/social/", status_code=status.HTTP_303_SEE_OTHER)

    text_clean = text_message.strip()
    selected_file_id = int(file_id) if file_id.strip().isdigit() else None
    if not text_clean and not selected_file_id:
        db.close()
        return RedirectResponse(
            url=f"/social/?chat={friend_id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    if selected_file_id:
        own = (
            db.query(CloudFile)
            .filter(CloudFile.id == selected_file_id, CloudFile.owner_user_id == user.id)
            .first()
        )
        if not own:
            db.close()
            return RedirectResponse(
                url=f"/social/?chat={friend_id}",
                status_code=status.HTTP_303_SEE_OTHER,
            )

    db.add(
        Message(
            sender_user_id=user.id,
            receiver_user_id=friend_id,
            text=text_clean,
            file_id=selected_file_id,
            created_at=utc_now().isoformat(),
        )
    )
    db.commit()
    db.close()
    return RedirectResponse(
        url=f"/social/?chat={friend_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
