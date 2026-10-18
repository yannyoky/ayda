package app.ayda.shared.social

import app.ayda.shared.AydaClient
import app.ayda.shared.InMemoryTokenStore
import app.ayda.shared.TEST_BASE
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
import kotlin.test.assertIs
import kotlin.test.assertNull

@OptIn(ExperimentalCoroutinesApi::class)
class InviteTest {
    private val dispatcher = StandardTestDispatcher()
    private val calls = mutableListOf<String>()
    private var failure: HttpStatusCode? = null

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private fun model(code: String = "k3J9xQ2mLp"): InviteViewModel {
        val engine =
            MockEngine(
                MockEngineConfig().apply {
                    dispatcher = this@InviteTest.dispatcher
                    addHandler { request ->
                        calls += "${request.method.value} ${request.url.encodedPath.removePrefix("/api/v1")}"
                        failure?.let { problem(it, "invite", "Нет") }
                            ?: json("""{"id":"u2","first_name":"Боря","since":"2026-10-17T00:00:00Z"}""")
                    }
                },
            )
        return InviteViewModel(AydaClient(TEST_BASE, InMemoryTokenStore(), engine), code)
    }

    @Test
    fun onlyInvitePathsGiveACode() {
        assertEquals("k3J9xQ2mLp", InviteLink.codeFrom("/i/k3J9xQ2mLp"))
        assertEquals("k3J9xQ2mLp", InviteLink.codeFrom("/i/k3J9xQ2mLp/"))
        assertNull(InviteLink.codeFrom("/i/short"))
        assertNull(InviteLink.codeFrom("/x/k3J9xQ2mLp"))
        assertNull(InviteLink.codeFrom("/i/k3J9xQ2mLp/more"))
        assertNull(InviteLink.codeFrom("/i/../../etc/passwd"))
        assertNull(InviteLink.codeFrom(null))
    }

    @Test
    fun acceptingMakesFriends() =
        runTest(dispatcher) {
            val model = model()
            assertEquals(InviteState.Accepting, model.state.value)
            advanceUntilIdle()

            val state = model.state.value
            assertIs<InviteState.Accepted>(state)
            assertEquals("Боря", state.friend.firstName)
            assertEquals(listOf("POST /invites/k3J9xQ2mLp/accept"), calls)
        }

    @Test
    fun refusalsAreTold() =
        runTest(dispatcher) {
            val model = model()
            advanceUntilIdle()
            val expected =
                mapOf(
                    HttpStatusCode.Conflict to InviteState.Own,
                    HttpStatusCode.Gone to InviteState.Expired,
                    HttpStatusCode.NotFound to InviteState.Unknown,
                )
            expected.forEach { (status, state) ->
                failure = status
                model.accept()
                advanceUntilIdle()
                assertEquals(state, model.state.value)
            }
            failure = HttpStatusCode.InternalServerError
            model.accept()
            advanceUntilIdle()
            assertIs<InviteState.Failed>(model.state.value)
        }
}
