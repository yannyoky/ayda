# 0013. A day chat with the assistant

English · [Русский](../ru/decisions/0013-assistant-chat.md)

## Context
Until M5 the assistant only turned the morning check-in into a pool and phrased a few cards. The owner (2026-10-23, epic #160) wants a real conversation: the check-in should not close after one message, and every quest should be open to discussion so the assistant can vary it (places for a walk, a restaurant for dinner, a menu from what is at home).

What stays: free LLMs only (ADR 0005; prod runs the Cloudflare chain), the providers are in the US, so text is minimal, never logged and covered by the consent (152-FZ). Places, recipes and quests must not be invented: a made-up address or a recipe with a missed allergen is worse than no answer.

## Decision
- **One chat a day.** Each user has an assistant chat for the local day; it ends with the day at 04:00. The check-in is its first message: `PUT /days/today/checkin` keeps building the pool and also writes the assistant's first reply (what was understood, a button to the picker). After that the user keeps writing in the same chat.
- **Topics.** Besides the day topic, every quest of the day has its own topic, opened by "Обсудить" on a quest. The quest's title, category, duration and place are part of that topic's prompt.
- **Free text for advice, facts from code.** The LLM answers in Russian prose (advice, ideas how to vary a quest, follow-up questions) and may ask code for at most one action. The answer is JSON validated against a schema: `reply` (up to 600 characters) and `action`, one of:
  - `find_places` with `kind` `walk`, `food` or `drinks`: code takes places near the user's city centre from OpenStreetMap, parks, gardens, embankments, viewpoints and squares for a walk, the venues of ADR 0011 for food and drinks;
  - `suggest_dishes` with up to 10 ingredients the user named and an optional meal: code matches them to the catalog ingredients (ADR 0012), ranks recipes by the share already at home, and the existing recipe picker takes it from there;
  - `suggest_quest` with title, category and duration: code clamps the values and adds an offered quest the user can take.

  Code checks the reply: no links, phone numbers, addresses or prices (those come only on cards), the banned topics of the pool texts, the length. A broken answer gets the usual retry and the next provider.
- **What goes to the LLM.** The last 10 messages of the topic (each cut to 300 characters), mood, goals, weather flags and the quest context. No name, Telegram id, city or coordinates; places are searched by code.
- **Without an LLM.** Code recognises the obvious requests by keywords (a walk, eating out, a bar, cooking or "what to cook from") and runs the same action with a template reply; anything else gets "Сейчас не получается ответить, попробуй позже". Cards work either way.
- **Storage and limits.** Messages live in an `assistant` table (user, day, topic quest or none, role, text, cards) and are deleted by an hourly job once the local day is over, and with the account. The check-in keeps its 30-day rule. Message text is never logged; the `assistant_message` event carries the topic kind, the action, the provider and counts. Up to 40 messages from the user a day, 1000 characters each; the request waits for the answer (up to 12 s) while the client shows that the assistant is typing.

## Consequences
The "code selects, the LLM ranks and phrases" rule of the PRD widens to "the LLM talks and picks, every fact comes from code". Each message is an LLM call, so the free Cloudflare quota becomes a real limit; the daily cap and the keyword fallback keep the app usable when it runs out. The consent text has to name the assistant chat next to the check-in. The chat is short-lived on purpose: a long memory of conversations would need its own retention decision. Walk places need a new OSM query next to the venues one (#163).
