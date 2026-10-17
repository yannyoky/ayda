package app.ayda.shared.social

import app.ayda.api.apis.SocialApi.WeekGetLadder
import app.ayda.api.models.Invite
import app.ayda.shared.AydaClient
import app.ayda.shared.InMemoryTokenStore
import app.ayda.shared.TEST_BASE
import app.ayda.shared.json
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.MockEngineConfig
import io.ktor.client.engine.mock.respond
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
class FriendsViewModelTest {
    private val dispatcher = StandardTestDispatcher()
    private val calls = mutableListOf<String>()
    private var friends = listOf("f1", "f2")

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private fun entry(
        rank: Int,
        id: String,
        me: Boolean = false,
    ) = """{"rank":$rank,"user":{"id":"$id","first_name":"$id"},"points":${100 - rank},"streak_days":3,"is_me":$me}"""

    private fun model(): FriendsViewModel {
        val engine =
            MockEngine(
                MockEngineConfig().apply {
                    dispatcher = this@FriendsViewModelTest.dispatcher
                    addHandler { request ->
                        val path = request.url.encodedPath.removePrefix("/api/v1")
                        val call =
                            "${request.method.value} $path" + (request.url.parameters["week"]?.let { "?$it" } ?: "")
                        calls += call
                        when {
                            call.startsWith("GET /ladder") -> {
                                val entries =
                                    (listOf(entry(1, "me", me = true)) + friends.mapIndexed { i, f -> entry(i + 2, f) })
                                        .joinToString(",")
                                val start = if (call.endsWith("previous")) "2026-10-05" else "2026-10-12"
                                json("""{"week_start":"$start","entries":[$entries]}""")
                            }
                            call == "GET /friends" -> {
                                val items =
                                    friends.joinToString(",") {
                                        """{"id":"$it","first_name":"$it","since":"2026-10-01T00:00:00Z"}"""
                                    }
                                json("""{"items":[$items]}""")
                            }
                            call == "POST /invites" ->
                                json(
                                    """{"code":"abcdefghij",""" +
                                        """"url":"https://t.me/ayda_quest_bot?startapp=abcdefghij",""" +
                                        """"expires_at":"2026-10-24T00:00:00Z"}""",
                                    HttpStatusCode.Created,
                                )
                            call.startsWith("DELETE /friends/") -> {
                                friends = friends - path.substringAfterLast('/')
                                respond("", HttpStatusCode.NoContent)
                            }
                            else -> error("unexpected $call")
                        }
                    }
                },
            )
        return FriendsViewModel(AydaClient(TEST_BASE, InMemoryTokenStore(), engine))
    }

    @Test
    fun theLadderSwitchesWeeks() =
        runTest(dispatcher) {
            val model = model()
            advanceUntilIdle()
            assertEquals(
                3,
                model.state.value.ladder
                    ?.propertyEntries
                    ?.size,
            )
            assertEquals(
                listOf("f1", "f2"),
                model.state.value.friends
                    .map { it.id },
            )
            assertFalse(model.state.value.alone)

            model.selectWeek(WeekGetLadder.previous)
            assertNull(model.state.value.ladder)
            advanceUntilIdle()

            assertEquals(
                "2026-10-05",
                model.state.value.ladder
                    ?.weekStart
                    .toString(),
            )
            assertTrue("GET /ladder?previous" in calls)
        }

    @Test
    fun anInviteGoesToTheShareSheet() =
        runTest(dispatcher) {
            val model = model()
            advanceUntilIdle()
            val shared = mutableListOf<Invite>()

            model.invite { shared += it }
            advanceUntilIdle()

            assertEquals("https://t.me/ayda_quest_bot?startapp=abcdefghij", shared.single().url)
            assertTrue(model.state.value.inviteShared)
        }

    @Test
    fun removingAFriendAsksFirstAndUpdatesTheLadder() =
        runTest(dispatcher) {
            friends = listOf("f1")
            val model = model()
            advanceUntilIdle()

            model.askRemove(
                model.state.value.friends
                    .single(),
            )
            model.confirmRemove()
            advanceUntilIdle()

            assertTrue("DELETE /friends/f1" in calls)
            assertTrue(
                model.state.value.friends
                    .isEmpty(),
            )
            assertTrue(model.state.value.alone)
        }
}
