# Ayda: roadmap

The MVP ships in three milestones. Each milestone is an epic issue with sub-issues; issues carry an `M1`/`M2`/`M3` label and a component label (`backend`, `miniapp`, `contracts`, `infra`, `docs`). Requirements: `prd.md`.

## M1: core loop ([#8](https://github.com/yannyoky/ayda/issues/8))

Morning check-in, daily quest pool, proofs, friends feed, points, streaks, ladder, bot reminders. Goes to the first group of friends when done.

Foundation:
- #11 MVP PRD and roadmap in docs
- #12 MVP database schema and OpenAPI contract
- #13 Backend foundation: settings, database, migrations, local Docker Compose
- #14 Mini App scaffold with themes and generated API client
- #15 Append-only events table and event logging API
- #18 Telegram bot skeleton
- #19 Job queue and scheduled reminders (US-04, US-11)

Morning:
- #16 Sign in with Telegram initData (US-01)
- #17 Onboarding and profile (US-02, US-03)
- #20 Quest catalog: model and first 150-200 quests
- #21 Weather via Open-Meteo
- #22 Pluggable LLM provider with schema validation and fallback
- #23 Pick a free LLM provider by an eval on fake profiles
- #24 Morning check-in (US-05)
- #25 Daily quest pool (US-06)
- #26 Take, replace and add own quests (US-07, US-08)

Evening:
- #27 Photo upload to S3 with EXIF stripping (US-10)
- #28 Complete a quest with a visibility level (US-09)
- #29 Points ledger and streaks (US-15)
- #30 Friend invites and friendships (US-12)
- #31 Friends feed with likes and comments (US-13, US-14)
- #32 Weekly ladder and Sunday summary (US-16)

Release:
- #33 Privacy under 152-FZ: consent, deletion, retention
- #34 Production setup: VPS, Caddy, deploy with manual approval, backups

## M2: direct messages and co-op ([#9](https://github.com/yannyoky/ayda/issues/9))

- #35 Centrifugo integration
- #36 Direct messages between friends (US-17)
- #37 Co-op quests at a distance (US-18)

## M3: local events ([#10](https://github.com/yannyoky/ayda/issues/10))

- #38 Research events sources across Russian cities and regions
- #39 Events ingestion and event quests (US-19)

## M4: native Android app, iOS later ([#89](https://github.com/yannyoky/ayda/issues/89))

Same core loop as the Mini App in a native app that works in Russia without Telegram (ADR 0009). Android first; iOS needs a Mac.

- #90 Native app plan: ADR 0009, PRD and roadmap
- #91 Sign-in without Telegram: email code, linked identities, refresh tokens
- #92 Mobile scaffold: KMP project, generated API client, theme, CI
- #93 Android: sign-in, consents and onboarding
- #94 Android: Today screen with check-in, quest pool, events and photo proofs
- #95 Android: feed, friends, invites and ladder
- #96 Android: direct messages and co-op quests over Centrifugo
- #97 Push notifications for the app (FCM)
- #98 Invite links that open the app (App Links)
- #99 Android release: signing, APK for friends, RuStore
- #100 iOS app in SwiftUI on the shared module (needs a Mac)

## After M4

Nudges from Steam and screen time, strict mode and self-chosen penalties, trust rating and call-outs, recipes, video proofs, predictive recommendations on the logged events.
