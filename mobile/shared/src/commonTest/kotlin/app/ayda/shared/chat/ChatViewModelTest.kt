package app.ayda.shared.chat

import androidx.lifecycle.viewModelScope
import app.ayda.api.models.Attachment
import app.ayda.api.models.ChatUploadInput
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
import kotlin.time.Duration.Companion.hours

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
                if ("attachment_id" in request.bodyText()) {
                    val voice =
                        message(10, author = "me", text = "", clientId = clientId).removeSuffix("}") +
                            ""","attachment":{"kind":"voice","status":"processing","duration_ms":null,"url":null}}"""
                    return json(voice, HttpStatusCode.Created)
                }
                json(message(10, author = "me", text = "Привет", clientId = clientId), HttpStatusCode.Created)
            }
            call == "POST /conversations/c1/read" -> respond("", HttpStatusCode.NoContent)
            call == "POST /conversations/c1/uploads" ->
                json(
                    """{"media_id":"a1","upload_url":"https://s3.test/chat/uploads/a1",""" +
                        """"headers":{"Content-Type":"audio/mp4"},"expires_at":"2026-10-17T20:15:00Z"}""",
                    HttpStatusCode.Created,
                )
            call == "PUT /chat/uploads/a1" -> respond("", HttpStatusCode.OK)
            call == "DELETE /conversations/c1/messages/3" -> respond("", HttpStatusCode.NoContent)
            call == "DELETE /conversations/c1" -> respond("", HttpStatusCode.NoContent)
            call == "PATCH /conversations/c1/messages/3" ->
                json(
                    message(3, author = "me", text = "в 8").removeSuffix("}") +
                        ""","edited_at":"2026-10-17T20:05:00Z"}""",
                )
            call == "PATCH /conversations/c1/messages/2" ->
                problem(HttpStatusCode.Conflict, "edit-window-over", "Поздно")
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
    fun aVoiceMessageIsUploadedOnceEvenWhenSendingIsRetried() =
        runTest(dispatcher) {
            val model = model()
            advanceUntilIdle()
            sendStatus = HttpStatusCode.ServiceUnavailable
            model.sendRecording(ChatUploadInput.Kind.voice, byteArrayOf(1, 2, 3))
            advanceUntilIdle()
            val failed =
                model.state.value.pending
                    .single()
            assertTrue(failed.failed)
            assertEquals("a1", failed.attachmentId)

            sendStatus = HttpStatusCode.Created
            model.retry(failed)
            advanceUntilIdle()
            assertEquals(1, calls.count { it.startsWith("POST /conversations/c1/uploads") })
            assertEquals(1, calls.count { it.startsWith("PUT /chat/uploads/a1") })
            val sent = calls.last { it.startsWith("POST /conversations/c1/messages") }
            assertTrue("\"attachment_id\":\"a1\"" in sent && "\"text\"" !in sent, sent)
            assertTrue(
                model.state.value.pending
                    .isEmpty(),
            )
            assertEquals(
                Attachment.Status.processing,
                model.state.value.messages
                    .last()
                    .attachment
                    ?.status,
            )
        }

    @Test
    fun aCircleIsUploadedAsVideo() =
        runTest(dispatcher) {
            val model = model()
            advanceUntilIdle()
            model.sendRecording(ChatUploadInput.Kind.video_note, byteArrayOf(4, 5, 6))
            advanceUntilIdle()
            val slot = calls.single { it.startsWith("POST /conversations/c1/uploads") }
            assertTrue("\"kind\":\"video_note\"" in slot && "\"content_type\":\"video/mp4\"" in slot, slot)
            assertTrue(
                model.state.value.pending
                    .isEmpty(),
            )
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
    fun anOwnMessageIsEditedInTheComposer() =
        runTest(dispatcher) {
            val model = model()
            advanceUntilIdle()
            val (second, third) = model.state.value.messages
            model.startEdit(third)
            assertEquals("m3", model.state.value.text)
            model.onTextChange("в 8")
            model.send()
            advanceUntilIdle()
            assertNull(model.state.value.editing)
            assertEquals(
                "в 8",
                model.state.value.messages
                    .last()
                    .text,
            )
            assertTrue(calls.any { it.startsWith("PATCH /conversations/c1/messages/3") && "\"text\":\"в 8\"" in it })
            assertFalse(calls.any { it.startsWith("POST /conversations/c1/messages") })

            model.startEdit(second)
            model.onTextChange("поздно")
            model.send()
            advanceUntilIdle()
            assertTrue(model.state.value.editTooLate)
            assertTrue(model.canEdit(second, second.createdAt + 23.hours))
            assertFalse(model.canEdit(second, second.createdAt + 25.hours))
            model.viewModelScope.cancel()
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
