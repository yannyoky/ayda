package app.ayda.shared.coop

import app.ayda.api.models.CoopPart
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
class PartsTest {
    private val dispatcher = StandardTestDispatcher()
    private val calls = mutableListOf<String>()
    private var itemDone = false
    private var handoff = false
    private var failure: Pair<HttpStatusCode, String>? = null

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private fun user(id: String) = """{"id":"$id","first_name":"$id"}"""

    private fun plan() =
        """{"id":"k1","title":"Готовим: Блины","category":"home","duration_min":60,"owner":${user("me")},""" +
            """"my_status":"owner","participants":[{"user":${user("me")},"status":"owner","completed":false},""" +
            """{"user":${user(
                "lena",
            )},"status":"accepted","completed":false}],"my_quest_id":"q1","conversation_id":"c1",""" +
            """"expires_at":"2026-10-24T01:00:00Z","bonus_awarded":false,"kind":"parts","parts":[""" +
            """{"id":"p1","position":0,"title":"Купить продукты","category":"home","duration_min":40,"place":null,""" +
            """"starts_at":null,"assignee":${user("me")},"state":"open","opens_after":null,"items":[""" +
            """{"id":"i1","text":"Мука: 150 г","done":$itemDone}],"my_quest_id":"q1","handoff":""" +
            (if (handoff) """{"to":${user("lena")},"for_me":false}""" else "null") +
            """},{"id":"p2","position":1,"title":"Приготовить","category":"home","duration_min":30,"place":null,""" +
            """"starts_at":null,"assignee":${user("lena")},"state":"locked","opens_after":"p1","items":[],""" +
            """"my_quest_id":null,"handoff":null}]}"""

    private fun client(): AydaClient {
        val engine =
            MockEngine(
                MockEngineConfig().apply {
                    dispatcher = this@PartsTest.dispatcher
                    addHandler { request ->
                        val call = "${request.method.value} ${request.url.encodedPath.removePrefix("/api/v1")}"
                        calls += "$call ${request.bodyText()}".trim()
                        val problem = failure
                        when {
                            call == "POST /realtime/token" -> json(TOKEN_JSON)
                            call == "GET /coops/k1" -> json(plan())
                            problem != null && call != "GET /coops/k1" -> problem(problem.first, problem.second, "Нет")
                            call == "PATCH /coops/k1/parts/p1/items/i1" -> {
                                itemDone = true
                                json(plan())
                            }
                            call == "POST /coops/k1/parts/p1/handoff" -> {
                                handoff = true
                                json(plan())
                            }
                            call == "DELETE /coops/k1/parts/p1/handoff" -> {
                                handoff = false
                                json(plan())
                            }
                            call == "POST /coops/k1/parts/p1/handoff/accept" -> json(plan())
                            else -> error("unexpected $call")
                        }
                    }
                },
            )
        return AydaClient(TEST_BASE, InMemoryTokenStore(), engine)
    }

    @Test
    fun theCoopComesWithItsParts() =
        runTest(dispatcher) {
            val client = client()
            val model = CoopViewModel(client, Realtime(client, FakeTransport()), "k1")
            advanceUntilIdle()

            val parts =
                model.state.value.coop
                    ?.parts
                    .orEmpty()
            assertEquals(listOf("Купить продукты", "Приготовить"), parts.map { it.title })
            assertEquals(CoopPart.State.open, parts[0].state)
            assertEquals(CoopPart.State.locked, parts[1].state)
        }

    @Test
    fun tickingAnItemUpdatesTheCoop() =
        runTest(dispatcher) {
            val client = client()
            var changed = 0
            val model = CoopViewModel(client, Realtime(client, FakeTransport()), "k1") { changed++ }
            advanceUntilIdle()

            model.tick("p1", "i1", done = true)
            advanceUntilIdle()

            assertTrue("""PATCH /coops/k1/parts/p1/items/i1 {"done":true}""" in calls)
            assertTrue(
                model.state.value.coop
                    ?.parts
                    ?.first()
                    ?.items
                    ?.first()
                    ?.done == true,
            )
            assertEquals(1, changed)
        }

    @Test
    fun aPartIsOfferedAndWithdrawn() =
        runTest(dispatcher) {
            val client = client()
            val model = CoopViewModel(client, Realtime(client, FakeTransport()), "k1")
            advanceUntilIdle()

            model.offerHandoff("p1", "lena")
            advanceUntilIdle()
            assertTrue("""POST /coops/k1/parts/p1/handoff {"friend_id":"lena"}""" in calls)
            assertEquals(
                "lena",
                model.state.value.coop
                    ?.parts
                    ?.first()
                    ?.handoff
                    ?.to
                    ?.id,
            )

            model.withdrawHandoff("p1")
            advanceUntilIdle()
            assertEquals(
                null,
                model.state.value.coop
                    ?.parts
                    ?.first()
                    ?.handoff,
            )

            model.answerHandoff("p1", accept = true)
            advanceUntilIdle()
            assertTrue("POST /coops/k1/parts/p1/handoff/accept" in calls)
        }

    @Test
    fun partErrorsAreExplainedAndTheCoopReloads() =
        runTest(dispatcher) {
            val client = client()
            val model = CoopViewModel(client, Realtime(client, FakeTransport()), "k1")
            advanceUntilIdle()
            val loads = calls.count { it == "GET /coops/k1" }

            failure = HttpStatusCode.Forbidden to "not-part-assignee"
            model.tick("p1", "i1", done = true)
            advanceUntilIdle()
            assertEquals(PartError.NotAssignee, model.state.value.partError)
            assertEquals(loads + 1, calls.count { it == "GET /coops/k1" })

            failure = HttpStatusCode.Conflict to "part-locked"
            model.tick("p1", "i1", done = true)
            advanceUntilIdle()
            assertEquals(PartError.Locked, model.state.value.partError)

            failure = HttpStatusCode.Conflict to "handoff-pending"
            model.offerHandoff("p1", "lena")
            advanceUntilIdle()
            assertEquals(PartError.Pending, model.state.value.partError)

            failure = HttpStatusCode.UnprocessableEntity to "coop-full"
            model.offerHandoff("p1", "eve")
            advanceUntilIdle()
            assertEquals(PartError.Full, model.state.value.partError)

            failure = null
            model.tick("p1", "i1", done = true)
            advanceUntilIdle()
            assertEquals(null, model.state.value.partError)
        }
}
