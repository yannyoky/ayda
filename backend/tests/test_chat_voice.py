import json
import subprocess
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select

from ayda.core.config import Settings
from ayda.core.db import Database
from ayda.core.jobs import Job
from ayda.core.storage import Storage
from ayda.main import create_app
from ayda.modules import chat
from ayda.worker import build_worker
from tests.conftest import FakeRealtime
from tests.contract import assert_matches
from tests.helpers import SignedIn
from tests.test_chat import open_dm, pair, send


@pytest.fixture
async def voice_app(
    s3_settings: Settings,
) -> AsyncIterator[tuple[httpx.AsyncClient, FakeRealtime]]:
    app: FastAPI = create_app(s3_settings)
    fake = FakeRealtime(s3_settings)
    app.state.realtime = fake
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
        yield c, fake
    await app.state.db.dispose()


def recording(folder: Path, seconds: int = 2) -> bytes:
    """An Opus recording in WebM, as Chrome's MediaRecorder makes, with a metadata tag."""
    path = folder / "rec.webm"
    tone = f"sine=frequency=440:duration={seconds}"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", tone,
         "-ac", "2", "-c:a", "libopus", "-metadata", "title=Kitchen at home", str(path)],
        check=True,
    )  # fmt: skip
    return path.read_bytes()


def probe(path: Path) -> dict[str, Any]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        check=True, capture_output=True,
    ).stdout  # fmt: skip
    return json.loads(out)


async def upload(
    client: httpx.AsyncClient, user: SignedIn, conversation_id: str, data: bytes
) -> str:
    response = await client.post(
        f"/conversations/{conversation_id}/uploads",
        json={"kind": "voice", "content_type": "audio/webm", "size_bytes": len(data)},
        headers=user.headers,
    )
    assert response.status_code == 201, response.text
    assert_matches(response, "createChatUpload")
    slot = response.json()
    async with httpx.AsyncClient(trust_env=False) as s3:
        put = await s3.put(slot["upload_url"], content=data, headers=slot["headers"])
    assert put.status_code == 200, put.text
    return slot["media_id"]


async def send_voice(
    client: httpx.AsyncClient, user: SignedIn, conversation_id: str, attachment_id: str
) -> httpx.Response:
    return await client.post(
        f"/conversations/{conversation_id}/messages",
        json={"client_id": str(uuid.uuid4()), "attachment_id": attachment_id},
        headers=user.headers,
    )


async def run_jobs(s3_settings: Settings, database: Database, fake: FakeRealtime) -> None:
    worker = build_worker(s3_settings, database, Storage(s3_settings), realtime_client=fake)
    while await worker.run_one():
        pass


async def test_a_voice_message_is_re_encoded_before_anyone_plays_it(
    voice_app: tuple[httpx.AsyncClient, FakeRealtime],
    s3_settings: Settings,
    database: Database,
    tmp_path: Path,
) -> None:
    client, fake = voice_app
    alice, bob = await pair(client)
    conversation = (await open_dm(client, alice, bob))["id"]
    attachment_id = await upload(client, alice, conversation, recording(tmp_path))

    sent = await send_voice(client, alice, conversation, attachment_id)
    assert sent.status_code == 201, sent.text
    assert_matches(sent, "sendMessage")
    message = sent.json()
    assert message["text"] == ""
    assert message["attachment"] == {
        "kind": "voice",
        "status": "processing",
        "duration_ms": None,
        "url": None,
    }
    [created] = [e for _, e in fake.sent if e["type"] == "message.created"]
    assert created["message"]["attachment"]["status"] == "processing"

    await run_jobs(s3_settings, database, fake)

    [updated] = [e for _, e in fake.sent if e["type"] == "message.updated"]
    voice = updated["message"]["attachment"]
    assert voice["status"] == "ready" and 1900 <= voice["duration_ms"] <= 2100
    page = await client.get(f"/conversations/{conversation}/messages", headers=bob.headers)
    assert_matches(page, "listMessages")
    assert page.json()["items"][0]["attachment"]["status"] == "ready"
    [item] = (await client.get("/conversations", headers=bob.headers)).json()["items"]
    assert item["last_message"]["attachment"]["kind"] == "voice"

    async with httpx.AsyncClient(trust_env=False) as s3:
        played = await s3.get(voice["url"])
        original = await s3.get(Storage(s3_settings).presign_get(f"chat/uploads/{attachment_id}"))
    assert played.status_code == 200 and original.status_code == 404
    (tmp_path / "voice.m4a").write_bytes(played.content)
    info = probe(tmp_path / "voice.m4a")
    [stream] = info["streams"]
    assert stream["codec_name"] == "aac" and stream["channels"] == 1
    assert "title" not in info["format"].get("tags", {})  # metadata of the original is gone

    # Voice can't be edited; deleting it deletes the file too.
    edit = await client.patch(
        f"/conversations/{conversation}/messages/{message['id']}",
        json={"text": "текст"},
        headers=alice.headers,
    )
    assert edit.status_code == 422
    removed = await client.delete(
        f"/conversations/{conversation}/messages/{message['id']}", headers=alice.headers
    )
    assert removed.status_code == 204
    async with database.sessionmaker() as session:
        jobs = list(await session.scalars(select(Job).where(Job.kind == "media.delete_files")))
        assert any(f"chat/voice/{attachment_id}.m4a" in j.payload["keys"] for j in jobs)
        assert await session.get(chat.Attachment, uuid.UUID(attachment_id)) is None


async def test_voice_uploads_are_checked(
    voice_app: tuple[httpx.AsyncClient, FakeRealtime],
    s3_settings: Settings,
    database: Database,
) -> None:
    client, fake = voice_app
    alice, bob = await pair(client)
    conversation = (await open_dm(client, alice, bob))["id"]
    broken = await upload(client, alice, conversation, b"not a recording at all")

    both = await client.post(
        f"/conversations/{conversation}/messages",
        json={"client_id": str(uuid.uuid4()), "attachment_id": broken, "text": "и текст"},
        headers=alice.headers,
    )
    neither = await client.post(
        f"/conversations/{conversation}/messages",
        json={"client_id": str(uuid.uuid4())},
        headers=alice.headers,
    )
    not_hers = await send_voice(client, bob, conversation, broken)
    video = await client.post(
        f"/conversations/{conversation}/uploads",
        json={"kind": "voice", "content_type": "video/mp4", "size_bytes": 10},
        headers=alice.headers,
    )
    assert both.status_code == neither.status_code == not_hers.status_code == 422
    assert video.status_code == 422

    assert (await send_voice(client, alice, conversation, broken)).status_code == 201
    again = await send_voice(client, alice, conversation, broken)
    assert again.status_code == 422  # already sent
    assert (await send(client, alice, conversation, "обычный текст")).status_code == 201

    await run_jobs(s3_settings, database, fake)
    [updated] = [e for _, e in fake.sent if e["type"] == "message.updated"]
    assert updated["message"]["attachment"]["status"] == "failed"

    stranger_chat = await client.post(
        f"/conversations/{uuid.uuid4()}/uploads",
        json={"kind": "voice", "content_type": "audio/mp4", "size_bytes": 10},
        headers=alice.headers,
    )
    assert stranger_chat.status_code == 404
