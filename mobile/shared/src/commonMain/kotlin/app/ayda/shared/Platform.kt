package app.ayda.shared

import io.ktor.client.engine.HttpClientEngine

/** OkHttp on Android, NSURLSession on iOS. */
internal expect fun platformEngine(): HttpClientEngine
