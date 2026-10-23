# 0009. Native apps: Kotlin Multiplatform, Android first, sign-in by email

English · [Русский](../ru/decisions/0009-native-apps.md)

## Context
After the MVP (M1-M3 as a Telegram Mini App) Ayda needs native apps (ADR 0002: Kotlin Multiplatform with Compose on Android and SwiftUI on iOS). They must reach parity with the Mini App's core loop and later carry native-only features (screen time, Steam nudges).

The Mini App leans on Telegram in three places: sign-in (initData), notifications (the bot) and invites (`t.me/<bot>?start=<code>`). Telegram does not work in Russia without a VPN, so the native app must work with no Telegram at all. The API issues a 12-hour access token and has no refresh token, which is fine inside Telegram but not for an app that stays signed in for weeks.

The cloud sandbox where Claude works is Linux: it can build and test Android but not iOS. iOS needs a Mac and an Apple Developer account, which is hard to pay for from Russia.

## Decision
- **Layout.** One Gradle project in `mobile/`: `shared` (KMP, Android and iOS targets: API client, models, session, cache, view models), `androidApp` (Jetpack Compose), `iosApp` (SwiftUI on the `shared` framework). The empty `android/` and `ios/` folders are removed.
- **Libraries.** Kotlin 2, Ktor client, kotlinx.serialization, kotlinx.coroutines, SQLDelight for the offline cache, Koin for DI, Coil 3 for images. Realtime uses the official Centrifugo SDKs (centrifuge-java, centrifuge-swift) behind one interface in `shared`. minSdk 26.
- **API client.** Generated at build time from `contracts/openapi.yaml` (ADR 0004) with OpenAPI Generator (`kotlin`, `multiplatform` library); never edited by hand.
- **Sign-in.** The owner chose email only (2026-10-17); it is free and works in Russia without a VPN:
  - email with a one-time 6-digit code, the main method (valid 10 minutes, 5 attempts, rate-limited per email and IP; sent over SMTP set by environment variables, e.g. Yandex 360 or Unisender Go free tier);
  - Telegram as an extra option for those who have it: the app opens `t.me/<bot>?startapp=login_<code>`, the user confirms in the Mini App (its verified initData names the Telegram user, so the bot does not need to receive updates, which a server in Russia may not get; added 2026-10-23), the bot still confirms `/start login_<code>`, the app exchanges the request once with a poll secret. The Mini App keeps initData;
  - VK ID, Yandex ID and SMS are not used now (SMS costs money per message); the identities table lets them be added later without a migration of users. Sign in with Apple may be required with the iOS app, since Telegram counts as third-party sign-in under App Store rules.
- **Identities.** A new table `auth.identities` (user_id, provider, subject, unique provider + subject). A user can link and unlink methods; the last one can't be removed. `auth.users.telegram_id` becomes nullable; existing users get a `telegram` identity.
- **Sessions.** Native clients get an access token (as today) plus a rotating opaque refresh token (60 days, stored hashed, reuse revokes the whole family). On the device it lives in Android Keystore / iOS Keychain.
- **Notifications.** FCM on Android (APNs through FCM on iOS later). A push carries only a type and an id; text is loaded from the API. Users without Telegram get notifications only by push; the bot stays for those who have Telegram, and the user picks the channel.
- **Invites.** `https://<domain>/i/<code>` with Android App Links (and Universal Links later). With the app installed the link opens it; without it the page offers the app and the Telegram bot. Old `t.me` links keep working.
- **Order and distribution.** Android first. A signed APK attached to a GitHub Release for the first friends, then RuStore (free), Google Play later. iOS after a Mac is available, through TestFlight.
- **CI.** A `mobile` job filtered by path: build, ktlint/detekt, unit tests of `shared` and `androidApp`. The iOS job on a macOS runner joins with the iOS app.

## Consequences
The app works for users in Russia without a VPN, and one person can use the Mini App and the app with the same account through a linked Telegram identity. The backend grows an identities table, email sending, refresh tokens, device tokens and a push channel; profile names and avatars stop assuming Telegram. Email addresses are personal data and are stored in Russia (152-FZ) and never logged; the privacy policy has to mention the email sender and Google (FCM) as processors. Shared Kotlin code keeps the iOS app to UI work, but it is blocked until the owner has a Mac. M4 issues: epic #89.
