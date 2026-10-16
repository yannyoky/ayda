import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Path, Response

from ayda.api.deps import AppSettings, CurrentUser, DbSession
from ayda.api.schemas import Friend, Invite, Items
from ayda.core.problems import Problem
from ayda.modules import auth, social

router = APIRouter(tags=["social"])

INVITE_PROBLEMS = {
    "invite-not-found": (404, "Приглашение не найдено"),
    "own-invite": (409, "Это твоё собственное приглашение"),
    "invite-expired": (410, "Срок приглашения истёк"),
}


def friend_schema(user: auth.User, since: datetime) -> Friend:
    return Friend(id=user.id, first_name=user.first_name, avatar_url=user.avatar_url, since=since)


@router.post("/invites", operation_id="createInvite", status_code=201)
async def create_invite(user: CurrentUser, session: DbSession, settings: AppSettings) -> Invite:
    try:
        invite = await social.create_invite(session, user.id, datetime.now(UTC))
    except social.InviteLimitError:
        raise Problem(429, "too-many-invites", detail="Слишком много приглашений") from None
    await session.commit()
    return Invite(
        code=invite.code,
        url=f"https://t.me/{settings.telegram_bot_username}?startapp={invite.code}",
        expires_at=invite.expires_at,
    )


@router.post("/invites/{code}/accept", operation_id="acceptInvite")
async def accept_invite(
    code: Annotated[str, Path(min_length=10, max_length=64)],
    user: CurrentUser,
    session: DbSession,
) -> Friend:
    try:
        inviter_id, since = await social.accept_invite(session, code, user.id, datetime.now(UTC))
    except social.InviteError as exc:
        status, detail = INVITE_PROBLEMS[exc.code]
        raise Problem(status, exc.code, detail=detail) from None
    inviter = await auth.get_user(session, inviter_id)
    if inviter is None or inviter.deletion_requested_at is not None:
        await session.rollback()
        raise Problem(404, "invite-not-found", detail=INVITE_PROBLEMS["invite-not-found"][1])
    await session.commit()
    return friend_schema(inviter, since)


@router.get("/friends", operation_id="listFriends")
async def list_friends(user: CurrentUser, session: DbSession) -> Items[Friend]:
    since = await social.friends(session, user.id)
    users = await auth.get_users(session, list(since))
    items = [
        friend_schema(u, since[u.id]) for u in users.values() if u.deletion_requested_at is None
    ]
    items.sort(key=lambda f: (f.first_name.lower(), str(f.id)))
    return Items(items=items)


@router.delete("/friends/{user_id}", operation_id="removeFriend", status_code=204)
async def remove_friend(user_id: uuid.UUID, user: CurrentUser, session: DbSession) -> Response:
    if not await social.remove_friend(session, user.id, user_id):
        raise Problem(404, "not-friends", detail="Вы не друзья")
    await session.commit()
    return Response(status_code=204)
