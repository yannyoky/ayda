import io
import socket
import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta

import boto3
import httpx
import pytest
from fastapi import FastAPI
from moto.server import ThreadedMotoServer
from PIL import Image
from pydantic import SecretStr
from sqlalchemy import select

from ayda.core.config import Settings
from ayda.core.db import Database
from ayda.core.jobs import enqueue
from ayda.core.storage import Storage
from ayda.main import create_app
from ayda.modules import social
from ayda.modules.social.images import MAX_SIDE, InvalidImage, clean_photo
from ayda.modules.social.media import MAX_UPLOADS_PER_DAY
from ayda.worker import build_worker
from tests.contract import assert_matches
from tests.helpers import sign_in

GPS_TAG = 0x8825
ORIENTATION_TAG = 0x0112


def photo(fmt: str = "JPEG", size: tuple[int, int] = (3000, 2000), rotate: bool = False) -> bytes:
    image = Image.new("RGB", size, (200, 30, 90))
    exif = Image.Exif()
    exif[0x010F] = "PhoneMaker"
    exif[GPS_TAG] = {1: "N", 2: (55.0, 45.0, 0.0)}
    if rotate:
        exif[ORIENTATION_TAG] = 6  # rotate 90° when shown
    out = io.BytesIO()
    image.save(out, fmt, exif=exif.tobytes())
    return out.getvalue()


def test_clean_photo_strips_metadata_and_resizes() -> None:
    jpeg, width, height = clean_photo(photo(rotate=True))

    cleaned = Image.open(io.BytesIO(jpeg))
    assert cleaned.format == "JPEG"
    assert (width, height) == cleaned.size == (1067, MAX_SIDE)  # orientation applied
    assert not cleaned.getexif() and "exif" not in cleaned.info


@pytest.mark.parametrize("fmt", ["PNG", "WEBP"])
def test_clean_photo_other_formats(fmt: str) -> None:
    _, width, height = clean_photo(photo(fmt, (800, 600)))
    assert (width, height) == (800, 600)


@pytest.mark.parametrize("data", [b"not an image", b"GIF89a" + b"\0" * 100])
def test_clean_photo_rejects_non_photos(data: bytes) -> None:
    with pytest.raises(InvalidImage):
        clean_photo(data)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def s3_url() -> Iterator[str]:
    port = _free_port()
    server = ThreadedMotoServer(ip_address="127.0.0.1", port=port, verbose=False)
    server.start()
    yield f"http://127.0.0.1:{port}"
    server.stop()


@pytest.fixture
def s3_settings(settings: Settings, s3_url: str) -> Settings:
    updated = settings.model_copy(
        update={
            "s3_endpoint_url": s3_url,
            "s3_bucket": f"test-{uuid.uuid4().hex[:8]}",
            "s3_access_key_id": SecretStr("test"),
            "s3_secret_access_key": SecretStr("test"),
            "s3_region": "us-east-1",
        }
    )
    boto3.client(  # pyright: ignore[reportUnknownMemberType]
        "s3",
        endpoint_url=s3_url,
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    ).create_bucket(Bucket=updated.s3_bucket)
    return updated


@pytest.fixture
async def s3_client(s3_settings: Settings) -> AsyncIterator[tuple[FastAPI, httpx.AsyncClient]]:
    app = create_app(s3_settings)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
        yield app, c
    await app.state.db.dispose()


async def upload(client: httpx.AsyncClient, headers: dict[str, str], data: bytes) -> str:
    response = await client.post(
        "/media/uploads",
        json={"content_type": "image/jpeg", "size_bytes": len(data)},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    assert_matches(response, "createUpload")
    slot = response.json()
    async with httpx.AsyncClient(trust_env=False) as s3:
        put = await s3.put(slot["upload_url"], content=data, headers=slot["headers"])
    assert put.status_code == 200, put.text
    return slot["media_id"]


async def media_row(database: Database, media_id: str) -> social.Media:
    async with database.sessionmaker() as session:
        media = await session.get(social.Media, uuid.UUID(media_id))
        assert media is not None
        return media


async def run_processing(s3_settings: Settings, database: Database, media_id: str) -> None:
    async with database.sessionmaker() as session:
        await enqueue(session, social.PROCESS_JOB, {"media_id": media_id})
        await session.commit()
    worker = build_worker(s3_settings, database, Storage(s3_settings))
    assert await worker.run_one()


async def test_upload_is_cleaned_before_it_can_be_seen(
    s3_client: tuple[FastAPI, httpx.AsyncClient], s3_settings: Settings, database: Database
) -> None:
    _, client = s3_client
    user = await sign_in(client)
    media_id = await upload(client, user.headers, photo())
    storage = Storage(s3_settings)

    pending = await media_row(database, media_id)
    assert pending.status == "pending" and social.photo_url(storage, pending) is None

    await run_processing(s3_settings, database, media_id)

    ready = await media_row(database, media_id)
    assert ready.status == "ready" and (ready.width, ready.height) == (MAX_SIDE, 1067)
    url = social.photo_url(storage, ready)
    assert url is not None
    async with httpx.AsyncClient(trust_env=False) as s3:
        served = await s3.get(url)
        original = await s3.get(storage.presign_get(f"uploads/{media_id}"))
    assert served.status_code == 200
    assert not Image.open(io.BytesIO(served.content)).getexif()
    assert original.status_code == 404  # the upload with GPS is gone


async def test_broken_upload_fails_and_is_deleted(
    s3_client: tuple[FastAPI, httpx.AsyncClient], s3_settings: Settings, database: Database
) -> None:
    _, client = s3_client
    user = await sign_in(client)
    media_id = await upload(client, user.headers, b"definitely not a photo")

    await run_processing(s3_settings, database, media_id)

    assert (await media_row(database, media_id)).status == "failed"


async def test_upload_validation_and_daily_limit(
    s3_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    _, client = s3_client
    user = await sign_in(client)

    too_big = await client.post(
        "/media/uploads",
        json={"content_type": "image/jpeg", "size_bytes": 10 * 1024 * 1024 + 1},
        headers=user.headers,
    )
    gif = await client.post(
        "/media/uploads", json={"content_type": "image/gif", "size_bytes": 10}, headers=user.headers
    )
    assert too_big.status_code == 422 and gif.status_code == 422

    for _ in range(MAX_UPLOADS_PER_DAY):
        ok = await client.post(
            "/media/uploads",
            json={"content_type": "image/png", "size_bytes": 10},
            headers=user.headers,
        )
        assert ok.status_code == 201
    over = await client.post(
        "/media/uploads", json={"content_type": "image/png", "size_bytes": 10}, headers=user.headers
    )
    assert over.status_code == 429


async def test_unattached_uploads_are_deleted_after_a_day(
    s3_client: tuple[FastAPI, httpx.AsyncClient], s3_settings: Settings, database: Database
) -> None:
    _, client = s3_client
    user = await sign_in(client)
    media_id = await upload(client, user.headers, photo())
    storage = Storage(s3_settings)

    async with database.sessionmaker() as session:
        assert await social.delete_unattached(session, storage, datetime.now(UTC)) == 0
        later = datetime.now(UTC) + timedelta(days=1, minutes=1)
        assert await social.delete_unattached(session, storage, later) == 1
        await session.commit()
        assert await session.scalar(select(social.Media)) is None
    async with httpx.AsyncClient(trust_env=False) as s3:
        assert (await s3.get(storage.presign_get(f"uploads/{media_id}"))).status_code == 404
