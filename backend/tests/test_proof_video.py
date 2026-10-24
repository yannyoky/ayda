import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select

from ayda.core.config import Settings
from ayda.core.db import Database
from ayda.core.jobs import Job
from ayda.core.storage import Storage
from ayda.main import create_app
from ayda.modules import social
from ayda.worker import build_worker
from tests.contract import assert_matches
from tests.helpers import SignedIn
from tests.test_chat_voice import circle, probe
from tests.test_completion import complete, own_quest
from tests.test_day import onboarded
from tests.test_media import photo


@pytest.fixture
async def s3_client(s3_settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    app: FastAPI = create_app(s3_settings)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
        yield c
    await app.state.db.dispose()


async def upload(
    client: httpx.AsyncClient, user: SignedIn, data: bytes, kind: str, content_type: str
) -> str:
    response = await client.post(
        "/media/uploads",
        json={"kind": kind, "content_type": content_type, "size_bytes": len(data)},
        headers=user.headers,
    )
    assert response.status_code == 201, response.text
    assert_matches(response, "createUpload")
    slot = response.json()
    async with httpx.AsyncClient(trust_env=False) as s3:
        put = await s3.put(slot["upload_url"], content=data, headers=slot["headers"])
    assert put.status_code == 200, put.text
    return slot["media_id"]


async def run_jobs(s3_settings: Settings, database: Database) -> None:
    worker = build_worker(s3_settings, database, Storage(s3_settings))
    while await worker.run_one():
        pass


async def my_post(client: httpx.AsyncClient, user: SignedIn) -> dict[str, object]:
    feed = await client.get("/feed", headers=user.headers)
    assert_matches(feed, "getFeed")
    [post] = feed.json()["items"]
    return post


async def test_a_video_proof_is_re_encoded_and_goes_after_30_days(
    s3_client: httpx.AsyncClient, s3_settings: Settings, database: Database, tmp_path: Path
) -> None:
    client = s3_client
    user = await onboarded(client)
    # A landscape VP8 video with a location tag; it should come out 720x404 or so.
    source = circle(tmp_path, seconds=3)
    media_id = await upload(client, user, source, "video", "video/webm")

    done = await complete(
        client, user, await own_quest(client, user), visibility="friends", media_ids=[media_id]
    )
    assert done.status_code == 200, done.text
    processing = await my_post(client, user)
    assert processing["photos"] == []
    assert processing["video"] == {
        "id": media_id,
        "kind": "video",
        "status": "processing",
        "url": None,
        "duration_ms": None,
        "width": None,
        "height": None,
    }

    await run_jobs(s3_settings, database)

    video = (await my_post(client, user))["video"]
    assert isinstance(video, dict)
    assert video["status"] == "ready" and 2900 <= video["duration_ms"] <= 3100
    assert (video["width"], video["height"]) == (640, 360)  # never upscaled
    async with httpx.AsyncClient(trust_env=False) as s3:
        played = await s3.get(video["url"])
    (tmp_path / "out.mp4").write_bytes(played.content)
    info = probe(tmp_path / "out.mp4")
    streams = {s["codec_type"]: s for s in info["streams"]}
    assert streams["video"]["codec_name"] == "h264" and streams["audio"]["codec_name"] == "aac"
    assert "location" not in info["format"].get("tags", {})

    async with database.sessionmaker() as session:
        assert await social.expire_videos(session, datetime.now(UTC) + timedelta(days=29)) == []
        keys = await social.expire_videos(session, datetime.now(UTC) + timedelta(days=31))
        await session.commit()
    assert f"videos/{media_id}.mp4" in keys
    expired = (await my_post(client, user))["video"]
    assert isinstance(expired, dict)
    assert (expired["status"], expired["url"]) == ("expired", None)


async def test_a_circle_proof_is_square(
    s3_client: httpx.AsyncClient, s3_settings: Settings, database: Database, tmp_path: Path
) -> None:
    client = s3_client
    user = await onboarded(client)
    media_id = await upload(client, user, circle(tmp_path), "video_note", "video/webm")
    quest_id = await own_quest(client, user)
    assert (
        await complete(client, user, quest_id, visibility="friends", media_ids=[media_id])
    ).status_code == 200

    await run_jobs(s3_settings, database)

    video = (await my_post(client, user))["video"]
    assert isinstance(video, dict)
    assert video["kind"] == "video_note" and video["status"] == "ready"
    async with httpx.AsyncClient(trust_env=False) as s3:
        played = await s3.get(video["url"])
    (tmp_path / "out.mp4").write_bytes(played.content)
    [stream] = [s for s in probe(tmp_path / "out.mp4")["streams"] if s["codec_type"] == "video"]
    assert (stream["width"], stream["height"]) == (480, 480)

    # Deleting the post deletes the video file too.
    post = await my_post(client, user)
    assert (await client.delete(f"/posts/{post['id']}", headers=user.headers)).status_code == 204
    async with database.sessionmaker() as session:
        jobs = list(await session.scalars(select(Job).where(Job.kind == "media.delete_files")))
    assert any(f"videos/{media_id}.mp4" in j.payload["keys"] for j in jobs)


async def test_a_video_goes_alone(
    s3_client: httpx.AsyncClient, database: Database, tmp_path: Path
) -> None:
    client = s3_client
    user = await onboarded(client)
    video = await upload(client, user, circle(tmp_path), "video", "video/webm")
    note = await upload(client, user, circle(tmp_path), "video_note", "video/webm")
    picture = await upload(client, user, photo(), "photo", "image/jpeg")

    for mix in ([video, picture], [video, note]):
        response = await complete(
            client, user, await own_quest(client, user), visibility="friends", media_ids=mix
        )
        assert response.status_code == 422
        assert response.json()["detail"] == "Можно приложить до 3 фото или одно видео"

    photo_as_video = await client.post(
        "/media/uploads",
        json={"kind": "video", "content_type": "image/jpeg", "size_bytes": 10},
        headers=user.headers,
    )
    big_photo = await client.post(
        "/media/uploads",
        json={"kind": "photo", "content_type": "image/jpeg", "size_bytes": 20 * 1024 * 1024},
        headers=user.headers,
    )
    big_video = await client.post(
        "/media/uploads",
        json={"kind": "video", "content_type": "video/mp4", "size_bytes": 51 * 1024 * 1024},
        headers=user.headers,
    )
    assert photo_as_video.status_code == big_photo.status_code == big_video.status_code == 422
    assert_matches(photo_as_video, "createUpload")
    async with database.sessionmaker() as session:
        row = await session.get(social.Media, uuid.UUID(video))
    assert row is not None and row.post_id is None  # the failed completions attached nothing
