import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query, Request, Response

from ayda.api.deps import CurrentUser, DbSession
from ayda.api.schemas import Comment, CommentInput, CommentPage, LikeState, PostPage
from ayda.app import feed
from ayda.core import jobs
from ayda.core.problems import Problem
from ayda.core.storage import Storage
from ayda.modules import analytics, social
from ayda.modules.analytics import EventType

router = APIRouter(tags=["social"])

Cursor = Annotated[str | None, Query(max_length=200)]
Limit = Annotated[int, Query(ge=1, le=50)]


def _storage(request: Request) -> Storage:
    storage: Storage = request.app.state.storage
    return storage


def _not_found() -> Problem:
    return Problem(404, "post-not-found", detail="Пост не найден")


def _bad_cursor() -> Problem:
    return Problem(422, "invalid-cursor", detail="Неверный курсор")


async def _visible(session: DbSession, user_id: uuid.UUID, post_id: uuid.UUID) -> social.Post:
    post = await social.visible_post(session, user_id, post_id)
    if post is None:
        raise _not_found()
    return post


@router.get("/feed", operation_id="getFeed")
async def get_feed(
    user: CurrentUser,
    session: DbSession,
    request: Request,
    cursor: Cursor = None,
    limit: Limit = 20,
) -> PostPage:
    authors = [user.id, *await social.friends(session, user.id)]
    try:
        posts, next_cursor = await social.feed_page(session, authors, cursor, limit)
    except social.CursorError:
        raise _bad_cursor() from None
    items = await feed.build_posts(session, _storage(request), user.id, posts)
    return PostPage(items=items, next_cursor=next_cursor)


@router.delete("/posts/{post_id}", operation_id="deletePost", status_code=204)
async def delete_post(post_id: uuid.UUID, user: CurrentUser, session: DbSession) -> Response:
    post = await _visible(session, user.id, post_id)
    if post.author_id != user.id:
        raise Problem(403, "not-your-post", detail="Удалить можно только свой пост")
    keys = await social.delete_post(session, post, datetime.now(UTC))
    if keys:
        await jobs.enqueue(session, social.DELETE_FILES_JOB, {"keys": keys})
    await session.commit()
    return Response(status_code=204)


async def _like_state(session: DbSession, user_id: uuid.UUID, post: social.Post) -> LikeState:
    stats = (await social.post_stats(session, user_id, [post.id]))[post.id]
    return LikeState(like_count=stats.like_count, liked_by_me=stats.liked_by_me)


@router.put("/posts/{post_id}/like", operation_id="likePost")
async def like_post(post_id: uuid.UUID, user: CurrentUser, session: DbSession) -> LikeState:
    post = await _visible(session, user.id, post_id)
    now = datetime.now(UTC)
    if await social.like(session, post, user.id, now):
        await analytics.record(
            session,
            EventType.REACTION_ADDED,
            user.id,
            {"post_id": post.id, "post_author_id": post.author_id, "reaction": "like"},
            occurred_at=now,
        )
    await session.commit()
    return await _like_state(session, user.id, post)


@router.delete("/posts/{post_id}/like", operation_id="unlikePost")
async def unlike_post(post_id: uuid.UUID, user: CurrentUser, session: DbSession) -> LikeState:
    post = await _visible(session, user.id, post_id)
    await social.unlike(session, post, user.id)
    await session.commit()
    return await _like_state(session, user.id, post)


@router.get("/posts/{post_id}/comments", operation_id="listComments")
async def list_comments(
    post_id: uuid.UUID,
    user: CurrentUser,
    session: DbSession,
    cursor: Cursor = None,
    limit: Limit = 20,
) -> CommentPage:
    post = await _visible(session, user.id, post_id)
    try:
        comments, next_cursor = await social.comments_page(session, post, cursor, limit)
    except social.CursorError:
        raise _bad_cursor() from None
    items = await feed.build_comments(session, user.id, post, comments)
    return CommentPage(items=items, next_cursor=next_cursor)


@router.post("/posts/{post_id}/comments", operation_id="addComment", status_code=201)
async def add_comment(
    post_id: uuid.UUID, body: CommentInput, user: CurrentUser, session: DbSession
) -> Comment:
    post = await _visible(session, user.id, post_id)
    now = datetime.now(UTC)
    try:
        comment = await social.add_comment(session, post, user.id, body.text, now)
    except social.CommentLimitError:
        raise Problem(429, "too-many-comments", detail="Слишком много комментариев") from None
    await analytics.record(
        session,
        EventType.REACTION_ADDED,
        user.id,
        {"post_id": post.id, "post_author_id": post.author_id, "reaction": "comment"},
        occurred_at=now,
    )
    await session.commit()
    [item] = await feed.build_comments(session, user.id, post, [comment])
    return item


@router.delete("/comments/{comment_id}", operation_id="deleteComment", status_code=204)
async def delete_comment(comment_id: uuid.UUID, user: CurrentUser, session: DbSession) -> Response:
    comment = await social.get_comment(session, comment_id)
    post = await social.visible_post(session, user.id, comment.post_id) if comment else None
    if comment is None or post is None:
        raise Problem(404, "comment-not-found", detail="Комментарий не найден")
    if user.id not in (comment.author_id, post.author_id):
        raise Problem(403, "not-your-comment", detail="Удалить может автор или владелец поста")
    await social.delete_comment(session, comment, datetime.now(UTC))
    await session.commit()
    return Response(status_code=204)
