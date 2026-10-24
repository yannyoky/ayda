# Ayda: MVP product requirements

English · [Русский](ru/prd.md)

Status: approved by the owner on 2026-10-16. The working copy in Russian is the [PRD doc](https://claude.ai/code/artifact/a7705f98-da00-4c76-a6d8-f768868c2d2e); this file and its Russian mirror `ru/prd.md` are the source of truth for the repository. Milestones and issues: `roadmap.md`.

## Goal and metrics

The MVP tests one loop: in the morning a person tells Ayda about their day and gets quests, in the evening they show friends what they did. Anything that does not serve this loop waits for later versions.

The MVP runs as a Telegram Mini App for a closed group of 5-10 friends for 4 weeks. Success thresholds:

| Metric | Threshold | How it is computed |
| --- | --- | --- |
| Morning check-in | ≥ 4 days out of 7 per active user | share of days with `checkin_submitted` |
| Completed quests | ≥ 1.5 per active day | `quest_completed` / days with a check-in |
| Evening show | ≥ 50% of completed quests have a proof in the feed | `proof_posted` / `quest_completed` |
| Friends react | ≥ 60% of proofs get a like or comment within 24 h | `reaction_added` per proof |
| Retention | ≥ 60% of the group active in week 4 | check-in on at least 3 days that week |
| Pool acceptance | ≤ 2 replacements per day on average | `quest_rejected` / days with a check-in |

If retention and evening show miss their thresholds after 4 weeks, we change the loop rather than add features.

## Users and a day with Ayda

First users are the owner and friends: 20-35 years old, living in different Russian cities, talking in Telegram. They want to spend less time on games and feeds, do more of what they themselves consider useful, and have friends see it.

1. **08:30.** The bot says "Good morning, what's today?" and opens the Mini App.
2. **Check-in.** The user writes in free text: "work until 18, need to finish a report, free in the evening, tired".
3. **Pool.** The assistant turns their tasks into quests and fills free time with quests that fit the weather and the user's interests: "a 40-minute walk along the embankment", "no screens after 22:00".
4. **Pick.** The user takes as many quests as they like (points for the first 5 completed, since M6) and replaces the ones that don't fit.
5. **Day.** They mark quests done and attach a photo to the ones they share.
6. **20:30.** The bot reminds about open quests and suggests showing the day to friends.
7. **Evening.** Friends like and comment on proofs, the ladder changes, the streak goes on.

## Scope

| Feature | Milestone | Why in the MVP |
| --- | --- | --- |
| Telegram sign-in (initData), profile, Graphite/Plum theme | M1 | no product without it |
| Onboarding: region, interests, own good and bad habits, reminder times | M1 | quests are built from it |
| Morning check-in in free text | M1 | main difference from competitors |
| Daily quest pool, take quests (up to 3 in M1, any number since M6), replace with an alternative | M1 | core of the loop |
| Own quest added by hand | M1 | when the assistant misses |
| Completion with a proof (text and optional photos), visibility personal / friends | M1 | evening half of the loop |
| Friends via a Telegram invite link | M1 | nobody to show without friends |
| Friends feed, likes and comments | M1 | "show friends" |
| Points, streak, weekly friends ladder | M1 | a reason to come back tomorrow |
| Morning and evening bot reminders | M1 | starts the loop every day |
| Weather for the user's city in quest selection | M1 | cheap (free API), makes outdoor quests better |
| Direct messages between friends (Centrifugo) | M2 | decided 2026-10-16, not needed for the M1 loop |
| Co-op quests at a distance with a chat | M2 | for friends in different cities |
| Local events in the city and region as a quest source | M3 | needs a data source for the whole country |

**Not in the MVP:** nudges from Steam and screen time (need native apps), strict mode, penalties and trust rating, the "call out" button, public profiles for strangers, recipes, video proofs, native apps, predictive recommendations (their events are logged from day one).

## User stories and acceptance criteria

A story is done when all its criteria hold, it has tests, and its events are written to `events`.

### Sign-in and onboarding (M1)

- **US-01. Sign in with Telegram.** As a new user, I open the Mini App from the bot and I'm signed in without a password.
    - The backend checks the initData signature and rejects data older than 24 h.
    - The first sign-in creates a profile with the Telegram name and avatar; later sign-ins find it.
    - An invalid signature returns 401, and initData itself never reaches logs.
- **US-02. Onboarding.** As a new user, I tell the app what I want in 2 minutes so quests are about me.
    - Steps: region and city (geolocation or pick from a list), up to 8 interests from a catalog and up to 5 of their own words (ADR 0018), own "want more" and "want less" habits, morning and evening reminder times.
    - Every step except the city can be skipped; everything is editable later in Profile.
    - Exact coordinates are not stored: they are rounded to the city (settlement center).
    - The user words habits themselves; the app does not judge them.
- **US-03. Theme.** As a user, I choose Graphite or Plum.
    - The theme applies immediately and is saved in the profile; Graphite is the default.

### Morning: check-in and pool (M1)

- **US-04. Morning reminder.** As a user, I get a bot message at my chosen time with an "Open" button.
    - Time is in the user's time zone, at most 5 minutes late.
    - No reminder if the check-in is already done. Reminders can be turned off.
- **US-05. Check-in.** As a user, I write about my day in free text and pick a mood (energetic / normal / tired).
    - Text up to 1000 characters, may be empty: then the pool is built from the profile.
    - One check-in per day; a new one replaces the old and rebuilds quests not taken yet.
    - Only the author sees the check-in text, and it is never logged.
- **US-06. Daily pool.** As a user, after the check-in I see 5-7 quests for today.
    - The pool holds tasks from the check-in turned into quests and catalog quests for free time.
    - Each quest has a title, category, duration, points and one "why you" line.
    - In rain there are no long outdoor quests unless the user said the weather will not stop them; frost below -15 °C, a thunderstorm and feeling unwell rule them out anyway (a storm rules out every outdoor quest).
    - With the "tired" mood the pool has at least one rest quest.
    - The pool appears in 10 seconds or less; without an LLM a code-only pool is shown (see the assistant section).
- **US-07. Take and replace.** As a user, I take the quests I want and replace the ones that don't fit (up to 3 in M1; any number since M6, #165).
    - "Not today" swaps a quest for an alternative from another category or duration; an optional reason (no time / don't want / can't).
    - Up to 5 replacements a day; a replaced quest does not come back the same day.
    - Taken quests show on the Today screen; rejection and its reason go to `events`.
- **US-08. Own quest.** As a user, I add my own quest with a title and category.
    - It counts as a taken quest and gives base points by duration.

### Day and evening: completion and proofs (M1)

- **US-09. Complete a quest.** As a user, I mark a quest done and choose who sees it.
    - Visibility: friends ("in the feed", with a caption and optional photos) or personal ("only me").
    - A feed proof can be text only; photos are optional. The former "routine" level (friends see the fact without details) was retired on 2026-10-23; older routine entries stay in the feed as they were.
    - A daily quest can be closed until 04:00 local time the next day, then it expires with no penalty.
- **US-10. Photo proof.** As a user, I can attach up to 3 photos from my phone.
    - Upload goes straight to S3 via a presigned URL, up to 10 MB per photo, JPEG/PNG/HEIC/WebP.
    - EXIF, including geotags, is removed before saving.
    - The author can delete a proof; the photo is deleted from storage and the points stay.
- **US-11. Evening reminder.** As a user, in the evening I get the day's result and a reminder about open quests.
    - Not sent if every taken quest is closed or there was no check-in.
    - Neutral tone, no shaming for what was not done.

### Friends, feed, ladder (M1)

- **US-12. Invite a friend.** As a user, I share a link in Telegram, and whoever opens it becomes my friend.
    - Link `t.me/<bot>?startapp=<code>`, the code lives 7 days and is reusable.
    - Friendship is mutual and can be removed; a former friend immediately stops seeing my posts.
- **US-13. Feed.** As a user, I see my friends' proofs, newest first.
    - Only friends and me in the feed; personal quests are never shown to anyone.
    - Pages of 20, the first page in 1 second or less.
- **US-14. Likes and comments.** As a friend, I like and comment on a proof.
    - One like per person, comments up to 500 characters; the comment author and the post author can delete it.
    - The post author gets a bot digest at most once an hour.
- **US-15. Points and streak.** As a user, I see my points for the day and week and my streak.
    - Rules in the scoring section; only the backend computes points.
- **US-16. Ladder.** As a user, I see the weekly ranking of me and my friends.
    - The week starts Monday 00:00 in each user's local time; on Sunday evening the bot sends the week's result.
    - Each row shows rank, weekly points and streak; points for personal quests count in the total without revealing details.

### Messaging and co-op (M2)

- **US-17. Direct messages.** As a user, I message a friend in the app.
    - Friends only; a message reaches an open chat in 1 second or less via Centrifugo.
    - History is saved and loads after a dropped connection; the bot only notifies about a new message, without its text.
- **US-18. Co-op quest.** As a user, I invite 1-3 friends to a shared quest, and each of us does it on their own.
    - The co-op quest has a shared chat; it counts for a participant when they mark it done themselves.
    - If all participants close it on the same day, each gets +50%.

### Events (M3)

- **US-19. Events nearby.** As a user, I see free and paid events in my city and region in the pool.
    - An event quest shows place, time, price and a link to the source.
    - Past events and those starting in less than 1 hour are not suggested; events refresh once a day in a nightly job.

## Quests, points, streaks and ladder

Points for a quest = base by duration × visibility multiplier × streak bonus, rounded to an integer. Rest is worth as much as a workout of the same length: the app does not reward overwork.

| Parameter | Value |
| --- | --- |
| Base: up to 15 min / 16-30 min / 31-60 min / over 60 min | 10 / 20 / 35 / 50 points |
| Visibility: friends (with or without a photo) / personal | ×1.0 / ×0.5 |
| Streak bonus | +10% for each full 7 days, at most +30% |
| Co-op, if everyone closes it the same day (M2) | +50% each |
| Daily limit | none for taking quests since M6 (owner, 2026-10-23, #165; a guard of 30 against abuse); points only for the first 5 completed quests of a day, the rest count for the streak only |
| Streak | a day counts if at least 1 quest of any visibility is completed |
| Streak freeze | 1 missed day a week is frozen automatically |
| Ladder | sum of weekly points among friends, reset on Monday; ties go to the longer streak |
| Penalties | none in the MVP: an unfinished quest simply expires |

Example: a 40-minute walk with a photo on day 10 of a streak gives 35 × 1.0 × 1.1 = 39 points. The same walk as a personal quest gives 19. Coefficients live in config so they can be tuned without a release.

## AI assistant: who decides what

Code selects candidates; the LLM only ranks them and writes the text. So the pool works without an LLM, and the model cannot invent a quest that is not in the catalog. From M6 the LLM also talks in the assistant chat, but every quest, place or recipe it shows still comes from code (ADR 0013).

1. **Parse the check-in.** The LLM extracts tasks, busy hours and mood into JSON by schema. Without an LLM, tasks are taken line by line and the time after 18:00 counts as free.
2. **Candidates.** Code takes 20-30 catalog quests: they match interests and habits, fit free slots, are allowed by the weather, were not shown yesterday and were not replaced today.
3. **Ranking and text.** The LLM gets candidates by id and a profile without name or exact location, and returns 5-7 ids in order with a "why you" line.
4. **Validation.** The answer is checked against a JSON schema: ids only from the candidates, text length, no banned topics. On failure: one retry, then the next provider, then ranking in code by simple weights.
5. **Logging.** Pool shown, take, replace and completion go to `events` with candidate ids and the provider, but without the check-in text and without the model's full answer.

Catalog at launch: 150-200 quests in 8 categories (sport, walk, city, rest, project, social, home, learning) with duration, weather requirements and tags, written by hand with LLM help and proofread. The LLM provider is chosen by an eval on fake profiles; Ollama is used for development.

## Non-functional requirements

| Area | Requirement |
| --- | --- |
| 152-FZ | DB, photos and backups on servers in Russia; consent to data processing at first sign-in; account deletion erases profile, photos and check-ins within 30 days and anonymizes `events` |
| Data minimization | location only to the city; EXIF removed from photos; check-in text kept 30 days |
| External LLMs | only the check-in text and an anonymized profile are sent, without name, Telegram id or city; the consent says plainly that an external service processes the text |
| Logs | no raw personal data: no initData, free text, coordinates or photo links |
| Events | append-only `events` table from the first release: check-in, pool shown, take, replace with reason, completion, proof, reaction, reminder sent and opened |
| Speed | API p95 ≤ 300 ms without LLM; pool ≤ 10 s; Mini App opens in ≤ 2 s on 4G |
| Reliability | one VPS, daily DB backup with a restore check monthly; an LLM outage does not break the loop |
| Security | secrets only from environment variables; rate limits on check-in, replacements and uploads; other users' proofs only for friends |
| Cost | only free LLMs and weather API; we pay for the VPS, S3 and domain |
| Language | interface and quests in Russian; strings live in translation files from the start |

## Decisions on open questions (2026-10-16)

The owner accepted every default:

- Direct messages and co-op go to M2; friends get M1 first.
- Events go to M3; sources are researched separately (no single free API covers the whole country).
- Up to 3 taken quests and up to 5 replacements a day.
- Personal quests give ×0.5 points and count in the ladder.
- Weather from Open-Meteo (free, no key).
- Check-in text is kept 30 days, then deleted; only events stay for recommendations.
- Bot handle (@ayda_quest_bot) is not checked yet; the owner creates the token in @BotFather before M1 starts.

## After the MVP: native app (M4)

Decided 2026-10-17 (ADR 0009, epic #89). Telegram does not work in Russia without a VPN, so the native app is the way in for friends without Telegram.

- **Scope:** the same loop as the Mini App: sign-in, consents and onboarding, morning check-in, daily pool with events, photo proofs, feed, friends and invites, ladder, DMs and co-op chat. Native-only features (Steam, screen time) are not in M4.
- **Sign-in:** email with a one-time code; Telegram as an extra option, and both can be linked to one account. No VK ID, Yandex ID or SMS for now (owner's choice 2026-10-17). The app must work with no Telegram at all.
- **Notifications:** push (FCM); the bot stays for those who have Telegram.
- **Order:** Android first (APK for friends, then RuStore, Google Play later); iOS when a Mac and an Apple Developer account are available.

## After M4: shared plans (M5)

Owner's scenarios, 2026-10-17 (epic #119). Both rest on one mechanism: a co-op quest split into parts, each part with its own assignee and details (place, time, checklist).

- **Meetup from chat.** Friends discuss a bar, a restaurant or a Dota session in a DM or co-op chat. On an explicit "Айда, организуй" tap the assistant suggests the type, a time and 3-5 places (or an online session), following the latest suggestion in the chat and putting a place named there first; the time can be edited in the card; once they pick, a co-op quest with place and time is created.
- **Cooking with a shopping hand-off.** In the morning check-in a user says she wants to cook lunch. The assistant offers 2-3 recipes and asks what is at home. Missing ingredients become a "buy groceries" part with a checklist that she can hand to a friend or partner; the "cook" part opens after it. Each gets points for their own part and a bonus if both parts close the same day.
- **Privacy:** the assistant reads a chat only after the tap and only the last few messages; message text is not logged. Our LLM providers are in the US, so background chat reading is out (152-FZ).
- **Data:** venues and recipes come from free sources with clear terms, no scraping (#121, #122). Default for venues: OpenStreetMap plus a link to 2GIS or Yandex Maps for reviews. Recipes come from a curated catalog; the LLM only picks and adapts them, because invented ingredients can miss allergens.

## After M5: assistant chat (M6)

Owner's request, 2026-10-23 (epic #160, ADR 0013).

- **The check-in opens a chat.** Sending the check-in no longer closes it: the user sees their message, the assistant's answer and a button to the picker, and can keep writing all day to talk or ask for advice. A first check-in with nothing taken yet goes straight to the picker (#158).
- **Discuss a quest.** Every quest in the picker and on Today has "Обсудить", which opens the chat on that quest. The assistant suggests how to vary it and, when asked, shows cards: places to walk for a walk, cafes, restaurants or bars for eating out, dishes from what is at home for cooking (then the cooking plan of M5), or a new quest to take.
- **Who decides what.** The LLM talks, gives advice and picks; places, recipes and quests on cards come only from code and our sources (OpenStreetMap, the recipe catalog, the quest catalog). Without an LLM, code answers the obvious requests by keywords.
- **Privacy:** the chat lives for the day and is deleted after it; message text is not logged; the LLM gets the last messages of the topic without name or city. The consent names the assistant chat.
- **Limits:** up to 40 messages a day; no limit on taken quests (owner, 2026-10-23): take as many as you like, points and the ladder count the first 5 completed a day (#165).
