import uuid
from datetime import UTC, datetime

from fastapi import APIRouter

from ayda.api.deps import Consented, CurrentUser, DbSession
from ayda.api.realtime import RealtimeDep
from ayda.api.schemas import Coop, CoopCreateInput, CoopInput, CoopItemInput, HandoffInput, Items
from ayda.app import coop as coop_app

router = APIRouter(tags=["coop"], dependencies=[Consented])


def _now() -> datetime:
    return datetime.now(UTC)


@router.post("/day-quests/{quest_id}/coop", operation_id="createCoop", status_code=201)
async def create_coop(
    quest_id: uuid.UUID,
    body: CoopInput,
    user: CurrentUser,
    session: DbSession,
    realtime: RealtimeDep,
) -> Coop:
    return await coop_app.create_coop(session, realtime, user, quest_id, body.friend_ids, _now())


@router.get("/coops", operation_id="listCoops")
async def list_coops(user: CurrentUser, session: DbSession) -> Items[Coop]:
    return Items(items=await coop_app.list_coops(session, user, _now()))


@router.get("/coops/{coop_id}", operation_id="getCoop")
async def get_coop(coop_id: uuid.UUID, user: CurrentUser, session: DbSession) -> Coop:
    return await coop_app.coop_view(session, user.id, coop_id)


@router.post("/coops/{coop_id}/accept", operation_id="acceptCoop")
async def accept_coop(
    coop_id: uuid.UUID, user: CurrentUser, session: DbSession, realtime: RealtimeDep
) -> Coop:
    return await coop_app.accept_coop(session, realtime, user, coop_id, _now())


@router.post("/coops/{coop_id}/decline", operation_id="declineCoop")
async def decline_coop(
    coop_id: uuid.UUID, user: CurrentUser, session: DbSession, realtime: RealtimeDep
) -> Coop:
    return await coop_app.decline_coop(session, realtime, user, coop_id, _now())


@router.post("/coops", operation_id="createPlan", status_code=201)
async def create_plan(
    body: CoopCreateInput, user: CurrentUser, session: DbSession, realtime: RealtimeDep
) -> Coop:
    return await coop_app.create_plan(session, realtime, user, body, _now())


@router.patch("/coops/{coop_id}/parts/{part_id}/items/{item_id}", operation_id="setCoopItem")
async def set_coop_item(
    coop_id: uuid.UUID,
    part_id: uuid.UUID,
    item_id: uuid.UUID,
    body: CoopItemInput,
    user: CurrentUser,
    session: DbSession,
    realtime: RealtimeDep,
) -> Coop:
    return await coop_app.set_item(
        session, realtime, user, coop_id, part_id, item_id, body.done, _now()
    )


@router.post("/coops/{coop_id}/parts/{part_id}/handoff", operation_id="offerHandoff")
async def offer_handoff(
    coop_id: uuid.UUID,
    part_id: uuid.UUID,
    body: HandoffInput,
    user: CurrentUser,
    session: DbSession,
    realtime: RealtimeDep,
) -> Coop:
    return await coop_app.offer_handoff(
        session, realtime, user, coop_id, part_id, body.friend_id, _now()
    )


@router.delete("/coops/{coop_id}/parts/{part_id}/handoff", operation_id="withdrawHandoff")
async def withdraw_handoff(
    coop_id: uuid.UUID,
    part_id: uuid.UUID,
    user: CurrentUser,
    session: DbSession,
    realtime: RealtimeDep,
) -> Coop:
    return await coop_app.withdraw_handoff(session, realtime, user, coop_id, part_id, _now())


@router.post("/coops/{coop_id}/parts/{part_id}/handoff/accept", operation_id="acceptHandoff")
async def accept_handoff(
    coop_id: uuid.UUID,
    part_id: uuid.UUID,
    user: CurrentUser,
    session: DbSession,
    realtime: RealtimeDep,
) -> Coop:
    return await coop_app.accept_handoff(session, realtime, user, coop_id, part_id, _now())


@router.post("/coops/{coop_id}/parts/{part_id}/handoff/decline", operation_id="declineHandoff")
async def decline_handoff(
    coop_id: uuid.UUID,
    part_id: uuid.UUID,
    user: CurrentUser,
    session: DbSession,
    realtime: RealtimeDep,
) -> Coop:
    return await coop_app.decline_handoff(session, realtime, user, coop_id, part_id, _now())
