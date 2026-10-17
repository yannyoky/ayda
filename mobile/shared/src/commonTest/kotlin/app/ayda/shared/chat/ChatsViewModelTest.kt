package app.ayda.shared.chat

import app.ayda.shared.AydaClient
import app.ayda.shared.InMemoryTokenStore
import app.ayda.shared.TEST_BASE
import app.ayda.shared.json
import app.ayda.shared.realtime.FakeTransport
import app.ayda.shared.realtime.Realtime
import app.ayda.shared.realtime.TOKEN_JSON
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.MockEngineConfig
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals

@OptIn(ExperimentalCoroutinesApi::class)
class ChatsViewModelTest {
    private val dispatcher = StandardTestDispatcher()
    private var unread = 2

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private fun conversation(
        id: String,
        unread: Int,
    ) = """{"id":"$id","kind":"dm","title":"Боря","members":[],"can_send":true,"last_message":null,""" +
        """"unread_count":$unread,"last_read_message_id":null,"updated_at":"2026-10-17T20:00:00Z"}"""

    private fun model(transport: FakeTransport): ChatsViewModel {
        val engine =
            MockEngine(
                MockEngineConfig().apply {
                    dispatcher = this@ChatsViewModelTest.dispatcher
                    addHandler { request ->
                        when (request.url.encodedPath.removePrefix("/api/v1")) {
                            "/realtime/token" -> json(TOKEN_JSON)
                            "/conversations" ->
                                json(
                                    """{"items":[${conversation("c1", unread)},${conversation("c2", 1)}]}""",
                                )
                            "/friends" ->
                                json(
                                    """{"items":[{"id":"u2","first_name":"Боря","since":"2026-10-01T00:00:00Z"}]}""",
                                )
                            "/conversations/direct" -> json(conversation("c3", 0))
                            else -> error("unexpected ${request.url}")
                        }
                    }
                },
            )
        val client = AydaClient(TEST_BASE, InMemoryTokenStore(), engine)
        return ChatsViewModel(client, Realtime(client, transport))
    }

    @Test
    fun unreadCountsFollowLiveEvents() =
        runTest(dispatcher) {
            val transport = FakeTransport()
            val model = model(transport)
            advanceUntilIdle()
            assertEquals(3, model.state.value.unread)
            assertEquals(
                "u2",
                model.state.value.friends
                    .single()
                    .id,
            )

            unread = 5
            transport.publish(
                """{"type":"conversation.read","conversation_id":"c2","user_id":"u2","last_read_message_id":4}""",
            )
            advanceUntilIdle()
            assertEquals(6, model.state.value.unread)

            model.markedRead("c1", 9)
            assertEquals(1, model.state.value.unread)
        }

    @Test
    fun aDirectChatOpensForAFriend() =
        runTest(dispatcher) {
            val model = model(FakeTransport())
            advanceUntilIdle()
            var opened: String? = null

            model.openDirect("u2") { opened = it.id }
            advanceUntilIdle()

            assertEquals("c3", opened)
        }
}
