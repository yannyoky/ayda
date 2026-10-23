"""AI assistant: free LLM providers behind one adapter. The LLM parses check-ins, ranks
candidates chosen by code and talks in the day chat, where every fact comes from code
(ADR 0013); every answer is validated against a schema."""

from ayda.modules.assistant import chat
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
    ChatAction,
    ChatAnswer,
    ChatContext,
    ChatQuest,
    MeetupIntent,
    ParsedCheckin,
    ParsedTask,
    Profile,
    RankedItem,
    RankedPool,
    RecipePick,
    RecipePicks,
    chat_reply,
    parse_checkin,
    pick_recipes,
    plan_meetup,
    rank_pool,
)

__all__ = [
    "DEFAULT_CHAIN",
    "PRESETS",
    "Assistant",
    "AssistantResult",
    "Candidate",
    "ChatAction",
    "ChatAnswer",
    "ChatContext",
    "ChatQuest",
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
    "RecipePick",
    "RecipePicks",
    "chat",
    "chat_reply",
    "parse_checkin",
    "pick_recipes",
    "plan_meetup",
    "providers_from_settings",
    "rank_pool",
]
