package app.ayda.shared.onboarding

import app.ayda.api.models.HabitDirection
import app.ayda.api.models.Me
import app.ayda.api.models.Theme
import app.ayda.shared.AydaClient
import app.ayda.shared.AydaClient.Companion.ApiJson
import app.ayda.shared.InMemoryTokenStore
import app.ayda.shared.ME_JSON
import app.ayda.shared.TEST_BASE
import app.ayda.shared.Tokens
import app.ayda.shared.bodyText
import app.ayda.shared.json
import app.ayda.shared.problem
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.MockEngineConfig
import io.ktor.client.engine.mock.MockRequestHandleScope
import io.ktor.client.engine.mock.respond
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
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

@OptIn(ExperimentalCoroutinesApi::class)
class OnboardingViewModelTest {
    private val dispatcher = StandardTestDispatcher()
    private val calls = mutableListOf<String>()
    private val changes = mutableListOf<Me>()

    /** The server's view of the user, updated by PATCH /me/profile. */
    private var me: Me = me(firstName = "", onboarded = false)

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private fun me(
        firstName: String,
        onboarded: Boolean,
    ): Me =
        ApiJson
            .decodeFromString<Me>(ME_JSON)
            .copy(firstName = firstName, onboarded = onboarded, city = null)

    private fun MockRequestHandleScope.server(request: HttpRequestData): HttpResponseData {
        val path = request.url.encodedPath.removePrefix("/api/v1")
        calls += "${request.method.value} $path ${request.bodyText()}".trim()
        return when ("${request.method.value} $path") {
            "GET /goals" -> json("""{"items":[{"code":"more_movement","title":"Больше двигаться"}]}""")
            "GET /me/goals" -> json("""{"goal_codes":[]}""")
            "GET /me/habits" -> json("""{"items":[]}""")
            "GET /cities" ->
                json(
                    """{"items":[{"id":435,"name":"Калининград","region_name":"Калининградская область","timezone":"Europe/Kaliningrad"}]}""",
                )
            "PATCH /me/profile" -> {
                val patch = ApiJson.decodeFromString<JsonObject>(request.bodyText())
                (patch["first_name"] as? JsonPrimitive)?.let { me = me.copy(firstName = it.content) }
                if (patch.containsKey("city_id")) {
                    me =
                        me.copy(
                            city =
                                app.ayda.api.models.City(
                                    435,
                                    "Калининград",
                                    "Калининградская область",
                                    "Europe/Kaliningrad",
                                ),
                        )
                }
                (patch["theme"] as? JsonPrimitive)?.let { me = me.copy(theme = Theme.valueOf(it.content)) }
                json(ApiJson.encodeToString(Me.serializer(), me))
            }
            "PUT /me/goals" -> json(request.bodyText())
            "POST /me/habits" ->
                json(
                    """{"id":"6f1e2d3c-4b5a-4968-8776-655443322110","direction":"more","text":"читать"}""",
                    HttpStatusCode.Created,
                )
            "POST /me/onboarding/complete" ->
                if (me.firstName.isBlank()) {
                    problem(HttpStatusCode.Conflict, "name-required", "Укажите имя")
                } else {
                    me = me.copy(onboarded = true)
                    json(ApiJson.encodeToString(Me.serializer(), me))
                }
            else -> respond("", HttpStatusCode.NotFound)
        }
    }

    private fun model(): OnboardingViewModel {
        val engine =
            MockEngine(
                MockEngineConfig().apply {
                    dispatcher = this@OnboardingViewModelTest.dispatcher
                    addHandler { server(it) }
                },
            )
        val client = AydaClient(TEST_BASE, InMemoryTokenStore(Tokens("a", "r")), engine)
        return OnboardingViewModel(client, me) { changes += it }
    }

    @Test
    fun anEmailUserGoesThroughEveryStepAndFinishes() =
        runTest(dispatcher) {
            val model = model()
            advanceUntilIdle()
            assertEquals(OnboardingStep.entries, model.state.value.steps)

            assertFalse(model.state.value.ready)
            model.onNameChange("  Аня ")
            model.next()
            advanceUntilIdle()
            assertEquals(OnboardingStep.City, model.state.value.step)
            assertFalse(model.state.value.ready)

            model.editor.onCityQueryChange("Кали")
            advanceTimeBy(400)
            advanceUntilIdle()
            model.editor.pickCity(
                model.editor.state.value.cities
                    .single(),
            )
            advanceUntilIdle()
            assertTrue(model.state.value.ready)
            model.next()
            advanceUntilIdle()

            model.editor.toggleGoal("more_movement")
            model.next()
            advanceUntilIdle()

            model.editor.addHabit(HabitDirection.more, " читать ")
            advanceUntilIdle()
            assertEquals(
                listOf("читать"),
                model.editor.state.value.habits
                    .map { it.text },
            )
            model.next()
            advanceUntilIdle()

            model.editor.setEvening(null)
            model.next()
            advanceUntilIdle()

            model.editor.pickTheme(Theme.plum)
            advanceUntilIdle()
            model.next()
            advanceUntilIdle()

            assertTrue(changes.last().onboarded)
            assertEquals(Theme.plum, changes.last().theme)
            assertEquals(
                listOf(
                    """PATCH /me/profile {"first_name":"Аня"}""",
                    """GET /cities""",
                    """PATCH /me/profile {"city_id":435}""",
                    """PUT /me/goals {"goal_codes":["more_movement"]}""",
                    """POST /me/habits {"direction":"more","text":"читать"}""",
                    """PATCH /me/profile {"reminders":{"morning_at":"08:30","evening_at":null}}""",
                    """PATCH /me/profile {"theme":"plum"}""",
                    """POST /me/onboarding/complete""",
                ),
                calls.filterNot { it.startsWith("GET /goals") || it.startsWith("GET /me/") },
            )
        }

    @Test
    fun aTelegramUserWithANameSkipsTheNameStepAndCanSkipOptionalSteps() =
        runTest(dispatcher) {
            me =
                me(
                    firstName = "Аня",
                    onboarded = false,
                ).copy(
                    city =
                        app.ayda.api.models
                            .City(435, "Калининград", "", "UTC"),
                )
            val model = model()
            advanceUntilIdle()

            assertEquals(OnboardingStep.City, model.state.value.step)
            model.skip() // the city is required: nothing happens
            assertEquals(OnboardingStep.City, model.state.value.step)
            model.next()
            advanceUntilIdle()
            repeat(3) {
                model.skip()
                advanceUntilIdle()
            }

            assertEquals(OnboardingStep.Theme, model.state.value.step)
            assertTrue(calls.none { it.startsWith("PUT /me/goals") || it.startsWith("PATCH") })
        }

    @Test
    fun goalsStopAtFive() =
        runTest(dispatcher) {
            val model = model()
            advanceUntilIdle()

            (1..7).forEach { model.editor.toggleGoal("g$it") }

            assertEquals(listOf("g1", "g2", "g3", "g4", "g5"), model.editor.state.value.selectedGoals)
        }

    @Test
    fun oneLetterDoesNotSearch() =
        runTest(dispatcher) {
            val model = model()
            advanceUntilIdle()

            model.editor.onCityQueryChange("К")
            advanceTimeBy(1_000)
            advanceUntilIdle()

            assertTrue(calls.none { it.startsWith("GET /cities") })
        }
}
