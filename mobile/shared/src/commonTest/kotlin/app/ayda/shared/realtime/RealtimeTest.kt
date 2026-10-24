package app.ayda.shared.realtime

import app.ayda.shared.AydaClient
import app.ayda.shared.InMemoryTokenStore
import app.ayda.shared.TEST_BASE
import app.ayda.shared.json
import app.ayda.shared.problem
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.MockEngineConfig
import io.ktor.http.HttpStatusCode
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertNull
import kotlin.test.assertTrue

@OptIn(ExperimentalCoroutinesApi::class)
class RealtimeTest {
    private val dispatcher = StandardTestDispatcher()
    private var tokenCalls = 0
    private var configured = true

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private fun realtime(transport: RealtimeTransport): Realtime {
        val engine =
            MockEngine(
                MockEngineConfig().apply {
                    dispatcher = this@RealtimeTest.dispatcher
                    addHandler {
                        tokenCalls++
                        if (configured) {
                            json(
                                TOKEN_JSON,
                            )
                        } else {
                            problem(HttpStatusCode.ServiceUnavailable, "unavailable", "Нет")
                        }
                    }
                },
            )
        return Realtime(AydaClient(TEST_BASE, InMemoryTokenStore(), engine), transport)
    }

    @Test
    fun publicationsBecomeEventsAndALostGapAsksToResync() =
        runTest(dispatcher) {
            val transport = FakeTransport()
            val realtime = realtime(transport)
            val events = mutableListOf<LiveEvent>()
            backgroundScope.launch(UnconfinedTestDispatcher(testScheduler)) { realtime.events.toList(events) }
            advanceUntilIdle()
            assertEquals("wss://api.test/connection/websocket" to "personal:#me", transport.opened)
            assertEquals(RealtimeStatus.Live, realtime.status.value)

            transport.publish(
                """{"type":"message.created","conversation_id":"c1","message":{"id":7,"conversation_id":"c1",""" +
                    """"author":{"id":"u2","first_name":"Боря"},"text":"Привет",""" +
                    """"created_at":"2026-10-17T20:00:00Z",""" +
                    """"client_id":null}}""",
            )
            transport.publish(
                """{"type":"message.updated","conversation_id":"c1","message":{"id":7,"conversation_id":"c1",""" +
                    """"author":{"id":"u2","first_name":"Боря"},"text":"Привет!",""" +
                    """"created_at":"2026-10-17T20:00:00Z","client_id":null,""" +
                    """"edited_at":"2026-10-17T20:01:00Z"}}""",
            )
            transport.publish("""{"type":"message.deleted","conversation_id":"c1","message_id":7}""")
            transport.publish("""{"type":"something.new","x":1}""")
            transport.publish("not json")
            transport.listener!!.onResubscribed(recovered = true)
            transport.listener!!.onResubscribed(recovered = false)

            assertEquals(4, events.size)
            assertEquals("Привет", assertIs<LiveEvent.MessageCreated>(events[0]).message.text)
            assertEquals("Привет!", assertIs<LiveEvent.MessageUpdated>(events[1]).message.text)
            assertEquals(LiveEvent.MessageDeleted("c1", 7), events[2])
            assertEquals(LiveEvent.Resync, events[3])
        }

    @Test
    fun theSdkGetsFreshTokens() =
        runTest(dispatcher) {
            val transport = FakeTransport()
            realtime(transport)
            advanceUntilIdle()
            var result: TokenResult? = null

            transport.tokens!!.fetch { result = it }
            advanceUntilIdle()

            assertEquals(TokenResult.Ok("t1"), result)
            assertEquals(2, tokenCalls)
        }

    @Test
    fun withoutRealtimeOnTheServerItStaysOffAndRetriesOnResume() =
        runTest(dispatcher) {
            configured = false
            val transport = FakeTransport()
            val realtime = realtime(transport)
            advanceUntilIdle()
            assertEquals(RealtimeStatus.Off, realtime.status.value)
            assertNull(transport.opened)

            configured = true
            realtime.pause()
            realtime.resume()
            advanceUntilIdle()

            assertTrue(realtime.live)
            realtime.pause()
            realtime.resume()
            assertEquals(listOf("pause", "resume"), transport.calls)
        }
}
