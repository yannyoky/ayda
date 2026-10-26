import uuid

from fastapi import APIRouter, Response

from ayda.api.deps import Consented, CurrentUser, DbSession
from ayda.api.schemas import (
    ConsentInput,
    Habit,
    HabitCreate,
    InterestSelection,
    Items,
    Me,
    ProfileUpdate,
)
from ayda.app import privacy, profile
from ayda.core.problems import Problem
from ayda.modules import auth, habits

router = APIRouter(tags=["profile"])


@router.get("/me", operation_id="getMe")
async def get_me(user: CurrentUser, session: DbSession) -> Me:
    return await profile.build_me(session, user)


@router.delete("/me", operation_id="requestAccountDeletion", status_code=202)
async def request_account_deletion(user: CurrentUser, session: DbSession) -> Response:
    await privacy.request_deletion(session, user)
    await session.commit()
    return Response(status_code=202)


@router.patch("/me/profile", operation_id="updateProfile", dependencies=[Consented])
async def update_profile(body: ProfileUpdate, user: CurrentUser, session: DbSession) -> Me:
    await profile.update_profile(session, user, body)
    await session.commit()
    return await profile.build_me(session, user)


@router.post("/me/onboarding/complete", operation_id="completeOnboarding", dependencies=[Consented])
async def complete_onboarding(user: CurrentUser, session: DbSession) -> Me:
    await profile.complete_onboarding(session, user)
    await session.commit()
    return await profile.build_me(session, user)


@router.post("/me/consents", operation_id="acceptConsent", status_code=204)
async def accept_consent(body: ConsentInput, user: CurrentUser, session: DbSession) -> Response:
    if body.version != auth.CURRENT_CONSENT_VERSION:
        raise Problem(422, "unknown-consent-version", detail="Неизвестная версия согласия")
    await auth.accept_consent(session, user.id, body.version)
    await session.commit()
    return Response(status_code=204)


@router.get("/me/interests", operation_id="listMyInterests", dependencies=[Consented])
async def list_my_interests(user: CurrentUser, session: DbSession) -> InterestSelection:
    return InterestSelection(
        codes=await habits.list_interests(session, user.id),
        tags=await habits.list_tags(session, user.id),
    )


@router.put("/me/interests", operation_id="setMyInterests", dependencies=[Consented])
async def set_my_interests(
    body: InterestSelection, user: CurrentUser, session: DbSession
) -> InterestSelection:
    try:
        codes, tags = await habits.set_interests(session, user.id, body.codes, body.tags)
    except habits.InterestsError as exc:
        raise Problem(422, "invalid-interests", detail=str(exc)) from None
    await session.commit()
    return InterestSelection(codes=codes, tags=tags)


def _habit(h: habits.UserHabit) -> Habit:
    return Habit(id=h.id, direction="more" if h.direction == "more" else "less", text=h.text)


@router.get("/me/habits", operation_id="listMyHabits", dependencies=[Consented])
async def list_my_habits(user: CurrentUser, session: DbSession) -> Items[Habit]:
    return Items(items=[_habit(h) for h in await habits.list_habits(session, user.id)])


@router.post("/me/habits", operation_id="addMyHabit", dependencies=[Consented], status_code=201)
async def add_my_habit(body: HabitCreate, user: CurrentUser, session: DbSession) -> Habit:
    try:
        habit = await habits.add_habit(session, user.id, body.direction, body.text)
    except habits.HabitLimitError:
        raise Problem(422, "too-many-habits", detail="Слишком много привычек") from None
    await session.commit()
    return _habit(habit)


@router.delete(
    "/me/habits/{habit_id}", operation_id="deleteMyHabit", dependencies=[Consented], status_code=204
)
async def delete_my_habit(habit_id: uuid.UUID, user: CurrentUser, session: DbSession) -> Response:
    if not await habits.delete_habit(session, user.id, habit_id):
        raise Problem(404, "habit-not-found")
    await session.commit()
    return Response(status_code=204)
