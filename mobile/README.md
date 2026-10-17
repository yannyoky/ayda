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

Sign-in needs email delivery configured in the backend (`SMTP_*` in `.env`); Telegram sign-in also needs the bot running.

## Checks

The same as the `mobile` CI job:

```bash
./gradlew ktlintCheck lint :shared:testAndroidHostTest :androidApp:testDebugUnitTest assembleDebug
```

`./gradlew ktlintFormat` fixes formatting.

## iOS (needs a Mac)

```bash
brew install xcodegen
cd mobile/iosApp && xcodegen generate && open Ayda.xcodeproj
```

The Xcode build runs `./gradlew :shared:embedAndSignAppleFrameworkForXcode` first and links the `Shared` framework. The iOS part has not been built yet: there is no Mac in CI or in the cloud sessions (#100).

## Tokens on the device

The access and refresh tokens are kept in one file in the app's private storage, encrypted with AES-256-GCM under a key in the Android Keystore (`EncryptedTokenStore`, `KeystoreCipher`). Backups and device transfer exclude app data, so a restored phone signs in again.

## Fonts

Unbounded and Manrope (variable TTF from Google Fonts, SIL Open Font License, texts in `androidApp/src/main/assets/licenses/`) are bundled in the APK, so the app makes no requests to Google for fonts.
