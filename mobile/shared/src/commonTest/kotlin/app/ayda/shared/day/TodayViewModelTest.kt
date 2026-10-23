package app.ayda.shared.day

import app.ayda.api.models.Category
import app.ayda.api.models.Mood
import app.ayda.api.models.PoolStatus
import app.ayda.api.models.QuestState
import app.ayda.api.models.RejectReason
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
import kotlinx.coroutines.test.advanceTimeBy
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
class TodayViewModelTest {
    private val dispatcher = StandardTestDispatcher()
    private val calls = mutableListOf<String>()

    /** A tiny stand-in for the day module: quest id to state, in pool order. */
    private val quests = linkedMapOf<String, String>()
    private var pool = "none"
    private var checkin = "null"
    private var replacementsLeft = 5
    private var nextId = 1

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private fun quest(
        id: String,
        state: String,
    ) = """{"id":"$id","source":"catalog","title":"Квест $id","category":"walk","duration_min":30,""" +
        """"base_points":20,"state":"$state","expires_at":"2026-10-18T01:00:00Z"}"""

    private fun dayJson(): String {
        val taken = quests.values.count { it != "offered" }
        val items = quests.entries.joinToString(",") { (id, state) -> quest(id, state) }
        return """{"local_date":"2026-10-17","checkin":$checkin,"pool_status":"$pool","quests":[$items],""" +
            """"limits":{"taken":$taken,"max_taken":30,"scored":0,"max_scored":5,""" +
            """"replacements_left":$replacementsLeft},""" +
            """"points_today":0,"points_week":120,""" +
            """"streak":{"current_days":4,"best_days":9,"freeze_available":true}}"""
    }

    private fun offer(vararg ids: String) = ids.forEach { quests[it] = "offered" }

    private fun MockRequestHandleScope.server(request: HttpRequestData): HttpResponseData {
        val path = request.url.encodedPath.removePrefix("/api/v1")
        val call = "${request.method.value} $path"
        calls += "$call ${request.bodyText()}".trim()
        val id = path.split('/').getOrNull(2).orEmpty()
        val taken = quests.values.count { it != "offered" }
        return when {
            call == "GET /days/today" -> json(dayJson())
            call == "PUT /days/today/checkin" -> {
                checkin = """{"text":"","mood":"tired","submitted_at":"2026-10-17T07:00:00Z"}"""
                pool = "generating"
                json(dayJson(), HttpStatusCode.Accepted)
            }
            call.endsWith("/take") ->
                if (taken >= 30) {
                    problem(HttpStatusCode.Conflict, "limit", "Лимит на сегодня набран")
                } else {
                    quests[id] = "taken"
                    json(quest(id, "taken"))
                }
            call.endsWith("/replace") ->
                if (replacementsLeft == 0) {
                    problem(HttpStatusCode.Conflict, "no-replacements", "Замены закончились")
                } else {
                    replacementsLeft--
                    quests.remove(id)
                    val fresh = "n${nextId++}"
                    quests[fresh] = "offered"
                    json(
                        """{"replaced":${quest(id, "replaced")},"replacement":${quest(fresh, "offered")},""" +
                            """"replacements_left":$replacementsLeft}""",
                    )
                }
            call == "POST /day-quests" ->
                if (taken >= 30) {
                    problem(HttpStatusCode.Conflict, "limit", "")
                } else {
                    quests["own"] = "taken"
                    json(quest("own", "taken"), HttpStatusCode.Created)
                }
            else -> error("unexpected $call")
        }
    }

    private fun model(): TodayViewModel {
        val engine =
            MockEngine(
                MockEngineConfig().apply {
                    dispatcher = this@TodayViewModelTest.dispatcher
                    addHandler { server(it) }
                },
            )
        return TodayViewModel(AydaClient(TEST_BASE, InMemoryTokenStore(), engine))
    }

    @Test
    fun aCheckInShowsThePoolOnceTheAssistantIsDone() =
        runTest(dispatcher) {
            val model = model()
            advanceUntilIdle()
            assertTrue(model.state.value.showCheckinForm)

            model.onMoodChange(Mood.tired)
            model.onCheckinTextChange("  ")
            model.submitCheckin()
            advanceTimeBy(100)
            assertTrue(model.state.value.generating)
            // Nothing is taken yet, so the screen goes on to the picker once.
            assertTrue(model.state.value.openPicker)
            model.pickerOpened()
            assertFalse(model.state.value.openPicker)
            assertTrue(calls.last().contains(""""mood":"tired""""))

            // The pool is ready on the next poll.
            pool = "ready"
            offer("q1", "q2", "q3")
            advanceUntilIdle()

            val state = model.state.value
            assertEquals(PoolStatus.ready, state.day?.poolStatus)
            assertEquals(listOf("q1", "q2", "q3"), state.offered.map { it.id })
            assertFalse(state.showCheckinForm)
        }

    @Test
    fun theUserTakesMoreThanThree() =
        runTest(dispatcher) {
            pool = "ready"
            offer("q1", "q2", "q3", "q4", "q5")
            val model = model()
            advanceUntilIdle()

            listOf("q1", "q2", "q3", "q4", "q5").forEach(model::toggle)
            assertEquals(listOf("q1", "q2", "q3", "q4", "q5"), model.state.value.chosen)
            assertEquals(100, model.state.value.chosenPoints)
            model.toggle("q2")
            assertEquals(listOf("q1", "q3", "q4", "q5"), model.state.value.chosen)

            var closed = false
            model.takeSelected { closed = true }
            advanceUntilIdle()

            assertTrue(closed)
            val state = model.state.value
            assertEquals(listOf("q1", "q3", "q4", "q5"), state.mine.map { it.id })
            assertTrue(state.mine.all { it.state == QuestState.taken })
            assertEquals(26, state.left)
            assertTrue(state.selected.isEmpty())
        }

    @Test
    fun notTodaySwapsTheQuestAndCountsReplacements() =
        runTest(dispatcher) {
            pool = "ready"
            offer("q1", "q2")
            replacementsLeft = 1
            val model = model()
            advanceUntilIdle()

            model.toggle("q1")
            model.askReplace(
                model.state.value.offered
                    .first(),
            )
            model.replace(RejectReason.no_time)
            advanceUntilIdle()

            assertTrue(calls.any { it.startsWith("POST /day-quests/q1/replace") && it.contains("no_time") })
            assertEquals(Notice.ReplacementsLeft(0), model.state.value.notice)
            assertEquals(
                listOf("q2", "n1"),
                model.state.value.offered
                    .map { it.id },
            )
            assertTrue(
                model.state.value.chosen
                    .isEmpty(),
            )
            assertFalse(model.state.value.canReplace)

            model.askReplace(
                model.state.value.offered
                    .first(),
            )
            model.replace(null)
            advanceUntilIdle()
            assertEquals(Notice.NoReplacements, model.state.value.notice)
        }

    @Test
    fun anOwnQuestIsTakenRightAwayUntilTheLimit() =
        runTest(dispatcher) {
            pool = "ready"
            offer("q1")
            val model = model()
            advanceUntilIdle()

            model.openOwnQuest()
            model.editOwnQuest { it.copy(title = "  Дописать отчёт ", category = Category.project, durationMin = 45) }
            var added = 0
            model.addOwnQuest { added++ }
            advanceUntilIdle()

            assertEquals(1, added)
            assertNull(model.state.value.ownQuest)
            assertTrue(calls.any { it.startsWith("POST /day-quests ") && it.contains(""""title":"Дописать отчёт"""") })
            assertEquals(
                listOf("own"),
                model.state.value.mine
                    .map { it.id },
            )

            // The guard against abuse: 30 taken quests.
            repeat(29) { quests["t$it"] = "taken" }
            model.openOwnQuest()
            model.editOwnQuest { it.copy(title = "Ещё один") }
            model.addOwnQuest { added++ }
            advanceUntilIdle()

            assertEquals(1, added)
            assertEquals("На сегодня взято слишком много квестов", model.state.value.error)
        }
}
