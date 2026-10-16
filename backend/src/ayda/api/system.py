from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ayda.core.db import Database, get_database
from ayda.core.problems import Problem

router = APIRouter(tags=["system"])


class Health(BaseModel):
    status: Literal["ok"]


@router.get("/health", operation_id="getHealth")
async def health(db: Annotated[Database, Depends(get_database)]) -> Health:
    try:
        await db.ping()
    except Exception as exc:
        raise Problem(503, "database-unavailable", detail="База данных недоступна") from exc
    return Health(status="ok")
