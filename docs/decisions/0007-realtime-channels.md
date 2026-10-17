# 0007. Realtime through one personal Centrifugo channel per user

English · [Русский](../ru/decisions/0007-realtime-channels.md)

## Context
M2 adds direct messages between friends (US-17) and co-op quests with a shared chat (US-18). ADR 0002 chose Centrifugo for realtime. A message has to reach an open chat within a second, the chat list needs live unread counts, history must survive a dropped connection, and a user may only receive what they belong to. A former friend must stop receiving a DM chat's messages at once, and a user can be in many chats.

Two channel layouts were considered:
- **A channel per conversation** (`chat:<id>`) with subscription tokens. The client subscribes to every conversation to keep the chat list live, so a user with 30 chats holds 30 subscriptions and 30 tokens. Access is decided when a token is issued, so removing a friend leaves the former friend subscribed until the token expires.
- **One personal channel per user** (`personal:#<user id>`). The backend publishes each event to the personal channels of the conversation's current members (Centrifugo `broadcast`). Centrifugo's user-limited channels (`#` boundary) let only the connection whose token carries that user id subscribe, so no subscription tokens are needed.

## Decision
- One personal channel per user, `personal:#<user id>`, in a `personal` namespace with `allow_user_limited_channels`, history of 100 publications for 1 hour, and `force_recovery`.
- The API issues a short-lived connection token (HS256 JWT, `sub` = user id, 1 hour) at `POST /realtime/token`; the client refreshes it through the same call. The Centrifugo HTTP API key and token secret come from environment variables.
- Write path: the API saves the message in PostgreSQL and commits, then broadcasts to the members' personal channels. If Centrifugo is unreachable, a `realtime.publish` job retries the broadcast, so a message is never lost and at worst arrives late.
- Events are small JSON objects with a `type` (`message.created`, `message.deleted`, `conversation.read`, later `coop.updated`), described in `contracts/openapi.yaml` as `RealtimeEvent`. The REST API stays the source of truth: after a reconnect that Centrifugo cannot recover (more than 1 hour or 100 events), the client reloads conversations and messages over REST.
- Access is checked only on the write path: the backend decides who receives each event. Removing a friendship closes the DM for new messages at once, because nothing more is published to the former friend.

## Consequences
One subscription per client keeps the chat list, unread counts and co-op updates live. Recovery after short drops is Centrifugo's job; long gaps fall back to REST pages. Message text passes through Centrifugo's in-memory history on the same Russian VPS for at most an hour and is not written to its logs. Scaling past one Centrifugo node would need its Redis engine, which is far beyond MVP load. A subscription token per channel can still be added later for channels shared by many users (for example a public event chat).
