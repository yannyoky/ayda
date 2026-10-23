"""AI assistant: free LLM providers behind one adapter. The LLM only parses check-ins and
ranks candidates chosen by code; every answer is validated against a schema."""

from ayda.modules.assistant.client import Assistant, AssistantResult, InvalidAnswer
from ayda.modules.assistant.providers import (
    DEFAULT_CHAIN,
    PRESETS,
    FakeProvider,
    LLMProvider,
    OpenAICompatibleProvider,
    ProviderError,
    providers_from_settings,
)
from ayda.modules.assistant.tasks import (
    Candidate,
    MeetupIntent,
    ParsedCheckin,
    ParsedTask,
    Profile,
    RankedItem,
    RankedPool,
    parse_checkin,
    plan_meetup,
    rank_pool,
)

__all__ = [
    "DEFAULT_CHAIN",
    "PRESETS",
    "Assistant",
    "AssistantResult",
    "Candidate",
    "FakeProvider",
    "InvalidAnswer",
    "LLMProvider",
    "MeetupIntent",
    "OpenAICompatibleProvider",
    "ParsedCheckin",
    "ParsedTask",
    "Profile",
    "ProviderError",
    "RankedItem",
    "RankedPool",
    "parse_checkin",
    "plan_meetup",
    "providers_from_settings",
    "rank_pool",
]
