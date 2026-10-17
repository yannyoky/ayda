import re
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select, update

from ayda.core.db import Database
from ayda.modules.analytics.models import Event
from ayda.modules.auth.models import EmailCode, EmailSend, UserIdentity
from tests.conftest import FakeMailer
from tests.contract import assert_matches
from tests.helpers import sign_in

EMAIL = "Sasha@Example.ru"
KALININGRAD = 435


def last_code(mailer: FakeMailer) -> str:
    match = re.search(r"\b(\d{6})\b", mailer.sent[-1][2])
    assert match
    return match.group(1)


async def allow_resend(database: Database) -> None:
    """Move earlier sends past the one-minute resend limit."""
    async with database.sessionmaker() as s:
        await s.execute(update(EmailSend).values(sent_at=datetime.now(UTC) - timedelta(minutes=2)))
        await s.commit()


async def email_session(
    client: httpx.AsyncClient, mailer: FakeMailer, email: str = EMAIL
) -> dict[str, object]:
    start = await client.post("/auth/email/start", json={"email": email})
    assert start.status_code == 202, start.text
    verify = await client.post(
        "/auth/email/verify", json={"email": email, "code": last_code(mailer)}
    )
    assert verify.status_code == 200, verify.text
    return verify.json()


async def test_email_sign_in_creates_user_once(
    client: httpx.AsyncClient, mailer: FakeMailer, database: Database
) -> None:
    start = await client.post("/auth/email/start", json={"email": EMAIL})
    assert start.status_code == 202
    assert_matches(start, "startEmailSignIn")
    to, subject, _ = mailer.sent[-1]
    assert to == "sasha@example.ru"
    assert "Ayda" in subject

    verify = await client.post(
        "/auth/email/verify", json={"email": " sasha@example.RU ", "code": last_code(mailer)}
    )
    assert verify.status_code == 200
    assert_matches(verify, "verifyEmailSignIn")
    body = verify.json()
    assert body["user"]["first_name"] == ""
    assert body["refresh_token"]
    assert body["refresh_expires_at"]
    me = await client.get("/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200

    await allow_resend(database)
    again = await email_session(client, mailer)
    assert again["user"] == body["user"]  # pyright: ignore[reportUnknownMemberType]

    async with database.sessionmaker() as s:
        rows = (await s.scalars(select(UserIdentity))).all()
        events = (await s.scalars(select(Event).order_by(Event.id))).all()
    assert [(r.provider, r.subject) for r in rows] == [("email", "sasha@example.ru")]
    assert [(e.type, e.payload) for e in events] == [
        ("signed_in", {"provider": "email", "new": True}),
        ("signed_in", {"provider": "email", "new": False}),
    ]


async def test_code_works_once(client: httpx.AsyncClient, mailer: FakeMailer) -> None:
    await client.post("/auth/email/start", json={"email": EMAIL})
    code = last_code(mailer)
    ok = await client.post("/auth/email/verify", json={"email": EMAIL, "code": code})
    assert ok.status_code == 200
    reused = await client.post("/auth/email/verify", json={"email": EMAIL, "code": code})
    assert reused.status_code == 401
    assert_matches(reused, "verifyEmailSignIn")


async def test_five_wrong_attempts_burn_the_code(
    client: httpx.AsyncClient, mailer: FakeMailer, database: Database
) -> None:
    await client.post("/auth/email/start", json={"email": EMAIL})
    code = last_code(mailer)
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        r = await client.post("/auth/email/verify", json={"email": EMAIL, "code": wrong})
        assert r.status_code == 401
    right = await client.post("/auth/email/verify", json={"email": EMAIL, "code": code})
    assert right.status_code == 401


async def test_expired_code_is_rejected(
    client: httpx.AsyncClient, mailer: FakeMailer, database: Database
) -> None:
    await client.post("/auth/email/start", json={"email": EMAIL})
    async with database.sessionmaker() as s:
        await s.execute(update(EmailCode).values(expires_at=datetime.now(UTC)))
        await s.commit()
    r = await client.post("/auth/email/verify", json={"email": EMAIL, "code": last_code(mailer)})
    assert r.status_code == 401


async def test_codes_are_rate_limited(
    client: httpx.AsyncClient, mailer: FakeMailer, database: Database
) -> None:
    assert (await client.post("/auth/email/start", json={"email": EMAIL})).status_code == 202
    soon = await client.post("/auth/email/start", json={"email": EMAIL})
    assert soon.status_code == 429
    assert_matches(soon, "startEmailSignIn")
    for _ in range(4):
        await allow_resend(database)
        assert (await client.post("/auth/email/start", json={"email": EMAIL})).status_code == 202
    await allow_resend(database)
    assert (await client.post("/auth/email/start", json={"email": EMAIL})).status_code == 429
    assert len(mailer.sent) == 5


async def test_invalid_email_and_disabled_mail(client: httpx.AsyncClient) -> None:
    bad = await client.post("/auth/email/start", json={"email": "not-an-email"})
    assert bad.status_code == 422
    assert_matches(bad, "startEmailSignIn")
    off = await client.post("/auth/email/start", json={"email": EMAIL})
    assert off.status_code == 503
    assert_matches(off, "startEmailSignIn")


async def test_failed_send_does_not_count(client: httpx.AsyncClient, mailer: FakeMailer) -> None:
    mailer.fail = True
    failed = await client.post("/auth/email/start", json={"email": EMAIL})
    assert failed.status_code == 503
    mailer.fail = False
    assert (await client.post("/auth/email/start", json={"email": EMAIL})).status_code == 202


async def test_refresh_rotates_and_reuse_revokes_the_family(
    client: httpx.AsyncClient, mailer: FakeMailer
) -> None:
    first = await email_session(client, mailer)
    old = first["refresh_token"]

    rotated = await client.post("/auth/refresh", json={"refresh_token": old})
    assert rotated.status_code == 200
    assert_matches(rotated, "refreshSession")
    new = rotated.json()["refresh_token"]
    assert new != old

    reused = await client.post("/auth/refresh", json={"refresh_token": old})
    assert reused.status_code == 401
    assert_matches(reused, "refreshSession")
    # The thief's reuse also signs out whoever holds the newer token.
    assert (await client.post("/auth/refresh", json={"refresh_token": new})).status_code == 401


async def test_logout_revokes_refresh_token(client: httpx.AsyncClient, mailer: FakeMailer) -> None:
    token = (await email_session(client, mailer))["refresh_token"]
    out = await client.post("/auth/logout", json={"refresh_token": token})
    assert out.status_code == 204
    assert_matches(out, "signOut")
    assert (await client.post("/auth/logout", json={"refresh_token": "unknown"})).status_code == 204
    assert (await client.post("/auth/refresh", json={"refresh_token": token})).status_code == 401


async def test_account_deletion_ends_native_sessions(
    client: httpx.AsyncClient, mailer: FakeMailer
) -> None:
    session = await email_session(client, mailer)
    headers = {"Authorization": f"Bearer {session['access_token']}"}
    assert (await client.delete("/me", headers=headers)).status_code == 202
    r = await client.post("/auth/refresh", json={"refresh_token": session["refresh_token"]})
    assert r.status_code == 401


async def test_email_user_sets_a_name_before_finishing_onboarding(
    client: httpx.AsyncClient, mailer: FakeMailer
) -> None:
    session = await email_session(client, mailer)
    h = {"Authorization": f"Bearer {session['access_token']}"}
    await client.post("/me/consents", json={"version": "2026-10-16"}, headers=h)
    await client.patch("/me/profile", json={"city_id": KALININGRAD}, headers=h)

    no_name = await client.post("/me/onboarding/complete", headers=h)
    assert no_name.status_code == 409
    assert no_name.json()["type"].endswith("name-required")

    blank = await client.patch("/me/profile", json={"first_name": "   "}, headers=h)
    assert blank.status_code == 422
    named = await client.patch("/me/profile", json={"first_name": "  Саша "}, headers=h)
    assert named.status_code == 200
    assert_matches(named, "updateProfile")
    assert named.json()["first_name"] == "Саша"
    done = await client.post("/me/onboarding/complete", headers=h)
    assert done.status_code == 200


async def test_telegram_sign_in_records_an_identity(
    client: httpx.AsyncClient, database: Database
) -> None:
    await sign_in(client, telegram_id=555)
    await sign_in(client, telegram_id=555)
    async with database.sessionmaker() as s:
        rows = (await s.scalars(select(UserIdentity))).all()
    assert [(r.provider, r.subject) for r in rows] == [("telegram", "555")]
