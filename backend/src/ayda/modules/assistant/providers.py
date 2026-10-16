"""OpenAI-compatible chat completion providers (free tiers only) and a fake for tests."""

import asyncio
import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol, cast

import httpx

from ayda.core.config import Settings


class ProviderError(Exception):
    """The call failed (HTTP, timeout, rate limit). `kind` is a short code for metadata."""

    def __init__(self, kind: str) -> None:
        super().__init__(kind)
        self.kind = kind


class LLMProvider(Protocol):
    name: str
    model: str

    async def complete(self, system: str, user: str, timeout_s: float) -> str: ...


@dataclass(frozen=True)
class Preset:
    base_url: str
    model: str
    key: Callable[[Settings], str | None]
    json_mode: bool = True
    rpm: int = 30
    timeout_s: float = 8.0
    # Extra request fields, e.g. a reasoning effort.
    extra: tuple[tuple[str, Any], ...] = ()


def _secret(name: str) -> Callable[[Settings], str | None]:
    def get(s: Settings) -> str | None:
        value = getattr(s, name)
        return value.get_secret_value() if value is not None else None

    return get


def _cf_url(s: Settings) -> str:
    account = s.cf_account_id.get_secret_value() if s.cf_account_id else ""
    return f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/v1"


GROQ = "https://api.groq.com/openai/v1"
LOW_EFFORT = (("reasoning_effort", "low"),)

# Fallback order and timeouts follow ADR 0005; LLM_PROVIDERS picks and orders them.
PRESETS: dict[str, Preset] = {
    "groq-gptoss20b": Preset(
        GROQ, "openai/gpt-oss-20b", _secret("groq_api_key"), timeout_s=4.0, extra=LOW_EFFORT
    ),
    "groq-gptoss120b": Preset(
        GROQ, "openai/gpt-oss-120b", _secret("groq_api_key"), timeout_s=4.0, extra=LOW_EFFORT
    ),
    "groq-llama70b": Preset(
        GROQ, "llama-3.3-70b-versatile", _secret("groq_api_key"), timeout_s=4.0
    ),
    "cloudflare-llama70b": Preset(
        "{cf}", "@cf/meta/llama-3.3-70b-instruct-fp8-fast", _secret("cf_api_token")
    ),
    "cloudflare-gptoss120b": Preset("{cf}", "@cf/openai/gpt-oss-120b", _secret("cf_api_token")),
    "ollama": Preset("{ollama}", "qwen3:8b", lambda _: None, json_mode=False, rpm=600),
}
DEFAULT_CHAIN = "groq-gptoss20b,groq-gptoss120b,cloudflare-llama70b"


class RateLimiter:
    """Spaces calls to one provider so a free tier's requests-per-minute is not exceeded."""

    def __init__(self, rpm: int) -> None:
        self._interval = 60.0 / rpm
        self._next = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self, max_wait_s: float) -> None:
        async with self._lock:
            now = time.monotonic()
            wait = self._next - now
            if wait > max_wait_s:
                raise ProviderError("rate_limited")
            if wait > 0:
                await asyncio.sleep(wait)
            self._next = max(now, self._next) + self._interval


class OpenAICompatibleProvider:
    def __init__(
        self,
        name: str,
        base_url: str,
        model: str,
        api_key: str | None,
        *,
        json_mode: bool = True,
        rpm: int = 30,
        timeout_s: float = 8.0,
        extra: tuple[tuple[str, Any], ...] = (),
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self.name = name
        self.model = model
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._api_key = api_key
        self._json_mode = json_mode
        self._max_timeout_s = timeout_s
        self._extra = dict(extra)
        self._limiter = RateLimiter(rpm)
        self._http = http or httpx.AsyncClient()

    async def complete(self, system: str, user: str, timeout_s: float) -> str:
        timeout_s = min(timeout_s, self._max_timeout_s)
        await self._limiter.acquire(max_wait_s=timeout_s / 2)
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        body: dict[str, Any] = {
            "model": self.model,
            "temperature": 0.3,
            "max_tokens": 1200,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        body.update(self._extra)
        if self._json_mode:
            body["response_format"] = {"type": "json_object"}
        try:
            response = await self._http.post(
                self._url, json=body, headers=headers, timeout=timeout_s
            )
        except httpx.TimeoutException:
            raise ProviderError("timeout") from None
        except httpx.HTTPError:
            raise ProviderError("network") from None
        if response.status_code == 429:
            raise ProviderError("http_429")
        if response.status_code != 200:
            raise ProviderError(f"http_{response.status_code}")
        try:
            data = cast(dict[str, Any], response.json())
            content = data["choices"][0]["message"].get("content") or ""
        except (ValueError, KeyError, IndexError, TypeError):
            raise ProviderError("bad_response") from None
        return str(content)


def providers_from_settings(
    settings: Settings, http: httpx.AsyncClient | None = None
) -> list[LLMProvider]:
    """Providers in fallback order; presets without a configured key are skipped."""
    out: list[LLMProvider] = []
    for entry in (e.strip() for e in settings.llm_providers.split(",")):
        if not entry:
            continue
        name, _, model_override = entry.partition("=")
        preset = PRESETS.get(name)
        if preset is None:
            raise ValueError(f"unknown LLM provider preset: {name}")
        key = preset.key(settings)
        if name != "ollama" and not key:
            continue
        base_url = preset.base_url.format(cf=_cf_url(settings), ollama=settings.ollama_url)
        out.append(
            OpenAICompatibleProvider(
                name,
                base_url,
                model_override or preset.model,
                key,
                json_mode=preset.json_mode,
                rpm=preset.rpm,
                timeout_s=preset.timeout_s,
                extra=preset.extra,
                http=http,
            )
        )
    return out


@dataclass
class FakeProvider:
    """Answers from a script, for tests. A str answer is returned, an exception is raised."""

    name: str = "fake"
    model: str = "fake-1"
    answers: list[str | Exception] = field(default_factory=lambda: [])
    calls: list[tuple[str, str]] = field(default_factory=lambda: [])

    async def complete(self, system: str, user: str, timeout_s: float) -> str:
        self.calls.append((system, user))
        if not self.answers:
            raise ProviderError("no_answer")
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


_THINK = re.compile(r"<think>.*?</think>", re.S)
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.S)


def extract_json(text: str) -> Any:
    """The JSON object in a model answer, tolerating <think> blocks and code fences."""
    text = _THINK.sub("", text).strip()
    text = _FENCE.sub("", text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in answer")
    return json.loads(text[start : end + 1])


__all__ = [
    "PRESETS",
    "FakeProvider",
    "LLMProvider",
    "OpenAICompatibleProvider",
    "ProviderError",
    "extract_json",
    "providers_from_settings",
]
