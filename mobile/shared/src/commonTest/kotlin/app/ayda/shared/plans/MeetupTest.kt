package app.ayda.shared.plans

import app.ayda.api.models.MeetupOffer
import app.ayda.shared.AydaClient
import app.ayda.shared.InMemoryTokenStore
import app.ayda.shared.TEST_BASE
import app.ayda.shared.bodyText
import app.ayda.shared.json
import app.ayda.shared.problem
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
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

@OptIn(ExperimentalCoroutinesApi::class)
class MeetupTest {
    private val dispatcher = StandardTestDispatcher()
    private val calls = mutableListOf<String>()
    private var offer = venueOffer()
    private var suggestFails = false

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private fun venueOffer() =
        """{"kind":"venue","source":"llm","starts_at":"2026-10-23T16:00:00Z","activity":null,"venues":[""" +
            """{"id":7,"name":"Кофейня на углу","kind":"cafe","address":"Ленина, 1","distance_m":350,""" +
            """"opening_hours":null,"open_now":null,"osm_url":"https://osm.test/n/7",""" +
            """"gis_url":"https://2gis.test/7",""" +
            """"yandex_url":"https://ya.test/7"}],"note":null,"attribution":"© OpenStreetMap contributors"}"""

    private fun coop() =
        """{"id":"k1","title":"Встреча","category":"social","duration_min":90,"owner":{"id":"me","first_name":"Я"},""" +
            """"my_status":"owner","participants":[],"my_quest_id":null,"conversation_id":null,""" +
            """"expires_at":"2026-10-24T01:00:00Z","bonus_awarded":false}"""

    private fun client(): AydaClient {
        val engine =
            MockEngine(
                MockEngineConfig().apply {
                    dispatcher = this@MeetupTest.dispatcher
                    addHandler { request ->
                        val call = "${request.method.value} ${request.url.encodedPath.removePrefix("/api/v1")}"
                        calls += "$call ${request.bodyText()}".trim()
                        when (call) {
                            "POST /conversations/c1/meetup" ->
                                if (suggestFails) {
                                    problem(
                                        HttpStatusCode.NotFound,
                                        "not-found",
                                        "Нет чата",
                                    )
                                } else {
                                    json(offer)
                                }
                            "POST /conversations/c1/meetup/pick" -> json(coop(), HttpStatusCode.Created)
                            else -> error("unexpected $call")
                        }
                    }
                },
            )
        return AydaClient(TEST_BASE, InMemoryTokenStore(), engine)
    }

    @Test
    fun theChatIsReadOnceAndTheCardIsShown() =
        runTest(dispatcher) {
            val model = MeetupViewModel(client(), "c1")
            assertTrue(model.state.value.loading)
            advanceUntilIdle()

            val state = model.state.value
            assertEquals(false, state.loading)
            assertEquals(MeetupOffer.Kind.venue, state.offer?.kind)
            assertEquals(
                listOf("Кофейня на углу"),
                state.offer
                    ?.venues
                    ?.map { it.name },
            )
            assertEquals(1, calls.count { it == "POST /conversations/c1/meetup" })
        }

    @Test
    fun pickingAVenueCreatesThePlanAtTheOfferedTime() =
        runTest(dispatcher) {
            val model = MeetupViewModel(client(), "c1")
            advanceUntilIdle()

            var created: String? = null
            model.pick(7L) { created = it.id }
            advanceUntilIdle()

            assertEquals("k1", created)
            assertTrue(
                """POST /conversations/c1/meetup/pick {"starts_at":"2026-10-23T16:00:00Z","venue_id":7}""" in calls,
                calls.toString(),
            )
        }

    @Test
    fun anOnlineActivityIsPickedWithoutAVenue() =
        runTest(dispatcher) {
            offer =
                """{"kind":"online","source":"llm","starts_at":"2026-10-23T16:00:00Z",""" +
                """"activity":"Дота","venues":[],""" +
                """"note":null,"attribution":null}"""
            val model = MeetupViewModel(client(), "c1")
            advanceUntilIdle()

            model.pick(null) {}
            advanceUntilIdle()

            assertTrue(
                calls.any {
                    it.startsWith("POST /conversations/c1/meetup/pick") && "\"activity\":\"Дота\"" in it
                },
                calls.toString(),
            )
            assertTrue(calls.none { "venue_id" in it })
        }

    @Test
    fun aFailedReadShowsTheErrorAndCanBeRetried() =
        runTest(dispatcher) {
            suggestFails = true
            val model = MeetupViewModel(client(), "c1")
            advanceUntilIdle()
            assertNotNull(model.state.value.error)
            assertNull(model.state.value.offer)

            suggestFails = false
            model.load()
            advanceUntilIdle()
            assertNull(model.state.value.error)
            assertNotNull(model.state.value.offer)
        }
}
