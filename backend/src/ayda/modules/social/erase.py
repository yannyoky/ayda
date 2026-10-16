import uuid

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ayda.modules.social.media import photo_key, upload_key
from ayda.modules.social.models import Comment, Friendship, Invite, Like, Media, Post


async def erase_user(session: AsyncSession, user_id: uuid.UUID) -> list[str]:
    """Delete everything the user wrote or uploaded; returns storage keys to delete."""
    media = list(await session.scalars(select(Media).where(Media.owner_id == user_id)))
    keys = [k for m in media for k in {m.storage_key, upload_key(m.id), photo_key(m.id)}]
    await session.execute(delete(Media).where(Media.owner_id == user_id))
    await session.execute(delete(Comment).where(Comment.author_id == user_id))
    await session.execute(delete(Like).where(Like.user_id == user_id))
    # Likes and comments of others on the user's posts go with the posts (ON DELETE CASCADE).
    await session.execute(delete(Post).where(Post.author_id == user_id))
    await session.execute(
        delete(Friendship).where(
            or_(Friendship.user_low == user_id, Friendship.user_high == user_id)
        )
    )
    await session.execute(delete(Invite).where(Invite.inviter_id == user_id))
    return keys
