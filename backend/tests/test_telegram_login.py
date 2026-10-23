import httpx
from aiogram.types import User as TgUser
from sqlalchemy import select, update

from ayda.bot import texts
from ayda.bot.handlers import LOGIN_CALLBACK, confirm_login, login_reply
from ayda.core.db import Database
from ayda.modules.auth.models import TelegramLoginRequest, User
from tests.conftest import FakeMailer
from tests.contract import assert_matches
from tests.helpers import make_init_data, sign_in
from tests.test_email_auth import allow_resend, email_session, last_code

TG = TgUser(id=777, is_bot=False, first_name="Петя", username="petya")


async def start(client: httpx.AsyncClient, headers: dict[str, str] | None = None) -> dict[str, str]:
    r = await client.post("/auth/telegram/login-requests", headers=headers or {})
    assert r.status_code == 201, r.text
    assert_matches(r, "createTelegramLoginRequest")
    return r.json()


def code_of(request: dict[str, str]) -> str:
    prefix = "https://t.me/ayda_quest_bot?startapp=login_"
    assert request["bot_url"].startswith(prefix)
    return request["bot_url"].removeprefix(prefix)


async def confirm(database: Database, request: dict[str, str], user: TgUser = TG) -> str:
    text, markup = await login_reply(database, code_of(request))
    assert text == texts.LOGIN_CONFIRM and markup is not None
    data = markup.inline_keyboard[0][0].callback_data
    assert data == f"{LOGIN_CALLBACK}{request['id']}"
    return await confirm_login(database, data or "", user)


async def exchange(
    client: httpx.AsyncClient, request: dict[str, str], secret: str | None = None
) -> httpx.Response:
    return await client.post(
        f"/auth/telegram/login-requests/{request['id']}/exchange",
        json={"poll_secret": secret or request["poll_secret"]},
    )


async def test_sign_in_through_the_bot(client: httpx.AsyncClient, database: Database) -> None:
    request = await start(client)

    pending = await exchange(client, request)
    assert pending.status_code == 202

    assert await confirm(database, request) == texts.LOGIN_DONE
    # Pressing the button again changes nothing.
    assert (
        await confirm_login(database, f"{LOGIN_CALLBACK}{request['id']}", TG) == texts.LOGIN_EXPIRED
    )

    wrong = await exchange(client, request, secret="not-the-secret")
    assert wrong.status_code == 401
    assert_matches(wrong, "exchangeTelegramLoginRequest")

    ok = await exchange(client, request)
    assert ok.status_code == 200
    assert_matches(ok, "exchangeTelegramLoginRequest")
    body = ok.json()
    assert body["user"]["first_name"] == "Петя"
    assert body["refresh_token"]

    assert (await exchange(client, request)).status_code == 401  # works once


async def test_bot_sign_in_finds_the_mini_app_account(
    client: httpx.AsyncClient, database: Database
) -> None:
    mini_app = await sign_in(client, telegram_id=777, name="Петя")
    request = await start(client)
    await confirm(database, request)
    ok = await exchange(client, request)
    assert ok.json()["user"]["id"] == mini_app.user_id


async def test_expired_link_is_refused_in_the_bot(
    client: httpx.AsyncClient, database: Database
) -> None:
    request = await start(client)
    async with database.sessionmaker() as s:
        await s.execute(
            update(TelegramLoginRequest).values(expires_at=TelegramLoginRequest.created_at)
        )
        await s.commit()
    text, markup = await login_reply(database, code_of(request))
    assert text == texts.LOGIN_EXPIRED and markup is None
    assert (await exchange(client, request)).status_code == 401
    assert (await login_reply(database, "unknown-code"))[0] == texts.LOGIN_EXPIRED


async def test_email_user_links_telegram_and_unlinks_email(
    client: httpx.AsyncClient, database: Database, mailer: FakeMailer
) -> None:
    session = await email_session(client, mailer)
    h = {"Authorization": f"Bearer {session['access_token']}"}

    request = await start(client, h)
    await confirm(database, request)
    linked = await exchange(client, request)
    assert linked.status_code == 200
    assert linked.json()["user"]["id"] == session["user"]["id"]  # pyright: ignore[reportIndexIssue]
    assert linked.json()["user"]["first_name"] == "Петя"  # an empty name is filled from Telegram

    listed = await client.get("/me/identities", headers=h)
    assert listed.status_code == 200
    assert_matches(listed, "listMyIdentities")
    items = listed.json()["items"]
    assert [(i["provider"], i["label"]) for i in items] == [
        ("email", "sasha@example.ru"),
        ("telegram", "Telegram"),
    ]

    # The Mini App now opens the same account.
    assert (await sign_in(client, telegram_id=777, name="Петя")).user_id == session["user"]["id"]  # pyright: ignore[reportIndexIssue]

    gone = await client.delete(f"/me/identities/{items[0]['id']}", headers=h)
    assert gone.status_code == 204
    assert_matches(gone, "unlinkMyIdentity")
    last = await client.delete(f"/me/identities/{items[1]['id']}", headers=h)
    assert last.status_code == 409
    assert_matches(last, "unlinkMyIdentity")
    missing = await client.delete(f"/me/identities/{items[0]['id']}", headers=h)
    assert missing.status_code == 404


async def test_telegram_of_another_account_is_not_linked(
    client: httpx.AsyncClient, database: Database, mailer: FakeMailer
) -> None:
    await sign_in(client, telegram_id=777)
    session = await email_session(client, mailer)
    h = {"Authorization": f"Bearer {session['access_token']}"}
    request = await start(client, h)
    await confirm(database, request)
    taken = await exchange(client, request)
    assert taken.status_code == 409
    assert_matches(taken, "exchangeTelegramLoginRequest")
    async with database.sessionmaker() as s:
        user = await s.scalar(select(User).where(User.telegram_id.is_(None)))
    assert user is not None


async def test_telegram_user_links_an_email(
    client: httpx.AsyncClient, database: Database, mailer: FakeMailer
) -> None:
    me = await sign_in(client, telegram_id=900)
    await client.post("/auth/email/start", json={"email": "p@example.ru"})
    wrong_code = "999999" if last_code(mailer) != "999999" else "111111"
    wrong = await client.post(
        "/me/identities/email",
        json={"email": "p@example.ru", "code": wrong_code},
        headers=me.headers,
    )
    assert wrong.status_code == 401
    assert_matches(wrong, "linkMyEmail")
    ok = await client.post(
        "/me/identities/email",
        json={"email": "p@example.ru", "code": last_code(mailer)},
        headers=me.headers,
    )
    assert ok.status_code == 201
    assert_matches(ok, "linkMyEmail")
    assert ok.json()["label"] == "p@example.ru"

    # Signing in by that email now opens the Telegram account.
    await allow_resend(database)
    by_email = await email_session(client, mailer, "p@example.ru")
    assert by_email["user"]["id"] == me.user_id  # pyright: ignore[reportIndexIssue]


async def test_email_of_another_account_is_not_linked(
    client: httpx.AsyncClient, database: Database, mailer: FakeMailer
) -> None:
    await email_session(client, mailer, "taken@example.ru")
    me = await sign_in(client, telegram_id=901)
    await allow_resend(database)
    await client.post("/auth/email/start", json={"email": "taken@example.ru"})
    taken = await client.post(
        "/me/identities/email",
        json={"email": "taken@example.ru", "code": last_code(mailer)},
        headers=me.headers,
    )
    assert taken.status_code == 409
    assert_matches(taken, "linkMyEmail")


async def approve(client: httpx.AsyncClient, code: str, init_data: str) -> httpx.Response:
    return await client.post(
        "/auth/telegram/login-requests/approve", json={"init_data": init_data, "code": code}
    )


async def test_sign_in_confirmed_in_the_mini_app(client: httpx.AsyncClient) -> None:
    request = await start(client)
    code = code_of(request)

    ok = await approve(client, code, make_init_data(777, "Петя", start_param=f"login_{code}"))
    assert ok.status_code == 204, ok.text
    # The same link cannot confirm twice.
    again = await approve(client, code, make_init_data(888, "Вася"))
    assert again.status_code == 404
    assert_matches(again, "approveTelegramLoginRequest")

    session = await exchange(client, request)
    assert session.status_code == 200, session.text
    assert session.json()["user"]["first_name"] == "Петя"


async def test_mini_app_confirmation_needs_valid_init_data(client: httpx.AsyncClient) -> None:
    request = await start(client)
    code = code_of(request)

    forged = await approve(client, code, make_init_data(777, bot_token="1:OTHER"))
    assert forged.status_code == 401
    unknown = await approve(client, "unknown-code", make_init_data(777))
    assert unknown.status_code == 404
    assert (await exchange(client, request)).status_code == 202
