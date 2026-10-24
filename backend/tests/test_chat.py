import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from fastapi import FastAPI
from sqlalchemy import select, update

from ayda.app import chat as chat_app
from ayda.app import notifications
from ayda.core.config import Settings
from ayda.core.db import Database
from ayda.core.jobs import Job
from ayda.core.realtime import Realtime
from ayda.modules import auth, chat
from ayda.worker import build_worker
from tests.conftest import FakeRealtime
from tests.contract import assert_matches
from tests.helpers import SignedIn, sign_in
from tests.test_bot import FakeSender
from tests.test_feed import befriend


async def open_dm(client: httpx.AsyncClient, a: SignedIn, b: SignedIn) -> dict[str, Any]:
    response = await client.post(
        "/conversations/direct", json={"user_id": b.user_id}, headers=a.headers
    )
    assert response.status_code == 200, response.text
    assert_matches(response, "openDirectConversation")
    return response.json()


async def send(
    client: httpx.AsyncClient, user: SignedIn, conversation_id: str, text: str
) -> httpx.Response:
    return await client.post(
        f"/conversations/{conversation_id}/messages",
        json={"text": text, "client_id": str(uuid.uuid4())},
        headers=user.headers,
    )


async def pair(client: httpx.AsyncClient) -> tuple[SignedIn, SignedIn]:
    alice = await sign_in(client, 1001, "Алиса")
    bob = await sign_in(client, 2002, "Боря")
    await befriend(client, alice, bob)
    return alice, bob


async def test_friends_chat_with_history_and_unread_counts(
    client: httpx.AsyncClient, realtime: FakeRealtime
) -> None:
    alice, bob = await pair(client)
    conversation = await open_dm(client, alice, bob)
    assert conversation["title"] == "Боря" and conversation["can_send"] is True
    assert conversation["last_message"] is None and conversation["unread_count"] == 0
    assert (await open_dm(client, bob, alice))["id"] == conversation["id"]  # one chat per pair

    sent = await send(client, alice, conversation["id"], "  привет  ")
    assert sent.status_code == 201
    assert_matches(sent, "sendMessage")
    message = sent.json()
    assert message["text"] == "привет" and message["author"]["first_name"] == "Алиса"
    await send(client, alice, conversation["id"], "как дела?")

    # Delivered over realtime to both members (the author's other devices too).
    created = [e for _, e in realtime.sent if e["type"] == "message.created"]
    assert [e["message"]["text"] for e in created] == ["привет", "как дела?"]
    assert realtime.sent[0][0] == {alice.user_id, bob.user_id}

    listed = await client.get("/conversations", headers=bob.headers)
    assert_matches(listed, "listConversations")
    [item] = listed.json()["items"]
    assert item["title"] == "Алиса" and item["unread_count"] == 2
    assert item["last_message"]["text"] == "как дела?"
    mine = (await client.get("/conversations", headers=alice.headers)).json()["items"][0]
    assert mine["unread_count"] == 0

    page = await client.get(
        f"/conversations/{conversation['id']}/messages?limit=1", headers=bob.headers
    )
    assert_matches(page, "listMessages")
    assert [m["text"] for m in page.json()["items"]] == ["как дела?"]
    older = await client.get(
        f"/conversations/{conversation['id']}/messages",
        params={"cursor": page.json()["next_cursor"]},
        headers=bob.headers,
    )
    assert [m["text"] for m in older.json()["items"]] == ["привет"]
    assert older.json()["next_cursor"] is None

    read = await client.post(
        f"/conversations/{conversation['id']}/read",
        json={"last_read_message_id": message["id"]},
        headers=bob.headers,
    )
    assert read.status_code == 204
    assert_matches(read, "markConversationRead")
    got = await client.get(f"/conversations/{conversation['id']}", headers=bob.headers)
    assert_matches(got, "getConversation")
    assert got.json()["unread_count"] == 1
    assert realtime.sent[-1][1] == {
        "type": "conversation.read",
        "conversation_id": conversation["id"],
        "user_id": bob.user_id,
        "last_read_message_id": message["id"],
    }
    # The mark never moves back.
    await client.post(
        f"/conversations/{conversation['id']}/read",
        json={"last_read_message_id": 0},
        headers=bob.headers,
    )
    got = await client.get(f"/conversations/{conversation['id']}", headers=bob.headers)
    assert got.json()["last_read_message_id"] == message["id"]


async def test_retry_with_the_same_client_id_is_saved_once(
    client: httpx.AsyncClient, realtime: FakeRealtime
) -> None:
    alice, bob = await pair(client)
    conversation = await open_dm(client, alice, bob)
    body = {"text": "один раз", "client_id": str(uuid.uuid4())}
    url = f"/conversations/{conversation['id']}/messages"

    first = await client.post(url, json=body, headers=alice.headers)
    second = await client.post(url, json=body, headers=alice.headers)

    assert first.status_code == 201 and second.status_code == 200
    assert_matches(second, "sendMessage")
    assert first.json()["id"] == second.json()["id"]
    assert len(realtime.sent) == 1
    items = (await client.get(url, headers=bob.headers)).json()["items"]
    assert len(items) == 1


async def test_only_friends_and_members(client: httpx.AsyncClient, realtime: FakeRealtime) -> None:
    alice, bob = await pair(client)
    eve = await sign_in(client, 3003, "Ева")
    conversation = await open_dm(client, alice, bob)

    stranger = await client.post(
        "/conversations/direct", json={"user_id": eve.user_id}, headers=alice.headers
    )
    assert stranger.status_code == 403
    assert_matches(stranger, "openDirectConversation")
    for response in (
        await client.get(f"/conversations/{conversation['id']}", headers=eve.headers),
        await client.get(f"/conversations/{conversation['id']}/messages", headers=eve.headers),
        await send(client, eve, conversation["id"], "я тут"),
    ):
        assert response.status_code == 404
    assert (await client.get("/conversations", headers=eve.headers)).json()["items"] == []


async def test_removing_a_friend_closes_the_chat(
    client: httpx.AsyncClient, realtime: FakeRealtime
) -> None:
    alice, bob = await pair(client)
    conversation = await open_dm(client, alice, bob)
    await send(client, alice, conversation["id"], "до связи")

    assert (
        await client.delete(f"/friends/{bob.user_id}", headers=alice.headers)
    ).status_code == 204
    closed = await send(client, bob, conversation["id"], "эй")
    assert closed.status_code == 403
    assert_matches(closed, "sendMessage")
    assert closed.json()["type"].endswith("/chat-closed")
    view = (await client.get(f"/conversations/{conversation['id']}", headers=bob.headers)).json()
    assert view["can_send"] is False
    # History stays readable.
    history = await client.get(f"/conversations/{conversation['id']}/messages", headers=bob.headers)
    assert [m["text"] for m in history.json()["items"]] == ["до связи"]
    # Nothing more is published to the former friend.
    assert all(e["type"] != "message.created" or "эй" not in str(e) for _, e in realtime.sent)


async def test_delete_own_message(client: httpx.AsyncClient, realtime: FakeRealtime) -> None:
    alice, bob = await pair(client)
    conversation = await open_dm(client, alice, bob)
    message = (await send(client, alice, conversation["id"], "упс")).json()
    url = f"/conversations/{conversation['id']}/messages/{message['id']}"

    foreign = await client.delete(url, headers=bob.headers)
    assert foreign.status_code == 403
    assert_matches(foreign, "deleteMessage")
    deleted = await client.delete(url, headers=alice.headers)
    assert deleted.status_code == 204
    assert_matches(deleted, "deleteMessage")
    assert (await client.delete(url, headers=alice.headers)).status_code == 404

    assert realtime.sent[-1][1] == {
        "type": "message.deleted",
        "conversation_id": conversation["id"],
        "message_id": message["id"],
    }
    listed = (await client.get("/conversations", headers=bob.headers)).json()["items"][0]
    assert listed["last_message"] is None and listed["unread_count"] == 0
    history = await client.get(f"/conversations/{conversation['id']}/messages", headers=bob.headers)
    assert history.json()["items"] == []


async def test_rate_limit_and_validation(
    client: httpx.AsyncClient, realtime: FakeRealtime, database: Database
) -> None:
    alice, bob = await pair(client)
    conversation = await open_dm(client, alice, bob)
    empty = await send(client, alice, conversation["id"], "   ")
    too_long = await send(client, alice, conversation["id"], "я" * 2001)
    bad_cursor = await client.get(
        f"/conversations/{conversation['id']}/messages?cursor=@@", headers=alice.headers
    )
    assert empty.status_code == too_long.status_code == bad_cursor.status_code == 422

    for _ in range(chat.MAX_MESSAGES_PER_MINUTE):
        assert (await send(client, alice, conversation["id"], "спам")).status_code == 201
    limited = await send(client, alice, conversation["id"], "ещё")
    assert limited.status_code == 429
    assert_matches(limited, "sendMessage")


async def test_bot_notice_has_no_text_and_skips_read_chats(
    client: httpx.AsyncClient, realtime: FakeRealtime, database: Database, settings: Settings
) -> None:
    alice, bob = await pair(client)
    conversation = await open_dm(client, alice, bob)
    await send(client, alice, conversation["id"], "секретный текст")
    await send(client, alice, conversation["id"], "и ещё")

    async with database.sessionmaker() as session:
        notices = list(await session.scalars(select(Job).where(Job.kind == "notify.send")))
        # One notice per chat and 10 minutes, a minute after the message.
        assert [j.payload["user_id"] for j in notices] == [bob.user_id]
        assert notices[0].run_at > datetime.now(UTC) + timedelta(seconds=30)
        assert "секрет" not in str(notices[0].payload)
        await session.execute(update(Job).values(run_at=datetime.now(UTC)))
        await session.commit()

    sender = FakeSender()
    worker = build_worker(settings, database, sender=sender)
    await worker.run_one()
    # Bob reached the bot? Users signed in via the Mini App are reachable by default.
    [(_, notice)] = sender.sent
    assert notice.text == "Тебе пишет Алиса 💬"
    assert notice.button is not None
    assert notice.button.url.endswith(f"startapp=c{uuid.UUID(conversation['id']).hex}")

    # Read in the app before the notice is due: nothing is sent.
    chat_app.register(settings)
    render = notifications.RENDERERS[chat_app.NOTIFY_KIND]
    last = (await send(client, alice, conversation["id"], "третье")).json()
    await client.post(
        f"/conversations/{conversation['id']}/read",
        json={"last_read_message_id": last["id"]},
        headers=bob.headers,
    )
    async with database.sessionmaker() as session:
        me = await auth.get_user(session, uuid.UUID(bob.user_id))
        assert me is not None
        params = {"conversation_id": conversation["id"], "message_id": last["id"]}
        assert await render(session, me, params) is None


async def test_failed_publish_does_not_lose_the_message(
    app: FastAPI, client: httpx.AsyncClient, database: Database, settings: Settings
) -> None:
    from pydantic import SecretStr

    app.state.realtime = Realtime(
        settings.model_copy(
            update={
                "centrifugo_api_url": "http://127.0.0.1:9/api",
                "centrifugo_api_key": SecretStr("x"),
            }
        )
    )
    alice, bob = await pair(client)
    conversation = await open_dm(client, alice, bob)
    sent = await send(client, alice, conversation["id"], "дойду позже")
    assert sent.status_code == 201
    async with database.sessionmaker() as session:
        retry = await session.scalar(select(Job).where(Job.kind == "realtime.publish"))
    assert retry is not None
    assert retry.payload == {
        "kind": chat_app.MESSAGE_CREATED,
        "params": {"message_id": sent.json()["id"]},
    }
    await app.state.realtime.aclose()


async def test_a_chat_deleted_for_me_comes_back_with_only_new_messages(
    client: httpx.AsyncClient, realtime: FakeRealtime
) -> None:
    alice, bob = await pair(client)
    conversation = await open_dm(client, alice, bob)
    await send(client, bob, conversation["id"], "старое")

    hidden = await client.delete(f"/conversations/{conversation['id']}", headers=alice.headers)
    assert hidden.status_code == 204
    assert_matches(hidden, "hideConversation")
    assert (await client.get("/conversations", headers=alice.headers)).json()["items"] == []
    [kept] = (await client.get("/conversations", headers=bob.headers)).json()["items"]
    assert kept["last_message"]["text"] == "старое" and kept["deletes_at"] is None

    await send(client, bob, conversation["id"], "новое")
    [back] = (await client.get("/conversations", headers=alice.headers)).json()["items"]
    assert back["unread_count"] == 1
    page = await client.get(f"/conversations/{conversation['id']}/messages", headers=alice.headers)
    assert [m["text"] for m in page.json()["items"]] == ["новое"]
    bob_page = await client.get(
        f"/conversations/{conversation['id']}/messages", headers=bob.headers
    )
    assert [m["text"] for m in bob_page.json()["items"]] == ["новое", "старое"]

    stranger = await sign_in(client, 3003, "Ева")
    missing = await client.delete(f"/conversations/{conversation['id']}", headers=stranger.headers)
    assert missing.status_code == 404
