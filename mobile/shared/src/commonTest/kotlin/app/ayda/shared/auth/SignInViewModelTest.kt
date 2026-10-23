package app.ayda.shared.auth

import app.ayda.api.models.Me
import app.ayda.shared.AydaClient
import app.ayda.shared.InMemoryTokenStore
import app.ayda.shared.TEST_BASE
import app.ayda.shared.json
import app.ayda.shared.problem
import app.ayda.shared.sessionJson
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.MockEngineConfig
import io.ktor.client.engine.mock.MockRequestHandler
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
class SignInViewModelTest {
    private val dispatcher = StandardTestDispatcher()
    private val signedIn = mutableListOf<Me>()

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    // The engine runs on the test dispatcher, so advanceUntilIdle() also waits for the HTTP calls.
    private fun model(handler: MockRequestHandler): SignInViewModel {
        val engine =
            MockEngine(
                MockEngineConfig().apply {
                    dispatcher = this@SignInViewModelTest.dispatcher
                    addHandler(handler)
                },
            )
        return SignInViewModel(SignIn(AydaClient(TEST_BASE, InMemoryTokenStore(), engine))) { signedIn += it }
    }

    @Test
    fun emailThenSixDigitsSignsIn() =
        runTest(dispatcher) {
            val model =
                model { request ->
                    if (request.url.encodedPath.endsWith("/start")) {
                        respond("", HttpStatusCode.Accepted)
                    } else {
                        json(sessionJson("a1", "r1"))
                    }
                }

            model.onEmailChange("anya@example")
            assertFalse(model.state.value.canSendCode)
            model.onEmailChange("anya@example.com")
            model.sendCode()
            advanceUntilIdle()
            assertEquals(SignInState.Step.Code, model.state.value.step)

            model.onCodeChange("12 34 56")
            advanceUntilIdle()

            assertEquals(listOf("Аня"), signedIn.map { it.firstName })
            // After a later sign-out the screen starts from the email step again.
            assertEquals(SignInState(), model.state.value)
        }

    @Test
    fun aWrongCodeShowsTheServerTextAndClearsTheField() =
        runTest(dispatcher) {
            val model =
                model { request ->
                    if (request.url.encodedPath.endsWith("/start")) {
                        respond("", HttpStatusCode.Accepted)
                    } else {
                        problem(HttpStatusCode.Unauthorized, "invalid-code", "Неверный или устаревший код")
                    }
                }
            model.onEmailChange("anya@example.com")
            model.sendCode()
            advanceUntilIdle()

            model.onCodeChange("000000")
            advanceUntilIdle()

            val state = model.state.value
            assertEquals("Неверный или устаревший код", state.error)
            assertEquals("", state.code)
            assertFalse(state.busy)
            assertTrue(signedIn.isEmpty())
        }

    @Test
    fun noNetworkSaysSo() =
        runTest(dispatcher) {
            val model = model { error("connection refused") }
            model.onEmailChange("anya@example.com")

            model.sendCode()
            advanceUntilIdle()

            assertEquals(SignInState.Step.Email, model.state.value.step)
            assertTrue(
                model.state.value.error!!
                    .startsWith("Нет связи"),
            )
        }

    @Test
    fun telegramShowsTheBotLinkUntilCancelled() =
        runTest(dispatcher) {
            val model =
                model { request ->
                    if (request.url.encodedPath.endsWith("/login-requests")) {
                        json(
                            """{"id":"4b8d7c3e-1f2a-4e5b-8c9d-0e1f2a3b4c5d","poll_secret":"s",""" +
                                """"bot_url":"https://t.me/bot?startapp=login_x","expires_at":"2999-01-01T00:00:00Z"}""",
                            HttpStatusCode.Created,
                        )
                    } else {
                        respond("", HttpStatusCode.Accepted)
                    }
                }

            model.signInWithTelegram()
            dispatcher.scheduler.advanceTimeBy(5_000)
            assertEquals("https://t.me/bot?startapp=login_x", model.state.value.telegramUrl)

            model.cancelTelegram()
            advanceUntilIdle()

            assertNull(model.state.value.telegramUrl)
            assertFalse(model.state.value.busy)
        }
}
