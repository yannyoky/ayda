package app.ayda.shared.assistant

import app.ayda.api.models.AssistantCard
import app.ayda.api.models.QuestState
import app.ayda.shared.AydaClient
import app.ayda.shared.InMemoryTokenStore
import app.ayda.shared.TEST_BASE
import app.ayda.shared.bodyText
import app.ayda.shared.json
import app.ayda.shared.problem
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.MockEngineConfig
import io.ktor.client.engine.mock.MockRequestHandleScope
import io.ktor.client.request.HttpRequestData
import io.ktor.client.request.HttpResponseData
import io.ktor.http.HttpStatusCode
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
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

@OptIn(ExperimentalCoroutinesApi::class)
class AssistantViewModelTest {
    private val dispatcher = StandardTestDispatcher()
    private val calls = mutableListOf<String>()
    private var sendStatus = HttpStatusCode.Created
    private var left = 38

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private val quest =
        """{"id":"q9","source":"catalog","title":"Пройти 3 км по набережной","category":"walk",""" +
            """"duration_min":40,"base_points":20,"state":"offered","expires_at":"2026-10-24T01:00:00Z"}"""

    private fun message(
        id: String,
        role: String,
        text: String,
        questId: String? = null,
        cards: String = "",
    ) = """{"id":"$id","role":"$role","text":"$text","quest_id":${questId?.let { "\"$it\"" } ?: "null"},""" +
        """"source":${if (role == "user") "null" else "\"llm\""},"cards":[$cards],""" +
        """"created_at":"2026-10-23T09:00:00Z"}"""

    private val questCard =
        """{"kind":"quest","places":[],"events":[],"recipes":[],"quest":$quest,"note":null,"attribution":null}"""

    private fun MockRequestHandleScope.server(request: HttpRequestData): HttpResponseData {
        val path = request.url.encodedPath.removePrefix("/api/v1")
        val call = "${request.method.value} $path"
        calls += "$call ${request.url.parameters["quest_id"] ?: ""} ${request.bodyText()}".trim()
        return when (call) {
            "GET /assistant/messages" ->
                json(
                    """{"items":[${message("m1", "user", "Работа до шести")},""" +
                        """${message("m2", "assistant", "Хороший план")}],"messages_left":$left}""",
                )
            "POST /assistant/messages" -> {
                if (sendStatus != HttpStatusCode.Created) return problem(sendStatus, "limit", "Сообщения закончились")
                left -= 1
                json(
                    """{"sent":${message("m3", "user", "Придумай квест")},""" +
                        """"reply":${message(
                            "m4",
                            "assistant",
                            "Вот идея",
                            cards = questCard,
                        )},"messages_left":$left}""",
                    HttpStatusCode.Created,
                )
            }
            "POST /day-quests/q9/take" -> json(quest.replace("\"offered\"", "\"taken\""))
            else -> error("unexpected $call")
        }
    }

    private fun model(
        questId: String? = null,
        onTaken: () -> Unit = {},
    ): AssistantViewModel {
        val engine =
            MockEngine(
                MockEngineConfig().apply {
                    dispatcher = this@AssistantViewModelTest.dispatcher
                    addHandler { server(it) }
                },
            )
        return AssistantViewModel(AydaClient(TEST_BASE, InMemoryTokenStore(), engine), questId, onTaken)
    }

    @Test
    fun loadsTheDayTopicAndShowsHints() =
        runTest(dispatcher) {
            val model = model()
            advanceUntilIdle()
            val state = model.state.value
            assertEquals(listOf("m1", "m2"), state.messages.map { it.id })
            assertEquals(38, state.messagesLeft)
            assertTrue(state.showHints)
            assertEquals("GET /assistant/messages", calls.single())
        }

    @Test
    fun aQuestTopicAsksForItsOwnMessages() =
        runTest(dispatcher) {
            model("q1")
            advanceUntilIdle()
            assertEquals("GET /assistant/messages q1", calls.single())
        }

    @Test
    fun theAssistantTypesUntilTheReplyArrives() =
        runTest(dispatcher) {
            val model = model()
            advanceUntilIdle()
            model.onTextChange("  Придумай квест ")
            model.send()
            assertTrue(model.state.value.typing)
            assertEquals("Придумай квест", model.state.value.waiting)
            assertEquals("", model.state.value.text)
            advanceUntilIdle()

            val state = model.state.value
            assertFalse(state.typing)
            assertEquals(listOf("m1", "m2", "m3", "m4"), state.messages.map { it.id })
            assertEquals(37, state.messagesLeft)
            assertEquals(
                AssistantCard.Kind.quest,
                state.messages
                    .last()
                    .cards
                    .single()
                    .kind,
            )
            assertTrue("\"text\":\"Придумай квест\"" in calls.last(), calls.last())
        }

    @Test
    fun aFailedMessageCanBeSentAgain() =
        runTest(dispatcher) {
            val model = model()
            advanceUntilIdle()
            sendStatus = HttpStatusCode.ServiceUnavailable
            model.ask("Где погулять сегодня?")
            advanceUntilIdle()
            assertEquals("Где погулять сегодня?", model.state.value.failed)

            sendStatus = HttpStatusCode.Created
            model.retry()
            advanceUntilIdle()
            assertNull(model.state.value.failed)
            assertEquals(4, model.state.value.messages.size)
        }

    @Test
    fun theDailyLimitClosesTheChat() =
        runTest(dispatcher) {
            val model = model()
            advanceUntilIdle()
            sendStatus = HttpStatusCode.TooManyRequests
            model.onTextChange("Ещё вопрос")
            model.send()
            advanceUntilIdle()
            assertTrue(model.state.value.limitReached)
            assertNull(model.state.value.failed)

            model.onTextChange("И ещё")
            assertFalse(model.state.value.canSend)
        }

    @Test
    fun aQuestFromACardIsTakenOnce() =
        runTest(dispatcher) {
            var refreshed = 0
            val model = model(onTaken = { refreshed++ })
            advanceUntilIdle()
            assertTrue(model.canTake("q9", QuestState.offered))
            model.take("q9")
            advanceUntilIdle()
            assertEquals(1, refreshed)
            assertFalse(model.canTake("q9", QuestState.offered))
        }

    @Test
    fun longTextIsCut() =
        runTest(dispatcher) {
            val model = model()
            model.onTextChange("а".repeat(1500))
            assertEquals(AssistantViewModel.MAX_LENGTH, model.state.value.text.length)
        }
}
