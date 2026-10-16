from fastapi import APIRouter

from ayda.api.deps import CurrentUser, DbSession
from ayda.api.schemas import Me
from ayda.app.profile import build_me

router = APIRouter(tags=["profile"])


@router.get("/me", operation_id="getMe")
async def get_me(user: CurrentUser, session: DbSession) -> Me:
    return await build_me(session, user)
