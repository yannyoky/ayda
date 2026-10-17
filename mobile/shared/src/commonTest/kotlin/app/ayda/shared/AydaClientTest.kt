package app.ayda.shared

import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.MockRequestHandleScope
import io.ktor.client.engine.mock.respond
import io.ktor.client.request.HttpRequestData
import io.ktor.client.request.HttpResponseData
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.content.OutgoingContent
import io.ktor.http.headersOf
import kotlinx.coroutines.async
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

class AydaClientTest {
    private val base = "https://api.test/api/v1"

    private fun session(
        access: String,
        refresh: String?,
    ): String {
        val refreshField = if (refresh == null) "" else ""","refresh_token":"$refresh""""
        return """
            {"access_token":"$access","expires_at":"2026-10-17T12:00:00Z","user":$ME$refreshField}
            """.trimIndent()
    }

    private fun MockRequestHandleScope.json(
        body: String,
        status: HttpStatusCode = HttpStatusCode.OK,
    ): HttpResponseData = respond(body, status, headersOf(HttpHeaders.ContentType, "application/json"))

    private fun MockRequestHandleScope.unauthorized(): HttpResponseData =
        respond(
            PROBLEM,
            HttpStatusCode.Unauthorized,
            headersOf(
                HttpHeaders.ContentType to listOf("application/problem+json"),
                HttpHeaders.WWWAuthenticate to listOf("Bearer"),
            ),
        )

    private fun HttpRequestData.bodyText(): String =
        (body as? OutgoingContent.ByteArrayContent)?.bytes()?.decodeToString() ?: ""

    @Test
    fun sendsTheStoredAccessToken() =
        runTest {
            val seen = mutableListOf<String?>()
            val engine =
                MockEngine { request ->
                    seen += request.headers[HttpHeaders.Authorization]
                    json(ME)
                }
            val client = AydaClient(base, InMemoryTokenStore(Tokens("a1", "r1")), engine)

            val me = client.profile.getMe().body()

            assertEquals("Аня", me.firstName)
            assertEquals(listOf<String?>("Bearer a1"), seen)
        }

    @Test
    fun rotatesTheRefreshTokenOnceAndRetries() =
        runTest {
            val store = InMemoryTokenStore(Tokens("old", "r1"))
            val refreshBodies = mutableListOf<String>()
            val engine =
                MockEngine { request ->
                    when (request.url.encodedPath) {
                        "/api/v1/auth/refresh" -> {
                            refreshBodies += request.bodyText()
                            assertNull(request.headers[HttpHeaders.Authorization])
                            json(session("new", "r2"))
                        }
                        else ->
                            if (request.headers[HttpHeaders.Authorization] == "Bearer new") json(ME) else unauthorized()
                    }
                }
            val client = AydaClient(base, store, engine)

            val response = client.profile.getMe()

            assertTrue(response.success)
            assertEquals(listOf("""{"refresh_token":"r1"}"""), refreshBodies)
            assertEquals(Tokens("new", "r2"), store.load())
        }

    @Test
    fun dropsTheTokensWhenTheRefreshTokenIsRejected() =
        runTest {
            val store = InMemoryTokenStore(Tokens("old", "stolen"))
            val engine = MockEngine { unauthorized() }
            val client = AydaClient(base, store, engine)
            val signedOut = async { client.signedOut.first() }

            val response = client.profile.getMe()

            assertEquals(401, response.status)
            signedOut.await()
            assertNull(store.load())
            assertFalse(client.isSignedIn())
        }

    @Test
    fun aWrongCodeIsNotAReasonToRefresh() =
        runTest {
            val store = InMemoryTokenStore(Tokens("a1", "r1"))
            val paths = mutableListOf<String>()
            val engine =
                MockEngine { request ->
                    paths += request.url.encodedPath
                    respond(
                        PROBLEM,
                        HttpStatusCode.Unauthorized,
                        headersOf(HttpHeaders.ContentType, "application/problem+json"),
                    )
                }
            val client = AydaClient(base, store, engine)

            client.auth.verifyEmailSignIn(
                app.ayda.api.models
                    .VerifyEmailSignInRequest(email = "anya@example.com", code = "000000"),
            )

            assertEquals(listOf("/api/v1/auth/email/verify"), paths)
            assertEquals(Tokens("a1", "r1"), store.load())
        }

    @Test
    fun keepsTheTokensWhenTheServerIsDown() =
        runTest {
            val store = InMemoryTokenStore(Tokens("old", "r1"))
            val engine =
                MockEngine { request ->
                    if (request.url.encodedPath.endsWith("/auth/refresh")) {
                        respond("", HttpStatusCode.ServiceUnavailable)
                    } else {
                        unauthorized()
                    }
                }
            val client = AydaClient(base, store, engine)

            client.profile.getMe()

            assertEquals(Tokens("old", "r1"), store.load())
        }

    @Test
    fun signInStoresTheSessionAndSignOutRevokesIt() =
        runTest {
            val store = InMemoryTokenStore()
            val calls = mutableListOf<String>()
            val engine =
                MockEngine { request ->
                    calls += "${request.method.value} ${request.url.encodedPath} ${request.bodyText()}"
                    when (request.url.encodedPath) {
                        "/api/v1/auth/email/verify" -> json(session("a1", "r1"))
                        "/api/v1/auth/logout" -> respond("", HttpStatusCode.NoContent)
                        else -> json(ME)
                    }
                }
            val client = AydaClient(base, store, engine)

            val session =
                client.auth
                    .verifyEmailSignIn(
                        app.ayda.api.models
                            .VerifyEmailSignInRequest(email = "anya@example.com", code = "123456"),
                    ).body()
            client.signedIn(session)
            assertEquals(Tokens("a1", "r1"), store.load())

            client.signOut()

            assertNull(store.load())
            assertEquals("""POST /api/v1/auth/logout {"refresh_token":"r1"}""", calls.last())
        }

    private companion object {
        const val ME =
            """{"id":"8d6c2f9e-3a1b-4c5d-9e7f-0a1b2c3d4e5f","first_name":"Аня","timezone":"Europe/Kaliningrad",""" +
                """"theme":"plum","reminders":{"morning_at":"08:30","evening_at":null},""" +
                """"consent_required":null,"onboarded":true}"""
        const val PROBLEM = """{"type":"about:blank","title":"Unauthorized","status":401}"""
    }
}
