package app.ayda.shared.session

import app.ayda.shared.AydaClient
import app.ayda.shared.InMemoryTokenStore
import app.ayda.shared.ME_JSON
import app.ayda.shared.TEST_BASE
import app.ayda.shared.TokenStore
import app.ayda.shared.Tokens
import app.ayda.shared.json
import app.ayda.shared.problem
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.MockEngineConfig
import io.ktor.client.engine.mock.MockRequestHandler
import io.ktor.client.engine.mock.respond
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
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
class SessionViewModelTest {
    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private fun client(
        store: TokenStore,
        handler: MockRequestHandler,
    ) = AydaClient(
        TEST_BASE,
        store,
        MockEngine(
            MockEngineConfig().apply {
                dispatcher = this@SessionViewModelTest.dispatcher
                addHandler(handler)
            },
        ),
    )

    @Test
    fun withoutTokensTheAppAsksToSignIn() =
        runTest(dispatcher) {
            val model = SessionViewModel(client(InMemoryTokenStore()) { error("no calls expected") })
            advanceUntilIdle()

            assertEquals(SessionState.SignedOut, model.state.value)
        }

    @Test
    fun storedTokensRestoreTheProfile() =
        runTest(dispatcher) {
            val model = SessionViewModel(client(InMemoryTokenStore(Tokens("a1", "r1"))) { json(ME_JSON) })
            advanceUntilIdle()

            assertEquals("Аня", assertIs<SessionState.SignedIn>(model.state.value).me.firstName)
        }

    @Test
    fun aRevokedSessionReturnsToSignIn() =
        runTest(dispatcher) {
            val store = InMemoryTokenStore(Tokens("a1", "stolen"))
            val model =
                SessionViewModel(
                    client(store) { request ->
                        if (request.url.encodedPath.endsWith("/auth/refresh")) {
                            problem(HttpStatusCode.Unauthorized, "invalid-refresh-token", "Войдите заново")
                        } else {
                            respond(
                                "",
                                HttpStatusCode.Unauthorized,
                                headersOf(HttpHeaders.WWWAuthenticate, "Bearer"),
                            )
                        }
                    },
                )
            advanceUntilIdle()

            assertEquals(SessionState.SignedOut, model.state.value)
            assertNull(store.load())
        }

    @Test
    fun noNetworkKeepsTheTokensAndOffersARetry() =
        runTest(dispatcher) {
            val store = InMemoryTokenStore(Tokens("a1", "r1"))
            var up = false
            val model = SessionViewModel(client(store) { if (up) json(ME_JSON) else error("offline") })
            advanceUntilIdle()
            assertEquals(SessionState.Offline, model.state.value)

            up = true
            model.restore()
            advanceUntilIdle()

            assertIs<SessionState.SignedIn>(model.state.value)
        }

    @Test
    fun signOutForgetsTheTokens() =
        runTest(dispatcher) {
            val store = InMemoryTokenStore(Tokens("a1", "r1"))
            val model =
                SessionViewModel(
                    client(store) { request ->
                        if (request.url.encodedPath.endsWith(
                                "/logout",
                            )
                        ) {
                            respond("", HttpStatusCode.NoContent)
                        } else {
                            json(ME_JSON)
                        }
                    },
                )
            advanceUntilIdle()

            model.signOut()
            advanceUntilIdle()

            assertEquals(SessionState.SignedOut, model.state.value)
            assertNull(store.load())
        }

    @Test
    fun aNewConsentWhileTheAppIsOpenShowsTheConsentAgain() =
        runTest(dispatcher) {
            var consent = "null"
            val client =
                client(InMemoryTokenStore(Tokens("a1", "r1"))) { request ->
                    if (request.url.encodedPath.endsWith("/me")) {
                        json(ME_JSON.replace(NO_CONSENT, "\"consent_required\":$consent"))
                    } else {
                        problem(HttpStatusCode.Conflict, "consent-required", "Сначала нужно принять согласие")
                    }
                }
            val model = SessionViewModel(client)
            advanceUntilIdle()
            assertNull(assertIs<SessionState.SignedIn>(model.state.value).me.consentRequired)

            consent = "\"2026-10-26\""
            runCatching { client.day.getToday() }
            advanceUntilIdle()

            assertEquals("2026-10-26", assertIs<SessionState.SignedIn>(model.state.value).me.consentRequired)
        }

    private companion object {
        const val NO_CONSENT = "\"consent_required\":null"
    }
}
