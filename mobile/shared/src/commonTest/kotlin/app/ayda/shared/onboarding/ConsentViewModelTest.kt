package app.ayda.shared.onboarding

import app.ayda.api.models.Me
import app.ayda.shared.AydaClient
import app.ayda.shared.ErrorTexts
import app.ayda.shared.InMemoryTokenStore
import app.ayda.shared.ME_JSON
import app.ayda.shared.TEST_BASE
import app.ayda.shared.Tokens
import app.ayda.shared.bodyText
import app.ayda.shared.json
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
import kotlin.test.assertTrue

@OptIn(ExperimentalCoroutinesApi::class)
class ConsentViewModelTest {
    private val dispatcher = StandardTestDispatcher()
    private val changes = mutableListOf<Me>()

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private fun model(handler: MockRequestHandler): ConsentViewModel {
        val engine =
            MockEngine(
                MockEngineConfig().apply {
                    dispatcher = this@ConsentViewModelTest.dispatcher
                    addHandler(handler)
                },
            )
        return ConsentViewModel(AydaClient(TEST_BASE, InMemoryTokenStore(Tokens("a", "r")), engine), "2026-10-16") {
            changes += it
        }
    }

    @Test
    fun acceptingSendsTheVersionAndReloadsTheProfile() =
        runTest(dispatcher) {
            val bodies = mutableListOf<String>()
            val model =
                model { request ->
                    if (request.url.encodedPath.endsWith("/consents")) {
                        bodies += request.bodyText()
                        respond("", HttpStatusCode.NoContent)
                    } else {
                        json(ME_JSON)
                    }
                }

            model.accept() // not agreed yet: nothing is sent
            model.onAgreedChange(true)
            model.accept()
            advanceUntilIdle()

            assertEquals(listOf("""{"version":"2026-10-16"}"""), bodies)
            assertEquals(1, changes.size)
        }

    @Test
    fun aFailureStaysOnTheScreen() =
        runTest(dispatcher) {
            val model = model { error("offline") }
            model.onAgreedChange(true)

            model.accept()
            advanceUntilIdle()

            assertEquals(ErrorTexts.OFFLINE, model.state.value.error)
            assertFalse(model.state.value.busy)
            assertTrue(changes.isEmpty())
        }
}
