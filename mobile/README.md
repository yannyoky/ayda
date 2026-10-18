# Ayda mobile

Native apps (ADR 0009): Kotlin Multiplatform shared code, Jetpack Compose on Android, SwiftUI on iOS.

| Module | What |
| --- | --- |
| `shared/` | API client generated from `contracts/openapi.yaml`, session handling (`AydaClient`), screen state shared by both platforms (`SignInViewModel`, `SessionViewModel`), design tokens. Android + iOS targets. |
| `androidApp/` | Android app on Compose. |
| `iosApp/` | SwiftUI skeleton; the Xcode project is generated with XcodeGen and needs a Mac. |

The API client is generated on every build into `shared/build/generated/openapi` and is never committed. If the contract changes in a way the app code no longer fits, `shared` stops compiling, and CI goes red.

## Android: build locally

You need JDK 21 and the Android SDK (Android Studio installs it; the SDK path goes to `local.properties` as `sdk.dir=...` or to `ANDROID_HOME`).

```bash
cd mobile
./gradlew assembleDebug          # androidApp/build/outputs/apk/debug/androidApp-debug.apk
./gradlew installDebug           # onto a connected device or a running emulator
```

The app talks to `http://10.0.2.2:8000/api/v1` by default, which is the host machine as seen from the emulator. Start the backend locally (see `backend/README.md`) or point the app elsewhere:

```bash
./gradlew installDebug -Payda.apiBaseUrl=https://api.example.ru/api/v1
```

Release builds talk HTTPS only; the debug build also allows plain HTTP to `10.0.2.2` and `localhost` (`androidApp/src/debug/res/xml/network_security_config.xml`).

Push notifications need a Firebase project (ADR 0009). Pass its web-app values at build time, as Gradle properties `ayda.firebase.appId`, `projectId`, `apiKey`, `senderId` or as environment variables `AYDA_FIREBASE_APP_ID`, `AYDA_FIREBASE_PROJECT_ID`, `AYDA_FIREBASE_API_KEY`, `AYDA_FIREBASE_SENDER_ID`. Without them the app builds and runs, just without push. The backend needs `FCM_SERVICE_ACCOUNT_JSON` to send.

Sign-in needs email delivery configured in the backend (`SMTP_*` in `.env`); Telegram sign-in also needs the bot running.

## Checks

The same as the `mobile` CI job:

```bash
./gradlew ktlintCheck lint :shared:testAndroidHostTest :androidApp:testDebugUnitTest assembleDebug assembleRelease
```

`./gradlew ktlintFormat` fixes formatting.

## iOS (needs a Mac)

```bash
brew install xcodegen
cd mobile/iosApp && xcodegen generate && open Ayda.xcodeproj
```

The Xcode build runs `./gradlew :shared:embedAndSignAppleFrameworkForXcode` first and links the `Shared` framework. The iOS part has not been built yet: there is no Mac in CI or in the cloud sessions (#100).

## Release

A release APK is built and signed by the **Android release** workflow (Actions → Android release → Run workflow, with a version such as `0.1.0`; the `production` environment's reviewer approves it). It attaches `ayda-<version>.apk` to a GitHub pre-release `android-v<version>` and prints the signing certificate's SHA-256 in the run summary; that value goes into `ANDROID_CERT_SHA256` on the VPS so invite links open the app (`docs/deploy.md`).

One-time setup, by the owner:

1. Create the keystore and keep a copy somewhere safe and offline. Losing it means users must uninstall the app to update it:
   ```bash
   keytool -genkeypair -v -keystore ayda.jks -alias ayda -keyalg RSA -keysize 4096 -validity 10000
   base64 -w0 ayda.jks    # the value for ANDROID_KEYSTORE_BASE64
   ```
2. In GitHub → Settings → Environments → `production` add the secrets `ANDROID_KEYSTORE_BASE64`, `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS`, `ANDROID_KEY_PASSWORD`, `ANDROID_SENTRY_DSN` and, for push, `FIREBASE_API_KEY`; and the variables `FIREBASE_APP_ID`, `FIREBASE_PROJECT_ID`, `FIREBASE_SENDER_ID` (`AYDA_DOMAIN` is already there from the deploy). The keystore never leaves the secrets and is deleted from the runner at the end of the run.
3. Create a project `ayda-android` in GlitchTip and use its DSN as `ANDROID_SENTRY_DSN`.

To build a signed release locally set `AYDA_KEYSTORE_FILE`, `AYDA_KEYSTORE_PASSWORD`, `AYDA_KEY_ALIAS` and `AYDA_KEY_PASSWORD` and run `./gradlew assembleRelease`; without them the release build is unsigned.

Error reports go to GlitchTip through the Sentry SDK when the build has a DSN (`-Payda.sentryDsn=...` or `AYDA_SENTRY_DSN`). `CrashReports` sends the exception type and stack trace only: no user, request, breadcrumbs, messages, extras or device details.

### RuStore

1. Register as a developer at https://dev.rustore.ru (an individual can publish free apps) and create the app `app.ayda`.
2. Upload the signed APK from the GitHub Release. RuStore signs nothing for you here: it keeps our signature, so later releases must use the same keystore.
3. Fill in the card: name "Ayda: квесты дня", the age rating, a link to a public privacy policy page (the store requires one; the app only shows the consent text, so the page still has to be published) and screenshots of Today, Feed and Friends.
4. Send it for moderation; every update is a new upload with a higher version code (the workflow uses the run number).

Google Play comes later: it needs an App Bundle (`bundleRelease`) and a Play Console account, and the same keystore can be the upload key.

## Tokens on the device

The access and refresh tokens are kept in one file in the app's private storage, encrypted with AES-256-GCM under a key in the Android Keystore (`EncryptedTokenStore`, `KeystoreCipher`). Backups and device transfer exclude app data, so a restored phone signs in again.

## Proof photos

Photos come from the system photo picker or the camera app, so the app asks for no storage or camera permission. `PhotoCompressor` decodes each photo, turns it upright, scales it to 2048 px on the longest side and saves it again as JPEG. Re-encoding drops all EXIF, so the location never leaves the phone. The JPEG goes straight to storage through the presigned URL from `POST /media/uploads`; the access token is sent only to the API, never to storage.

## Fonts

Unbounded and Manrope (variable TTF from Google Fonts, SIL Open Font License, texts in `androidApp/src/main/assets/licenses/`) are bundled in the APK, so the app makes no requests to Google for fonts.
