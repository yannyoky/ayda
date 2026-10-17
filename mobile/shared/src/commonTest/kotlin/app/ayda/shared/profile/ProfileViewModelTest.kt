package app.ayda.shared.profile

import app.ayda.api.models.Me
import app.ayda.api.models.NotificationChannel
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
class ProfileViewModelTest {
    private val dispatcher = StandardTestDispatcher()
    private val calls = mutableListOf<String>()
    private val changes = mutableListOf<Me>()
    private var signedOut = 0

    private fun identity(
        id: String,
        provider: String,
        label: String,
    ) = """{"id":"$id","provider":"$provider","label":"$label","created_at":"2026-10-17T00:00:00Z"}"""

    private val telegram = identity("11111111-1111-4111-8111-111111111111", "telegram", "Telegram")
    private val email = identity("22222222-2222-4222-8222-222222222222", "email", "anya@example.com")
    private var identities = listOf(telegram)

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private fun MockRequestHandleScope.server(request: HttpRequestData): HttpResponseData {
        val path = request.url.encodedPath.removePrefix("/api/v1")
        val call = "${request.method.value} $path"
        calls += "$call ${request.bodyText()}".trim()
        return when {
            call == "GET /me/identities" -> json("""{"items":[${identities.joinToString(",")}]}""")
            call == "POST /auth/email/start" -> respond("", HttpStatusCode.Accepted)
            call == "POST /me/identities/email" -> {
                identities = identities + email
                json(email, HttpStatusCode.Created)
            }
            call.startsWith("DELETE /me/identities/") ->
                if (identities.size == 1) {
                    problem(HttpStatusCode.Conflict, "last-identity", "Это последний способ входа")
                } else {
                    identities = identities.drop(1)
                    respond("", HttpStatusCode.NoContent)
                }
            call == "PATCH /me/profile" -> json(ME_JSON.replace("Аня", "Анна"))
            call == "DELETE /me" -> respond("", HttpStatusCode.Accepted)
            call == "GET /goals" -> json("""{"items":[]}""")
            call == "GET /me/goals" -> json("""{"goal_codes":[]}""")
            call == "GET /me/habits" -> json("""{"items":[]}""")
            else -> respond("", HttpStatusCode.NotFound)
        }
    }

    private fun model(): ProfileViewModel {
        val engine =
            MockEngine(
                MockEngineConfig().apply {
                    dispatcher = this@ProfileViewModelTest.dispatcher
                    addHandler { server(it) }
                },
            )
        val client = AydaClient(TEST_BASE, InMemoryTokenStore(Tokens("a", "r")), engine)
        val me = ApiJson.decodeFromString<Me>(ME_JSON)
        return ProfileViewModel(client, me, { changes += it }, { signedOut += 1 })
    }

    @Test
    fun linkingAnEmailSendsACodeThenLinksAndReloads() =
        runTest(dispatcher) {
            val model = model()
            advanceUntilIdle()
            assertFalse(model.state.value.hasEmail)
            assertFalse(model.state.value.canUnlink)

            model.startEmailLink()
            model.onLinkEmailChange("anya@example.com")
            model.sendLinkCode()
            advanceUntilIdle()
            assertTrue(
                model.state.value.emailLink!!
                    .codeSent,
            )
            model.onLinkCodeChange("12-34-56")
            model.confirmEmailLink()
            advanceUntilIdle()

            assertNull(model.state.value.emailLink)
            assertTrue(model.state.value.hasEmail)
            assertTrue(model.state.value.canUnlink)
            assertTrue("""POST /me/identities/email {"email":"anya@example.com","code":"123456"}""" in calls)
        }

    @Test
    fun theLastSignInMethodStaysWithTheServerExplanation() =
        runTest(dispatcher) {
            val model = model()
            advanceUntilIdle()

            model.unlink(
                model.state.value.identities
                    .single(),
            )
            advanceUntilIdle()

            assertEquals("Это последний способ входа", model.state.value.error)
            assertEquals(1, model.state.value.identities.size)
        }

    @Test
    fun renamingReportsTheNewProfile() =
        runTest(dispatcher) {
            val model = model()
            advanceUntilIdle()
            assertFalse(model.state.value.canSaveName)

            model.onNameChange("Анна")
            model.saveName()
            advanceUntilIdle()

            assertEquals("Анна", changes.last().firstName)
            assertTrue("""PATCH /me/profile {"first_name":"Анна"}""" in calls)
        }

    @Test
    fun deletingTheAccountSignsOut() =
        runTest(dispatcher) {
            val model = model()
            advanceUntilIdle()

            model.askDeletion()
            assertTrue(model.state.value.confirmDeletion)
            model.deleteAccount()
            advanceUntilIdle()

            assertTrue("DELETE /me" in calls)
            assertEquals(1, signedOut)
        }

    @Test
    fun theNotificationChannelIsSentOnlyWhenChosen() =
        runTest(dispatcher) {
            val model = model()
            advanceUntilIdle()

            model.pickChannel(NotificationChannel.auto)
            model.saveName()
            model.onNameChange("Анна")
            model.saveName()
            advanceUntilIdle()
            model.pickChannel(NotificationChannel.telegram)
            advanceUntilIdle()

            val patches = calls.filter { it.startsWith("PATCH /me/profile") }
            assertEquals(
                listOf(
                    """PATCH /me/profile {"first_name":"Анна"}""",
                    """PATCH /me/profile {"notification_channel":"telegram"}""",
                ),
                patches,
            )
        }
}
