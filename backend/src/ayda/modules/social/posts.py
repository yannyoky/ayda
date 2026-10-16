"""Proofs and routine entries in the feed."""

import uuid
from collections.abc import Sequence
from datetime import date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from ayda.modules.social.media import claim_media
from ayda.modules.social.models import Post


async def create_post(
    session: AsyncSession,
    *,
    author_id: uuid.UUID,
    day_quest_id: uuid.UUID,
    kind: str,
    quest_title: str,
    category: str,
    caption: str | None,
    local_date: date,
    media_ids: Sequence[uuid.UUID],
    now: datetime,
) -> tuple[Post, list[uuid.UUID]]:
    """A `routine` post keeps only the category. Returns the post and the ids of attached
    photos that still need cleaning (the caller enqueues the media job for them)."""
    proof = kind == "proof"
    media = await claim_media(session, author_id, media_ids) if proof else []
    post = Post(
        author_id=author_id,
        day_quest_id=day_quest_id,
        kind=kind,
        quest_title=quest_title if proof else None,
        category=category,
        caption=(caption or None) if proof else None,
        local_date=local_date,
        created_at=now,
    )
    session.add(post)
    await session.flush()
    to_process: list[uuid.UUID] = []
    for item in media:
        item.post_id = post.id
        if item.status == "pending":
            item.status = "processing"
            to_process.append(item.id)
    await session.flush()
    return post, to_process
