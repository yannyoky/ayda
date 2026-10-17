package app.ayda.shared.coop

import app.ayda.api.models.CoopStatus
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
import kotlin.test.assertTrue

@OptIn(ExperimentalCoroutinesApi::class)
class CoopsTest {
    private val dispatcher = StandardTestDispatcher()
    private val calls = mutableListOf<String>()
    private var status = "invited"
    private var acceptProblem: Pair<HttpStatusCode, String>? = null

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private fun coop() =
        """{"id":"k1","title":"Прогулка","category":"walk","duration_min":30,""" +
            """"owner":{"id":"u2","first_name":"Боря"},""" +
            """"my_status":"$status",""" +
            """"participants":[{"user":{"id":"u2","first_name":"Боря"},"status":"owner",""" +
            """"completed":false}],"my_quest_id":null,"conversation_id":null,"expires_at":"2026-10-18T01:00:00Z",""" +
            """"bonus_awarded":false}"""

    private fun friend(id: String) = """{"id":"$id","first_name":"$id","since":"2026-10-01T00:00:00Z"}"""

    private fun client(): AydaClient {
        val engine =
            MockEngine(
                MockEngineConfig().apply {
                    dispatcher = this@CoopsTest.dispatcher
                    addHandler { request ->
                        val call = "${request.method.value} ${request.url.encodedPath.removePrefix("/api/v1")}"
                        calls += "$call ${request.bodyText()}".trim()
                        val failure = acceptProblem
                        when (call) {
                            "POST /realtime/token" -> json(TOKEN_JSON)
                            "GET /coops" -> json("""{"items":[${coop()}]}""")
                            "GET /coops/k1" -> json(coop())
                            "POST /coops/k1/accept" ->
                                if (failure != null) {
                                    problem(failure.first, failure.second, "Нет")
                                } else {
                                    status = "accepted"
                                    json(coop())
                                }
                            "POST /coops/k1/decline" -> {
                                status = "declined"
                                json(coop())
                            }
                            "GET /friends" ->
                                json("""{"items":[${(1..4).joinToString(",") { friend("f$it") }}]}""")
                            "POST /day-quests/q1/coop" -> json(coop(), HttpStatusCode.Created)
                            else -> error("unexpected $call")
                        }
                    }
                },
            )
        return AydaClient(TEST_BASE, InMemoryTokenStore(), engine)
    }

    @Test
    fun acceptingAnInvitationReloadsTheDay() =
        runTest(dispatcher) {
            val client = client()
            val transport = FakeTransport()
            var dayReloads = 0
            val model = CoopsViewModel(client, Realtime(client, transport)) { dayReloads++ }
            advanceUntilIdle()
            assertEquals(
                listOf("k1"),
                model.state.value.invites
                    .map { it.id },
            )

            model.answer("k1", accept = true)
            advanceUntilIdle()

            assertTrue(
                model.state.value.invites
                    .isEmpty(),
            )
            assertEquals(1, dayReloads)
            transport.publish("""{"type":"coop.updated","coop_id":"k1"}""")
            advanceUntilIdle()
            assertEquals(2, dayReloads)
        }

    @Test
    fun answerErrorsAreExplained() =
        runTest(dispatcher) {
            val client = client()
            val model = CoopViewModel(client, Realtime(client, FakeTransport()), "k1")
            advanceUntilIdle()

            acceptProblem = HttpStatusCode.Conflict to "daily-limit-reached"
            model.answer(accept = true)
            advanceUntilIdle()
            assertEquals(AnswerError.DailyLimit, model.state.value.error)

            acceptProblem = HttpStatusCode.Gone to "coop-over"
            model.answer(accept = true)
            advanceUntilIdle()
            assertEquals(AnswerError.Over, model.state.value.error)

            model.answer(accept = false)
            advanceUntilIdle()
            assertEquals(
                CoopStatus.declined,
                model.state.value.coop
                    ?.myStatus,
            )
        }

    @Test
    fun atMostThreeFriendsAreInvited() =
        runTest(dispatcher) {
            val model = CoopInviteViewModel(client(), "q1")
            advanceUntilIdle()

            (1..4).forEach { model.toggle("f$it") }
            assertEquals(setOf("f1", "f2", "f3"), model.state.value.picked)
            model.toggle("f2")
            var created: String? = null
            model.send { created = it.id }
            advanceUntilIdle()

            assertEquals("k1", created)
            assertTrue("""POST /day-quests/q1/coop {"friend_ids":["f1","f3"]}""" in calls)
        }
}
