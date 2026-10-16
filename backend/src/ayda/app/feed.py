"""Feed assembly across modules: posts and comments (social) with author names (auth)."""

import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from ayda.api.schemas import Comment, Photo, Post, UserSummary
from ayda.core.storage import Storage
from ayda.modules import auth, social

DELETED_NAME = "Удалённый пользователь"


def user_summary(user: auth.User | None, user_id: uuid.UUID) -> UserSummary:
    if user is None or user.deletion_requested_at is not None:
        return UserSummary(id=user_id, first_name=DELETED_NAME, avatar_url=None)
    return UserSummary(id=user.id, first_name=user.first_name, avatar_url=user.avatar_url)


async def build_posts(
    session: AsyncSession, storage: Storage, viewer_id: uuid.UUID, posts: Sequence[social.Post]
) -> list[Post]:
    ids = [p.id for p in posts]
    authors = await auth.get_users(session, list({p.author_id for p in posts}))
    stats = await social.post_stats(session, viewer_id, ids)
    photos = await social.post_photos(session, ids)
    out: list[Post] = []
    for post in posts:
        proof = post.kind == "proof"
        urls = [(m, social.photo_url(storage, m)) for m in photos.get(post.id, []) if proof]
        out.append(
            Post(
                id=post.id,
                author=user_summary(authors.get(post.author_id), post.author_id),
                kind="proof" if proof else "routine",
                quest_title=post.quest_title if proof else None,
                category=post.category,  # pyright: ignore[reportArgumentType]
                caption=post.caption if proof else None,
                photos=[
                    Photo(id=m.id, url=url, width=m.width or 0, height=m.height or 0)
                    for m, url in urls
                    if url is not None
                ],
                local_date=post.local_date,
                created_at=post.created_at,
                like_count=stats[post.id].like_count,
                liked_by_me=stats[post.id].liked_by_me,
                comment_count=stats[post.id].comment_count,
            )
        )
    return out


async def build_comments(
    session: AsyncSession,
    viewer_id: uuid.UUID,
    post: social.Post,
    comments: Sequence[social.Comment],
) -> list[Comment]:
    authors = await auth.get_users(session, list({c.author_id for c in comments}))
    return [
        Comment(
            id=c.id,
            author=user_summary(authors.get(c.author_id), c.author_id),
            text=c.text,
            created_at=c.created_at,
            can_delete=viewer_id in (c.author_id, post.author_id),
        )
        for c in comments
    ]
