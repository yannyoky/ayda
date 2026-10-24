package app.ayda.shared

import app.ayda.api.apis.AssistantApi
import app.ayda.api.apis.AuthApi
import app.ayda.api.apis.ChatApi
import app.ayda.api.apis.CoopApi
import app.ayda.api.apis.DayApi
import app.ayda.api.apis.EventsApi
import app.ayda.api.apis.MediaApi
import app.ayda.api.apis.ProfileApi
import app.ayda.api.apis.RecipesApi
import app.ayda.api.apis.ReferenceApi
import app.ayda.api.apis.SocialApi
import app.ayda.api.models.RefreshTokenInput
import app.ayda.api.models.Session
import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.engine.HttpClientEngine
import io.ktor.client.plugins.HttpTimeout
import io.ktor.client.plugins.auth.Auth
import io.ktor.client.plugins.auth.authProvider
import io.ktor.client.plugins.auth.providers.BearerAuthProvider
import io.ktor.client.plugins.auth.providers.BearerTokens
import io.ktor.client.plugins.auth.providers.RefreshTokensParams
import io.ktor.client.plugins.auth.providers.bearer
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.contentType
import io.ktor.http.isSuccess
import io.ktor.serialization.kotlinx.json.json
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.serialization.json.Json

/**
 * One HTTP client for the whole app, shared by the generated API classes.
 *
 * It attaches the access token to every request and, when the server answers 401,
 * rotates the refresh token once and retries. If the refresh token is rejected,
 * the stored tokens are dropped and [signedOut] fires so the app can show sign-in.
 */
class AydaClient(
    baseUrl: String,
    private val tokens: TokenStore,
    engine: HttpClientEngine = platformEngine(),
) {
    val baseUrl: String = baseUrl.trimEnd('/')

    private val signedOutEvents = MutableSharedFlow<Unit>(extraBufferCapacity = 1)

    /** Fires when the session ended on the server side (refresh token expired or revoked). */
    val signedOut: SharedFlow<Unit> = signedOutEvents.asSharedFlow()

    val http: HttpClient =
        HttpClient(engine) {
            expectSuccess = false
            install(ContentNegotiation) { json(ApiJson) }
            // OkHttp gives up reading after 10 s by default, and an assistant answer may take the
            // server up to 12 s of model time plus its own work.
            install(HttpTimeout) {
                connectTimeoutMillis = 10_000
                socketTimeoutMillis = 30_000
                requestTimeoutMillis = 30_000
            }
            install(Auth) {
                bearer {
                    loadTokens { tokens.load()?.toBearer() }
                    refreshTokens { refresh() }
                    // Only our API gets the token; presigned storage uploads must go without it.
                    sendWithoutRequest { it.url.buildString().startsWith(this@AydaClient.baseUrl) }
                }
            }
        }

    val auth = AuthApi(this.baseUrl, http)
    val assistant = AssistantApi(this.baseUrl, http)
    val profile = ProfileApi(this.baseUrl, http)
    val day = DayApi(this.baseUrl, http)
    val events = EventsApi(this.baseUrl, http)
    val social = SocialApi(this.baseUrl, http)
    val chat = ChatApi(this.baseUrl, http)
    val coop = CoopApi(this.baseUrl, http)
    val media = MediaApi(this.baseUrl, http)
    val recipes = RecipesApi(this.baseUrl, http)
    val reference = ReferenceApi(this.baseUrl, http)

    suspend fun isSignedIn(): Boolean = tokens.load() != null

    /** Keeps the tokens of a session returned by any sign-in endpoint. */
    suspend fun signedIn(session: Session) {
        val refresh = requireNotNull(session.refreshToken) { "Native sign-in must return a refresh token" }
        tokens.save(Tokens(session.accessToken, refresh))
        forgetCachedTokens()
    }

    /** Revokes the session on the server when possible and forgets it locally either way. */
    suspend fun signOut() {
        val current = tokens.load()
        tokens.clear()
        forgetCachedTokens()
        if (current != null) {
            runCatching { auth.signOut(RefreshTokenInput(current.refreshToken)) }
        }
    }

    private suspend fun RefreshTokensParams.refresh(): BearerTokens? {
        // Only an expired or revoked access token is a reason to refresh. Other 401s, such as a
        // wrong email code, come without the Bearer challenge and go back to the caller as they are.
        if (response.headers[HttpHeaders.WWWAuthenticate]?.startsWith("Bearer") != true) return null
        val refreshToken = oldTokens?.refreshToken ?: tokens.load()?.refreshToken ?: return null
        val response =
            client.post("$baseUrl/auth/refresh") {
                markAsRefreshTokenRequest()
                contentType(ContentType.Application.Json)
                setBody(RefreshTokenInput(refreshToken))
            }
        return when {
            response.status.isSuccess() -> {
                val session = response.body<Session>()
                val rotated = Tokens(session.accessToken, session.refreshToken ?: refreshToken)
                tokens.save(rotated)
                rotated.toBearer()
            }
            response.status == HttpStatusCode.Unauthorized -> {
                tokens.clear()
                signedOutEvents.tryEmit(Unit)
                null
            }
            // A server or network hiccup: keep the tokens and let the caller see the 401.
            else -> null
        }
    }

    private fun forgetCachedTokens() {
        http.authProvider<BearerAuthProvider>()?.clearToken()
    }

    companion object {
        val ApiJson: Json =
            Json {
                ignoreUnknownKeys = true
            }
    }
}

private fun Tokens.toBearer() = BearerTokens(accessToken, refreshToken)
