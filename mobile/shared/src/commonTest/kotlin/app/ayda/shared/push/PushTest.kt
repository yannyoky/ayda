package app.ayda.shared.push

import app.ayda.api.models.RegisterMyDeviceRequest
import app.ayda.shared.AydaClient
import app.ayda.shared.InMemoryTokenStore
import app.ayda.shared.TEST_BASE
import app.ayda.shared.Tokens
import app.ayda.shared.bodyText
import app.ayda.shared.json
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.http.HttpStatusCode
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

class PushTest {
    @Test
    fun aPushOpensTheMatchingScreen() {
        assertEquals(PushTarget.Today, PushTarget.from(mapOf("kind" to "reminder.morning", "day" to "2026-10-17")))
        assertEquals(PushTarget.Feed, PushTarget.from(mapOf("kind" to "social.digest")))
        assertEquals(PushTarget.Friends, PushTarget.from(mapOf("kind" to "ladder.weekly")))
        assertEquals(
            PushTarget.Chat("c1"),
            PushTarget.from(mapOf("kind" to "chat.message", "conversation_id" to "c1", "message_id" to "7")),
        )
        assertEquals(
            PushTarget.Coop("k1"),
            PushTarget.from(
                mapOf(
                    "kind" to "coop.bonus",
                    "coop_id" to "k1",
                    "points" to "15",
                ),
            ),
        )
        assertEquals(PushTarget.Today, PushTarget.from(mapOf("kind" to "something.later")))
        assertNull(PushTarget.from(mapOf("kind" to "chat.message")))
        assertNull(PushTarget.from(mapOf("google.message_id" to "x")))
    }

    @Test
    fun theTokenIsRegisteredAndRemovedOnSignOut() =
        runTest {
            val calls = mutableListOf<String>()
            val engine =
                MockEngine { request ->
                    calls +=
                        "${request.method.value} ${request.url.encodedPath.removePrefix(
                            "/api/v1",
                        )} ${request.bodyText()}".trim()
                    if (request.method.value == "PUT") {
                        json("""{"id":"d1","platform":"android","created_at":"2026-10-17T20:00:00Z"}""")
                    } else {
                        respond("", HttpStatusCode.NoContent)
                    }
                }
            val store = InMemoryDeviceStore()
            val tokens = InMemoryTokenStore()
            val push =
                PushRegistration(AydaClient(TEST_BASE, tokens, engine), store, RegisterMyDeviceRequest.Platform.android)

            assertFalse(push.register("fcm-1"))
            tokens.save(Tokens("a1", "r1"))
            assertTrue(push.register("fcm-1"))
            assertEquals("d1", store.load())
            push.unregister()
            push.unregister()

            assertEquals(
                listOf("""PUT /me/devices {"platform":"android","token":"fcm-1"}""", "DELETE /me/devices/d1"),
                calls,
            )
            assertNull(store.load())
        }
}
