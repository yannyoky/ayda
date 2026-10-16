import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ayda.modules.assistant.models import LLMCall
from ayda.modules.assistant.providers import LLMProvider, ProviderError, extract_json

log = logging.getLogger(__name__)

Purpose = Literal["parse_checkin", "rank_pool"]


class InvalidAnswer(ValueError):
    """The answer parsed but broke a rule the schema can't express (e.g. an unknown id)."""


@dataclass(frozen=True)
class AssistantResult[T: BaseModel]:
    value: T
    provider: str
    model: str


class Assistant:
    """Calls providers in order. An invalid answer gets one retry, then the next provider;
    None means every provider failed and the caller uses its code-only fallback."""

    def __init__(
        self,
        providers: Sequence[LLMProvider],
        sessionmaker: async_sessionmaker[AsyncSession] | None = None,
        timeout_s: float = 8.0,
    ) -> None:
        self.providers = list(providers)
        self._sessionmaker = sessionmaker
        self._timeout_s = timeout_s

    async def _record(self, calls: list[LLMCall]) -> None:
        if self._sessionmaker is None or not calls:
            return
        try:
            async with self._sessionmaker() as session:
                session.add_all(calls)
                await session.commit()
        except Exception:  # metadata must never break the user's request
            log.warning("could not record llm call metadata", exc_info=True)

    async def run[T: BaseModel](
        self,
        purpose: Purpose,
        system: str,
        user: str,
        schema: type[T],
        check: Callable[[T], None] | None = None,
        deadline_s: float | None = None,
    ) -> AssistantResult[T] | None:
        started = time.monotonic()
        calls: list[LLMCall] = []
        try:
            for provider in self.providers:
                for _attempt in range(2):
                    left = (deadline_s or 1e9) - (time.monotonic() - started)
                    timeout = min(self._timeout_s, left)
                    if timeout < 0.5:
                        return None
                    t0 = time.monotonic()
                    error_kind: str | None = None
                    value: T | None = None
                    try:
                        answer = await provider.complete(system, user, timeout)
                        value = schema.model_validate(extract_json(answer))
                        if check is not None:
                            check(value)
                    except ProviderError as exc:
                        error_kind = exc.kind
                    except (ValueError, ValidationError):
                        error_kind = "invalid_output"
                        value = None
                    calls.append(
                        LLMCall(
                            purpose=purpose,
                            provider=provider.name,
                            model=provider.model,
                            latency_ms=int((time.monotonic() - t0) * 1000),
                            ok=error_kind is None,
                            error_kind=error_kind,
                        )
                    )
                    # Logs carry provider and latency only, never prompt or answer text.
                    log.info(
                        "llm call purpose=%s provider=%s ok=%s error=%s",
                        purpose,
                        provider.name,
                        error_kind is None,
                        error_kind,
                    )
                    if value is not None and error_kind is None:
                        return AssistantResult(value, provider.name, provider.model)
                    if error_kind != "invalid_output":
                        break  # provider is down or limited: go to the next one
            return None
        finally:
            await self._record(calls)
