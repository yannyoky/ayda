package app.ayda.android.reports

import io.sentry.Breadcrumb
import io.sentry.SentryEvent
import io.sentry.protocol.Message
import io.sentry.protocol.Request
import io.sentry.protocol.SentryException
import io.sentry.protocol.User
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class CrashReportsTest {
    @Test
    fun aReportKeepsTheErrorAndLosesThePerson() {
        val event =
            SentryEvent().apply {
                user = User().apply { email = "anna@example.ru" }
                request = Request().apply { url = "https://ayda.example.ru/api/v1/me" }
                addBreadcrumb(Breadcrumb("tapped Anna's chat"))
                message = Message().apply { message = "Anna wrote: hi" }
                exceptions =
                    listOf(
                        SentryException().apply {
                            type = "IllegalStateException"
                            value = "no chat with Anna"
                        },
                    )
                setExtra("friend", "Anna")
                setTag("screen", "chat")
            }

        val report = CrashReports.scrub(event)

        assertNull(report.user)
        assertNull(report.request)
        assertNull(report.breadcrumbs)
        assertNull(report.message)
        assertEquals(emptyMap<String, Any>(), report.extras)
        assertEquals(emptyMap<String, String>(), report.tags)
        assertEquals("IllegalStateException", report.exceptions?.single()?.type)
        assertNull(report.exceptions?.single()?.value)
    }
}
