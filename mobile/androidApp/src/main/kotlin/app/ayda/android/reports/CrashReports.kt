package app.ayda.android.reports

import android.content.Context
import app.ayda.android.BuildConfig
import io.sentry.SentryEvent
import io.sentry.SentryLevel
import io.sentry.android.core.SentryAndroid

/**
 * Crash and error reports to the self-hosted GlitchTip (ADR 0009). A report says what failed and
 * where, never who or what the user was doing: personal data is never sent (152-FZ).
 */
object CrashReports {
    fun init(context: Context) {
        if (BuildConfig.SENTRY_DSN.isEmpty()) return
        SentryAndroid.init(context) { options ->
            options.dsn = BuildConfig.SENTRY_DSN
            options.isSendDefaultPii = false
            options.isEnableUserInteractionBreadcrumbs = false
            options.isEnableActivityLifecycleBreadcrumbs = false
            options.isEnableAppComponentBreadcrumbs = false
            options.isEnableSystemEventBreadcrumbs = false
            options.isEnableNetworkEventBreadcrumbs = false
            options.isAttachScreenshot = false
            options.isAttachViewHierarchy = false
            options.maxBreadcrumbs = 0
            options.tracesSampleRate = 0.0
            options.environment = if (BuildConfig.DEBUG) "debug" else "release"
            options.setBeforeSend { event, _ -> scrub(event) }
        }
    }

    /** Keeps the exception types and stack traces; drops everything that could name a person. */
    internal fun scrub(event: SentryEvent): SentryEvent {
        event.user = null
        event.request = null
        event.breadcrumbs = null
        event.contexts.remove("device")
        event.serverName = null
        event.message = null
        // Messages may quote what the user typed or a name from the API.
        event.exceptions?.forEach { it.value = null }
        event.setExtras(emptyMap())
        event.setTags(event.tags?.filterKeys { it == "environment" } ?: emptyMap())
        if (event.level == null) event.level = SentryLevel.ERROR
        return event
    }
}
