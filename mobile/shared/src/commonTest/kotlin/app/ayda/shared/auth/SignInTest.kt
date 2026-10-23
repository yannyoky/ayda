package app.ayda.shared.auth

import app.ayda.api.models.TelegramLoginRequest
import app.ayda.shared.ApiProblem
import app.ayda.shared.ApiResult
import app.ayda.shared.AydaClient
import app.ayda.shared.InMemoryTokenStore
import app.ayda.shared.TEST_BASE
import app.ayda.shared.Tokens
import app.ayda.shared.bodyText
import app.ayda.shared.json
import app.ayda.shared.problem
import app.ayda.shared.sessionJson
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.http.HttpStatusCode
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.currentTime
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertNull
import kotlin.time.Clock
import kotlin.time.Duration.Companion.milliseconds
import kotlin.time.Duration.Companion.minutes
import kotlin.time.Instant

@OptIn(ExperimentalCoroutinesApi::class)
class SignInTest {
    private val start = Instant.parse("2026-10-17T12:00:00Z")

    /** Moves with the test scheduler, so polling `delay`s advance it. */
    private fun TestScope.clock() =
        object : Clock {
            override fun now(): Instant = start + currentTime.milliseconds
        }

    private fun request() =
        TelegramLoginRequest(
            id = "4b8d7c3e-1f2a-4e5b-8c9d-0e1f2a3b4c5d",
            pollSecret = "s3cret",
            botUrl = "https://t.me/ayda_quest_bot?startapp=login_x8Kq2LmN",
            expiresAt = start + 5.minutes,
        )

    @Test
    fun aRightCodeSignsInAndKeepsTheTokens() =
        runTest {
            val store = InMemoryTokenStore()
            val bodies = mutableListOf<String>()
            val engine =
                MockEngine { request ->
                    bodies += request.bodyText()
                    when (request.url.encodedPath) {
                        "/api/v1/auth/email/start" -> respond("", HttpStatusCode.Accepted)
                        else -> json(sessionJson("a1", "r1"))
                    }
                }
            val signIn = SignIn(AydaClient(TEST_BASE, store, engine))

            assertEquals(ApiResult.Ok(Unit), signIn.sendCode("  anya@example.com "))
            val me = signIn.verifyCode("anya@example.com", "123456")

            assertEquals("Аня", assertIs<ApiResult.Ok<*>>(me).let { (it.value as app.ayda.api.models.Me).firstName })
            assertEquals(Tokens("a1", "r1"), store.load())
            assertEquals(
                listOf("""{"email":"anya@example.com"}""", """{"email":"anya@example.com","code":"123456"}"""),
                bodies,
            )
        }

    @Test
    fun aWrongCodeComesBackAsTheServerExplainedIt() =
        runTest {
            val engine =
                MockEngine { problem(HttpStatusCode.Unauthorized, "invalid-code", "Неверный или устаревший код") }
            val signIn = SignIn(AydaClient(TEST_BASE, InMemoryTokenStore(), engine))

            val result = signIn.verifyCode("anya@example.com", "000000")

            assertEquals(ApiResult.Failed(ApiProblem(401, "invalid-code", "Неверный или устаревший код")), result)
        }

    @Test
    fun telegramPollsUntilTheUserConfirms() =
        runTest {
            var polls = 0
            val engine =
                MockEngine { request ->
                    assertEquals("""{"poll_secret":"s3cret"}""", request.bodyText())
                    polls += 1
                    if (polls < 3) respond("", HttpStatusCode.Accepted) else json(sessionJson("a1", "r1"))
                }
            val store = InMemoryTokenStore()
            val signIn = SignIn(AydaClient(TEST_BASE, store, engine), clock())

            val result = signIn.awaitTelegram(request())

            assertIs<ApiResult.Ok<*>>(result)
            assertEquals(3, polls)
            assertEquals(Tokens("a1", "r1"), store.load())
        }

    @Test
    fun telegramGivesUpWhenTheRequestExpires() =
        runTest {
            val engine = MockEngine { respond("", HttpStatusCode.Accepted) }
            val signIn = SignIn(AydaClient(TEST_BASE, InMemoryTokenStore(), engine), clock())

            assertNull(signIn.awaitTelegram(request()))
            assertEquals(5.minutes.inWholeMilliseconds, currentTime)
        }
}
