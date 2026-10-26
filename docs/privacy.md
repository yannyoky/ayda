# Ayda privacy policy

English · [Русский](ru/privacy.md)

Version of 26 October 2026, for consent version `2026-10-26`. Users see the Russian text at `/privacy.html` (`miniapp/public/privacy.html`). A change here also changes that page and the Russian version.

Ayda is in a closed test for now. The operator's contact for requests will be added to this document before the public launch.

## What data we process and why

| Data | Why | Kept for |
| --- | --- | --- |
| Name and avatar from Telegram, or name and email for email sign-in | sign-in, so friends recognize you | while the account exists |
| City and time zone (no exact location) | weather, events and quests for your city | while the account exists |
| Morning check-in text | quests that fit your day | 30 days |
| Messages to the assistant | assistant replies | until the end of the day |
| Own habits and interests | quest selection | until you delete them |
| Proof photos, videos and circles (EXIF and geotags removed) | friends' feed | photos until the post is deleted, videos 30 days |
| Chat messages, voice messages and circles | messaging with friends | until deleted; a co-op chat 30 days after the quest, circles 30 days |
| In-app events (taken, completed, liked) | statistics and better quest selection | anonymized on account deletion |

## Where the data is stored

The database, photos, videos and backups are stored on servers in Russia. Backups older than 14 days are deleted. Logs carry no texts, tokens, emails or coordinates.

## AI services

To pick quests and answer in the chat, Ayda sends third-party AI services:

- the check-in text;
- messages to the assistant;
- the last messages of a chat when you tap «Айда, организуй», including the other person's messages;
- an anonymized day profile: interests, habits you want more or less of, mood from the check-in, weather.

Name, email, Telegram id and city are not sent. AI services may be located outside Russia. When a service is unavailable, the Ayda algorithm answers instead. Do not put sensitive details into the check-in or the assistant chat: health, documents, other people's contacts.

Services in use now:

| Service | Country | What it gets | Why |
| --- | --- | --- | --- |
| Cloudflare Workers AI (Cloudflare, Inc.) | USA | the texts and profile listed above | parsing the check-in, picking and phrasing quests, assistant replies, meetup plans |

A new service is added to this table before any data is sent to it.

## Other services

| Service | Country | What it gets | Why |
| --- | --- | --- | --- |
| Telegram | outside Russia | bot messages: reminders and day summaries | Telegram sign-in and reminders, if you sign in with Telegram |
| Firebase Cloud Messaging (Google LLC) | USA | device token and a generic notification text without names or message texts | push notifications in the Android app, when enabled |

## Your rights

- You can delete the account in the profile. Sign-out on every device is immediate, data is erased within 30 days, events are anonymized.
- The accepted consent text and this policy are in the profile, section «Данные и приватность».
- Withdrawing consent means deleting the account: the service does not work without consent.
- When the data or the purposes change, we show a new consent, and the app does not open further without it.
