"""Private S3-compatible object storage (in Russia) behind presigned URLs.

boto3 is synchronous; network calls run in a thread. Presigning is local signing only.
"""

import asyncio
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from ayda.core.config import Settings

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client
else:
    S3Client = Any

UPLOAD_TTL = timedelta(minutes=15)
READ_TTL = timedelta(hours=1)


class ObjectMissing(LookupError):
    pass


def _client(settings: Settings, endpoint: str) -> S3Client:
    def secret(value: Any) -> str | None:
        return value.get_secret_value() if value is not None else None

    return boto3.client(  # pyright: ignore[reportUnknownMemberType]
        "s3",
        endpoint_url=endpoint,
        region_name=settings.s3_region,
        aws_access_key_id=secret(settings.s3_access_key_id),
        aws_secret_access_key=secret(settings.s3_secret_access_key),
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


class Storage:
    def __init__(self, settings: Settings, bucket: str | None = None) -> None:
        self.bucket = bucket or settings.s3_bucket
        self._s3 = _client(settings, settings.s3_endpoint_url)
        # URLs handed to clients may need the public host (e.g. MinIO behind a proxy).
        public = settings.s3_public_endpoint_url or settings.s3_endpoint_url
        self._presigner = _client(settings, public)

    def presign_put(self, key: str, content_type: str, size_bytes: int) -> str:
        """Content type and exact length are signed, so the client can't send another file."""
        return self._presigner.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self.bucket,
                "Key": key,
                "ContentType": content_type,
                "ContentLength": size_bytes,
            },
            ExpiresIn=int(UPLOAD_TTL.total_seconds()),
        )

    def presign_get(self, key: str) -> str:
        return self._presigner.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=int(READ_TTL.total_seconds()),
        )

    async def get(self, key: str, max_bytes: int) -> bytes:
        def run() -> bytes:
            try:
                obj = self._s3.get_object(Bucket=self.bucket, Key=key)
            except ClientError as exc:
                if exc.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
                    raise ObjectMissing(key) from None
                raise
            return obj["Body"].read(max_bytes + 1)

        return await asyncio.to_thread(run)

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        await asyncio.to_thread(
            self._s3.put_object, Bucket=self.bucket, Key=key, Body=data, ContentType=content_type
        )

    async def upload_file(self, path: str, key: str) -> None:
        await asyncio.to_thread(self._s3.upload_file, path, self.bucket, key)

    async def download_file(self, key: str, path: str) -> None:
        await asyncio.to_thread(self._s3.download_file, self.bucket, key, path)

    async def list_keys(self, prefix: str) -> list[tuple[str, datetime]]:
        """(key, last modified) of every object under the prefix."""

        def run() -> list[tuple[str, datetime]]:
            out: list[tuple[str, datetime]] = []
            for page in self._s3.get_paginator("list_objects_v2").paginate(
                Bucket=self.bucket, Prefix=prefix
            ):
                for obj in page.get("Contents", []):
                    key, modified = obj.get("Key"), obj.get("LastModified")
                    if key is not None and modified is not None:
                        out.append((key, modified))
            return out

        return await asyncio.to_thread(run)

    async def delete(self, keys: Sequence[str]) -> None:
        if not keys:
            return
        objects: Any = [{"Key": k} for k in keys]
        await asyncio.to_thread(
            self._s3.delete_objects, Bucket=self.bucket, Delete={"Objects": objects}
        )
