package app.ayda.shared.auth

import app.ayda.api.models.ExchangeTelegramLoginRequestRequest
import app.ayda.api.models.Me
import app.ayda.api.models.Session
import app.ayda.api.models.StartEmailSignInRequest
import app.ayda.api.models.TelegramLoginRequest
import app.ayda.api.models.VerifyEmailSignInRequest
import app.ayda.shared.ApiResult
import app.ayda.shared.AydaClient
import app.ayda.shared.apiCall
import io.ktor.client.call.body
import kotlinx.coroutines.delay
import kotlin.time.Clock
import kotlin.time.Duration
import kotlin.time.Duration.Companion.seconds

/** The sign-in calls of ADR 0009: an email one-time code, or a confirmation in the Telegram bot. */
class SignIn(
    private val client: AydaClient,
    private val clock: Clock = Clock.System,
) {
    /** Sends a six-digit code to [email]. */
    suspend fun sendCode(email: String): ApiResult<Unit> =
        apiCall({ client.auth.startEmailSignIn(StartEmailSignInRequest(email.trim())) }) {}

    /** Exchanges the code for a session and keeps its tokens. */
    suspend fun verifyCode(
        email: String,
        code: String,
    ): ApiResult<Me> =
        apiCall({ client.auth.verifyEmailSignIn(VerifyEmailSignInRequest(email.trim(), code.trim())) }) {
            keep(it.body())
        }

    /** Creates a request the user confirms in the bot; open [TelegramLoginRequest.botUrl] next. */
    suspend fun startTelegram(): ApiResult<TelegramLoginRequest> = apiCall { client.auth.createTelegramLoginRequest() }

    /**
     * Polls until the user confirms in the bot, then keeps the session.
     * Returns `null` when the request expired unconfirmed.
     */
    suspend fun awaitTelegram(
        request: TelegramLoginRequest,
        every: Duration = 2.5.seconds,
    ): ApiResult<Me>? {
        val body = ExchangeTelegramLoginRequestRequest(request.pollSecret)
        while (clock.now() < request.expiresAt) {
            val result =
                apiCall({ client.auth.exchangeTelegramLoginRequest(request.id, body) }) {
                    if (it.status == 202) null else keep(it.body())
                }
            when (result) {
                is ApiResult.Ok -> result.value?.let { return ApiResult.Ok(it) }
                is ApiResult.Failed -> return result
                // A short network drop while the user is in Telegram: keep waiting.
                is ApiResult.Offline -> Unit
            }
            delay(every)
        }
        return null
    }

    private suspend fun keep(session: Session): Me {
        client.signedIn(session)
        return session.user
    }
}
