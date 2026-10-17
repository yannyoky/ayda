import uuid

from fastapi import APIRouter, Response

from ayda.api.deps import AppSettings, CurrentUser, DbSession
from ayda.api.schemas import EmailVerify, Items, SignInIdentity
from ayda.core.problems import Problem
from ayda.modules import auth

router = APIRouter(tags=["profile"])


def _schema(identity: auth.UserIdentity) -> SignInIdentity:
    email = identity.provider == "email"
    return SignInIdentity(
        id=identity.id,
        provider="email" if email else "telegram",
        label=identity.subject if email else "Telegram",
        created_at=identity.created_at,
    )


@router.get("/me/identities", operation_id="listMyIdentities")
async def list_my_identities(user: CurrentUser, session: DbSession) -> Items[SignInIdentity]:
    return Items(items=[_schema(i) for i in await auth.list_identities(session, user.id)])


@router.post("/me/identities/email", operation_id="linkMyEmail", status_code=201)
async def link_my_email(
    body: EmailVerify, user: CurrentUser, session: DbSession, settings: AppSettings
) -> SignInIdentity:
    try:
        email = auth.normalize_email(body.email)
    except auth.EmailError:
        raise Problem(422, "invalid-email", detail="Проверьте адрес почты") from None
    try:
        await auth.check_code(session, email, body.code, settings.token_secret)
    except auth.EmailError:
        await session.commit()  # keep the wrong-attempt count
        raise Problem(401, "invalid-code", detail="Неверный или устаревший код") from None
    try:
        identity = await auth.link_email(session, user, email)
    except auth.IdentityError:
        await session.rollback()
        raise Problem(
            409, "identity-taken", detail="Эта почта уже привязана к другому аккаунту"
        ) from None
    await session.commit()
    return _schema(identity)


@router.delete("/me/identities/{identity_id}", operation_id="unlinkMyIdentity", status_code=204)
async def unlink_my_identity(
    identity_id: uuid.UUID, user: CurrentUser, session: DbSession
) -> Response:
    try:
        await auth.unlink_identity(session, user, identity_id)
    except auth.IdentityError as exc:
        if exc.code == "not-found":
            raise Problem(404, "not-found", detail="Способ входа не найден") from None
        raise Problem(
            409, "last-identity", detail="Нельзя отвязать последний способ входа"
        ) from None
    await session.commit()
    return Response(status_code=204)
