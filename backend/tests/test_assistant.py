import json

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select

from ayda.core.config import Settings
from ayda.core.db import Database
from ayda.modules import assistant
from ayda.modules.assistant import (
    Assistant,
    Candidate,
    FakeProvider,
    Profile,
    ProviderError,
    providers_from_settings,
)
from ayda.modules.assistant.models import LLMCall

CANDIDATES = [
    Candidate(i, f"Квест {i}", "rest" if i == 7 else "sport", 30, False) for i in range(1, 11)
]
PROFILE = Profile(["more_movement"], ["гулять"], ["дота"], "tired", None)


def ranked(ids: list[int], why: str = "Подходит тебе сегодня") -> str:
    return json.dumps({"items": [{"id": i, "why": why} for i in ids]}, ensure_ascii=False)


async def test_valid_answer_on_first_try() -> None:
    fake = FakeProvider(answers=[ranked([7, 1, 2, 3, 4])])

    result = await assistant.rank_pool(Assistant([fake]), PROFILE, CANDIDATES, [], True)

    assert result is not None
    assert [i.id for i in result.value.items] == [7, 1, 2, 3, 4]
    assert result.provider == "fake"


async def test_answer_in_think_block_and_fence_is_parsed() -> None:
    fake = FakeProvider(answers=["<think>хм</think>```json\n" + ranked([7, 1, 2, 3, 4]) + "\n```"])
    result = await assistant.rank_pool(Assistant([fake]), PROFILE, CANDIDATES, [], True)
    assert result is not None


@pytest.mark.parametrize(
    "bad",
    [
        "not json",
        ranked([7, 1, 2, 3, 999]),  # id outside the candidates
        ranked([7, 7, 1, 2, 3]),  # duplicates
        ranked([1, 2, 3, 4, 5]),  # no rest quest for a tired user
        ranked([7, 1]),  # too few
        ranked([7, 1, 2, 3, 4], why="Сходи в казино"),
    ],
)
async def test_invalid_answer_gets_one_retry(bad: str) -> None:
    fake = FakeProvider(answers=[bad, ranked([7, 1, 2, 3, 4])])

    result = await assistant.rank_pool(Assistant([fake]), PROFILE, CANDIDATES, [], True)

    assert result is not None
    assert len(fake.calls) == 2


async def test_two_invalid_answers_move_to_next_provider() -> None:
    first = FakeProvider(name="a", answers=["{}", "{}"])
    second = FakeProvider(name="b", answers=[ranked([7, 1, 2, 3, 4])])

    result = await assistant.rank_pool(Assistant([first, second]), PROFILE, CANDIDATES, [], True)

    assert result is not None and result.provider == "b"


async def test_provider_error_skips_retry() -> None:
    first = FakeProvider(name="a", answers=[ProviderError("http_429"), ranked([7, 1, 2, 3, 4])])
    second = FakeProvider(name="b", answers=[ranked([7, 2, 3, 4, 5])])

    result = await assistant.rank_pool(Assistant([first, second]), PROFILE, CANDIDATES, [], True)

    assert result is not None and result.provider == "b"
    assert len(first.calls) == 1


async def test_all_failing_returns_none_for_code_fallback() -> None:
    result = await assistant.rank_pool(
        Assistant([FakeProvider(answers=["x", "y"])]), PROFILE, CANDIDATES, [], True
    )
    assert result is None
    assert await assistant.rank_pool(Assistant([]), PROFILE, CANDIDATES, [], True) is None


async def test_prompt_has_no_personal_identifiers() -> None:
    fake = FakeProvider(answers=[ranked([7, 1, 2, 3, 4])])
    await assistant.rank_pool(Assistant([fake]), PROFILE, CANDIDATES, ["отчёт"], True)

    _, user = fake.calls[0]
    payload = json.loads(user)
    assert set(payload) == {"profile", "today_tasks", "candidates"}
    assert set(payload["profile"]) == {"goals", "want_more", "want_less", "mood", "weather"}


async def test_parse_checkin() -> None:
    answer = {
        "tasks": [{"title": "Доделать отчёт", "category": "project", "duration_min": 120}],
        "busy": ["09:00-18:00"],
        "free_evening": True,
    }
    fake = FakeProvider(answers=[json.dumps(answer, ensure_ascii=False)])

    result = await assistant.parse_checkin(Assistant([fake]), "работаю до 18, отчёт", "normal")

    assert result is not None
    assert result.value.tasks[0].title == "Доделать отчёт"
    assert result.value.free_evening is True


async def test_call_metadata_is_recorded_without_text(database: Database) -> None:
    fake = FakeProvider(answers=["oops", ranked([7, 1, 2, 3, 4])])
    client = Assistant([fake], sessionmaker=database.sessionmaker)

    await assistant.rank_pool(client, PROFILE, CANDIDATES, [], True)

    async with database.sessionmaker() as session:
        rows = list((await session.execute(select(LLMCall))).scalars())
    assert sorted((r.ok, r.error_kind or "") for r in rows) == [
        (False, "invalid_output"),
        (True, ""),
    ]
    assert {c.key for c in LLMCall.__table__.columns} == {
        "id",
        "purpose",
        "provider",
        "model",
        "latency_ms",
        "ok",
        "error_kind",
        "created_at",
    }


def test_providers_from_settings_skip_missing_keys() -> None:
    settings = Settings(
        llm_providers="groq-gptoss120b,zai-glm47flash=glm-4.5-flash,ollama",
        zai_api_key=SecretStr("k"),
        groq_api_key=None,
    )
    providers = providers_from_settings(settings)
    assert [(p.name, p.model) for p in providers] == [
        ("zai-glm47flash", "glm-4.5-flash"),
        ("ollama", "qwen3:8b"),
    ]
    with pytest.raises(ValueError, match="unknown"):
        providers_from_settings(Settings(llm_providers="nope"))


async def test_openai_compatible_provider_request_and_errors() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if len(seen) == 1:
            return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})
        return httpx.Response(429)

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = assistant.OpenAICompatibleProvider(
        "t", "https://llm.example/v1", "m", "secret", rpm=6000, http=http
    )

    assert await provider.complete("sys", "user", 5) == "{}"
    body = json.loads(seen[0].content)
    assert body["response_format"] == {"type": "json_object"}
    assert seen[0].headers["authorization"] == "Bearer secret"
    assert str(seen[0].url) == "https://llm.example/v1/chat/completions"
    with pytest.raises(ProviderError, match="http_429"):
        await provider.complete("sys", "user", 5)
