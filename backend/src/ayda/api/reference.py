from typing import Annotated

from fastapi import APIRouter, Query

from ayda.api.deps import CurrentUser, DbSession
from ayda.api.schemas import City, Interest, Items
from ayda.app.profile import city_schema
from ayda.core.problems import Problem
from ayda.modules import events, habits

router = APIRouter(tags=["reference"])


@router.get("/cities", operation_id="searchCities")
async def search_cities(
    _: CurrentUser,
    session: DbSession,
    query: Annotated[str | None, Query(min_length=2, max_length=100)] = None,
    lat: Annotated[float | None, Query(ge=-90, le=90)] = None,
    lon: Annotated[float | None, Query(ge=-180, le=180)] = None,
    limit: Annotated[int, Query(ge=1, le=20)] = 10,
) -> Items[City]:
    # Coordinates are used for this lookup only; they are never stored or logged.
    if lat is not None and lon is not None:
        cities = await events.nearest_cities(session, lat, lon, limit)
    elif query is not None and lat is None and lon is None:
        cities = await events.search_cities(session, query, limit)
    else:
        raise Problem(422, "validation-failed", detail="Нужен query или lat и lon")
    return Items(items=[city_schema(c) for c in cities])


@router.get("/interests", operation_id="listInterests")
async def list_interests(_: CurrentUser) -> Items[Interest]:
    return Items(items=[Interest(code=i.code, title=i.title) for i in habits.INTERESTS])
