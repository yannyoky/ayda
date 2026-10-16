"""The friends feed: posts of a user and their friends, likes and comments.

Callers check visibility with `visible_post` (author or a friend of the author) before
reading or reacting; a former friend loses access the moment the friendship is removed.
"""

import base64
import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ayda.modules.social.friends import are_friends
from ayda.modules.social.media import photo_key, upload_key
from ayda.modules.social.models import Comment, Like, Media, Post

MAX_COMMENTS_PER_HOUR = 60
DELETE_FILES_JOB = "media.delete_files"


class CursorError(ValueError):
    pass


class CommentLimitError(Exception):
    pass


def encode_cursor(created_at: datetime, item_id: uuid.UUID) -> str:
    raw = json.dumps([created_at.isoformat(), str(item_id)]).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        created_at, item_id = json.loads(raw)
        return datetime.fromisoformat(created_at), uuid.UUID(item_id)
    except (ValueError, TypeError) as exc:
        raise CursorError(str(exc)) from None


async def visible_post(
    session: AsyncSession, viewer_id: uuid.UUID, post_id: uuid.UUID
) -> Post | None:
    post = await session.get(Post, post_id)
    if post is None or post.deleted_at is not None:
        return None
    if post.author_id == viewer_id or await are_friends(session, viewer_id, post.author_id):
        return post
    return None


async def feed_page(
    session: AsyncSession,
    author_ids: Sequence[uuid.UUID],
    cursor: str | None,
    limit: int,
) -> tuple[list[Post], str | None]:
    """Newest first. `author_ids` is the viewer and their friends."""
    query = select(Post).where(Post.author_id.in_(author_ids), Post.deleted_at.is_(None))
    if cursor:
        created_at, post_id = decode_cursor(cursor)
        query = query.where(
            or_(
                Post.created_at < created_at, and_(Post.created_at == created_at, Post.id < post_id)
            )
        )
    rows = list(
        await session.scalars(
            query.order_by(Post.created_at.desc(), Post.id.desc()).limit(limit + 1)
        )
    )
    next_cursor = (
        encode_cursor(rows[limit - 1].created_at, rows[limit - 1].id) if len(rows) > limit else None
    )
    return rows[:limit], next_cursor


@dataclass(frozen=True)
class PostStats:
    like_count: int
    liked_by_me: bool
    comment_count: int


async def post_stats(
    session: AsyncSession, viewer_id: uuid.UUID, post_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, PostStats]:
    if not post_ids:
        return {}
    like_rows = await session.execute(
        select(Like.post_id, func.count()).where(Like.post_id.in_(post_ids)).group_by(Like.post_id)
    )
    likes: dict[uuid.UUID, int] = {pid: n for pid, n in like_rows}
    mine = set(
        await session.scalars(
            select(Like.post_id).where(Like.post_id.in_(post_ids), Like.user_id == viewer_id)
        )
    )
    comment_rows = await session.execute(
        select(Comment.post_id, func.count())
        .where(Comment.post_id.in_(post_ids), Comment.deleted_at.is_(None))
        .group_by(Comment.post_id)
    )
    comments: dict[uuid.UUID, int] = {pid: n for pid, n in comment_rows}
    return {
        pid: PostStats(likes.get(pid, 0), pid in mine, comments.get(pid, 0)) for pid in post_ids
    }


async def post_photos(
    session: AsyncSession, post_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, list[Media]]:
    """Cleaned photos only, in upload order."""
    out: dict[uuid.UUID, list[Media]] = {}
    if not post_ids:
        return out
    rows = await session.scalars(
        select(Media)
        .where(Media.post_id.in_(post_ids), Media.status == "ready")
        .order_by(Media.created_at, Media.id)
    )
    for media in rows:
        assert media.post_id is not None
        out.setdefault(media.post_id, []).append(media)
    return out


async def like(session: AsyncSession, post: Post, user_id: uuid.UUID, now: datetime) -> bool:
    """True when the like is new."""
    result = await session.execute(
        insert(Like)
        .values(post_id=post.id, user_id=user_id, created_at=now)
        .on_conflict_do_nothing()
        .returning(Like.user_id)
    )
    return result.first() is not None


async def unlike(session: AsyncSession, post: Post, user_id: uuid.UUID) -> None:
    await session.execute(delete(Like).where(Like.post_id == post.id, Like.user_id == user_id))


async def add_comment(
    session: AsyncSession, post: Post, author_id: uuid.UUID, text: str, now: datetime
) -> Comment:
    recent = await session.scalar(
        select(func.count())
        .select_from(Comment)
        .where(Comment.author_id == author_id, Comment.created_at > now - timedelta(hours=1))
    )
    if (recent or 0) >= MAX_COMMENTS_PER_HOUR:
        raise CommentLimitError
    comment = Comment(post_id=post.id, author_id=author_id, text=text, created_at=now)
    session.add(comment)
    await session.flush()
    return comment


async def comments_page(
    session: AsyncSession, post: Post, cursor: str | None, limit: int
) -> tuple[list[Comment], str | None]:
    """Oldest first."""
    query = select(Comment).where(Comment.post_id == post.id, Comment.deleted_at.is_(None))
    if cursor:
        created_at, comment_id = decode_cursor(cursor)
        query = query.where(
            or_(
                Comment.created_at > created_at,
                and_(Comment.created_at == created_at, Comment.id > comment_id),
            )
        )
    rows = list(
        await session.scalars(query.order_by(Comment.created_at, Comment.id).limit(limit + 1))
    )
    last = rows[limit - 1] if len(rows) > limit else None
    return rows[:limit], encode_cursor(last.created_at, last.id) if last else None


async def get_comment(session: AsyncSession, comment_id: uuid.UUID) -> Comment | None:
    comment = await session.get(Comment, comment_id)
    return comment if comment is not None and comment.deleted_at is None else None


async def delete_comment(session: AsyncSession, comment: Comment, now: datetime) -> None:
    comment.deleted_at = now
    await session.flush()


async def delete_post(session: AsyncSession, post: Post, now: datetime) -> list[str]:
    """Hide the post and delete its photo rows; returns the storage keys for the caller to
    delete with DELETE_FILES_JOB (retried by the worker). Points are not touched."""
    media = list(await session.scalars(select(Media).where(Media.post_id == post.id)))
    keys = [k for m in media for k in {m.storage_key, upload_key(m.id), photo_key(m.id)}]
    for item in media:
        await session.delete(item)
    post.deleted_at = now
    post.caption = None
    post.quest_title = None
    await session.flush()
    return keys


async def reaction_recipients(
    session: AsyncSession, start: datetime, end: datetime
) -> set[uuid.UUID]:
    """Authors of live posts that got likes or comments from others in [start, end)."""
    likes = (
        select(Post.author_id)
        .join(Like, Like.post_id == Post.id)
        .where(Like.created_at >= start, Like.created_at < end, Like.user_id != Post.author_id)
    )
    comments = (
        select(Post.author_id)
        .join(Comment, Comment.post_id == Post.id)
        .where(
            Comment.created_at >= start,
            Comment.created_at < end,
            Comment.author_id != Post.author_id,
            Comment.deleted_at.is_(None),
        )
    )
    rows = await session.scalars(likes.where(Post.deleted_at.is_(None)).union(comments))
    return set(rows)


async def reaction_counts(
    session: AsyncSession, author_id: uuid.UUID, start: datetime, end: datetime
) -> tuple[int, int]:
    """(likes, comments) from others on the author's live posts in [start, end)."""
    likes = await session.scalar(
        select(func.count())
        .select_from(Like)
        .join(Post, Like.post_id == Post.id)
        .where(
            Post.author_id == author_id,
            Post.deleted_at.is_(None),
            Like.user_id != author_id,
            Like.created_at >= start,
            Like.created_at < end,
        )
    )
    comments = await session.scalar(
        select(func.count())
        .select_from(Comment)
        .join(Post, Comment.post_id == Post.id)
        .where(
            Post.author_id == author_id,
            Post.deleted_at.is_(None),
            Comment.author_id != author_id,
            Comment.deleted_at.is_(None),
            Comment.created_at >= start,
            Comment.created_at < end,
        )
    )
    return likes or 0, comments or 0
