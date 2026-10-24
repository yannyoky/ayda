package app.ayda.shared.chat

import androidx.lifecycle.viewModelScope
import app.ayda.shared.AydaClient
import app.ayda.shared.InMemoryTokenStore
import app.ayda.shared.TEST_BASE
import app.ayda.shared.bodyText
import app.ayda.shared.json
import app.ayda.shared.problem
import app.ayda.shared.realtime.FakeTransport
import app.ayda.shared.realtime.Realtime
import app.ayda.shared.realtime.TOKEN_JSON
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.MockEngineConfig
import io.ktor.client.engine.mock.MockRequestHandleScope
import io.ktor.client.engine.mock.respond
import io.ktor.client.request.HttpRequestData
import io.ktor.client.request.HttpResponseData
import io.ktor.http.HttpStatusCode
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.cancel
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

@OptIn(ExperimentalCoroutinesApi::class)
class ChatViewModelTest {
    private val dispatcher = StandardTestDispatcher()
    private val calls = mutableListOf<String>()
    private var sendStatus = HttpStatusCode.Created
    private val read = mutableListOf<Long>()
    private val hidden = mutableListOf<String>()

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private fun message(
        id: Long,
        author: String = "u2",
        text: String = "m$id",
        clientId: String? = null,
        conversation: String = "c1",
    ) = """{"id":$id,"conversation_id":"$conversation",""" +
        """"author":{"id":"$author","first_name":"$author"},"text":"$text",""" +
        """"created_at":"2026-10-17T20:00:00Z","client_id":${clientId?.let { "\"$it\"" } ?: "null"}}"""

    private fun MockRequestHandleScope.server(request: HttpRequestData): HttpResponseData {
        val path = request.url.encodedPath.removePrefix("/api/v1")
        val call = "${request.method.value} $path"
        calls += "$call ${request.url.parameters["cursor"] ?: ""} ${request.bodyText()}".trim()
        return when {
            call == "POST /realtime/token" -> json(TOKEN_JSON)
            call == "GET /conversations/c1" ->
                json(
                    """{"id":"c1","kind":"dm","title":"Боря","members":[{"id":"u2","first_name":"Боря"}],""" +
                        """"can_send":true,""" +
                        """"last_message":null,"unread_count":2,"last_read_message_id":1,"updated_at":"2026-10-17T20:00:00Z"}""",
                )
            call == "GET /conversations/c1/messages" && request.url.parameters["cursor"] == null ->
                json("""{"items":[${message(3)},${message(2)}],"next_cursor":"older"}""")
            call == "GET /conversations/c1/messages" -> json("""{"items":[${message(1)}],"next_cursor":null}""")
            call == "POST /conversations/c1/messages" -> {
                if (sendStatus != HttpStatusCode.Created) return problem(sendStatus, "too-many", "Слишком часто")
                val clientId = Regex("\"client_id\":\"([^\"]+)\"").find(request.bodyText())!!.groupValues[1]
                json(message(10, author = "me", text = "Привет", clientId = clientId), HttpStatusCode.Created)
            }
            call == "POST /conversations/c1/read" -> respond("", HttpStatusCode.NoContent)
            call == "DELETE /conversations/c1/messages/3" -> respond("", HttpStatusCode.NoContent)
            call == "DELETE /conversations/c1" -> respond("", HttpStatusCode.NoContent)
            else -> error("unexpected $call")
        }
    }

    private fun model(transport: FakeTransport = FakeTransport()): ChatViewModel {
        val engine =
            MockEngine(
                MockEngineConfig().apply {
                    dispatcher = this@ChatViewModelTest.dispatcher
                    addHandler { server(it) }
                },
            )
        val client = AydaClient(TEST_BASE, InMemoryTokenStore(), engine)
        return ChatViewModel(client, Realtime(client, transport), "c1", { _, last -> read += last }) { hidden += it }
    }

    @Test
    fun historyIsOldestFirstAndPagesBack() =
        runTest(dispatcher) {
            val model = model()
            advanceUntilIdle()
            assertEquals(
                listOf(2L, 3L),
                model.state.value.messages
                    .map { it.id },
            )
            assertEquals(listOf(3L), read)
            assertTrue("POST /conversations/c1/read  {\"last_read_message_id\":3}" in calls)

            model.loadOlder()
            advanceUntilIdle()

            assertEquals(
                listOf(1L, 2L, 3L),
                model.state.value.messages
                    .map { it.id },
            )
            assertFalse(model.state.value.hasOlder)
        }

    @Test
    fun aSentMessageIsPendingUntilTheServerConfirmsIt() =
        runTest(dispatcher) {
            val transport = FakeTransport()
            val model = model(transport)
            advanceUntilIdle()

            model.onTextChange("  Привет ")
            model.send()
            assertEquals(
                "Привет",
                model.state.value.pending
                    .single()
                    .text,
            )
            assertEquals("", model.state.value.text)
            advanceUntilIdle()

            assertTrue(
                model.state.value.pending
                    .isEmpty(),
            )
            assertEquals(
                10L,
                model.state.value.messages
                    .last()
                    .id,
            )
            // The same message comes back over the personal channel: no duplicate.
            val clientId =
                model.state.value.messages
                    .last()
                    .clientId
            transport.publish(
                """{"type":"message.created","conversation_id":"c1","message":${message(
                    10,
                    "me",
                    "Привет",
                    clientId,
                )}}""",
            )
            transport.publish("""{"type":"message.created","conversation_id":"c1","message":${message(11)}}""")
            transport.publish(
                """{"type":"message.created","conversation_id":"c2","message":${message(12, conversation = "c2")}}""",
            )
            advanceUntilIdle()

            assertEquals(
                listOf(2L, 3L, 10L, 11L),
                model.state.value.messages
                    .map { it.id },
            )
            assertEquals(11L, read.last())
        }

    @Test
    fun aFailedMessageCanBeRetriedWithTheSameClientId() =
        runTest(dispatcher) {
            sendStatus = HttpStatusCode.TooManyRequests
            val model = model()
            advanceUntilIdle()

            model.onTextChange("Привет")
            model.send()
            advanceUntilIdle()
            val failed =
                model.state.value.pending
                    .single()
            assertTrue(failed.failed)
            assertTrue(model.state.value.tooFast)

            sendStatus = HttpStatusCode.Created
            model.retry(failed)
            advanceUntilIdle()

            val sent = calls.filter { it.startsWith("POST /conversations/c1/messages") }
            assertEquals(2, sent.size)
            assertEquals(sent[0], sent[1])
            assertTrue(
                model.state.value.pending
                    .isEmpty(),
            )
        }

    @Test
    fun deletingTheChatForMeAsksFirstAndClosesIt() =
        runTest(dispatcher) {
            val model = model()
            advanceUntilIdle()
            model.askHide()
            assertTrue(model.state.value.askingHide)
            model.cancelHide()
            assertFalse(model.state.value.askingHide)
            assertFalse("DELETE /conversations/c1" in calls)

            model.askHide()
            model.confirmHide()
            advanceUntilIdle()
            assertTrue(model.state.value.hidden)
            assertEquals(listOf("c1"), hidden)
            assertTrue("DELETE /conversations/c1" in calls)
            model.viewModelScope.cancel()
        }

    @Test
    fun deletingAsksFirstAndALiveDeletionRemovesTheMessage() =
        runTest(dispatcher) {
            val transport = FakeTransport()
            val model = model(transport)
            advanceUntilIdle()

            model.askDelete(
                model.state.value.messages
                    .last(),
            )
            model.confirmDelete()
            advanceUntilIdle()
            assertEquals(
                listOf(2L),
                model.state.value.messages
                    .map { it.id },
            )
            assertNull(model.state.value.deleting)

            transport.publish("""{"type":"message.deleted","conversation_id":"c1","message_id":2}""")
            advanceUntilIdle()
            assertTrue(
                model.state.value.messages
                    .isEmpty(),
            )
        }

    @Test
    fun withoutRealtimeTheChatPolls() =
        runTest(dispatcher) {
            val model = model(FakeTransport(connectLive = false))
            runCurrent()
            val before = calls.count { it == "GET /conversations/c1/messages" }

            advanceTimeBy(ChatViewModel.POLL.inWholeMilliseconds + 1)
            runCurrent()

            assertEquals(before + 1, calls.count { it == "GET /conversations/c1/messages" })
            model.viewModelScope.cancel()
        }
}
