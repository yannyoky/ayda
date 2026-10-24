package app.ayda.shared.day

import app.ayda.api.models.Day
import app.ayda.api.models.Visibility
import app.ayda.shared.AydaClient
import app.ayda.shared.AydaClient.Companion.ApiJson
import app.ayda.shared.ErrorTexts
import app.ayda.shared.InMemoryTokenStore
import app.ayda.shared.TEST_BASE
import app.ayda.shared.Tokens
import app.ayda.shared.bodyText
import app.ayda.shared.json
import app.ayda.shared.media.MAX_PHOTO_BYTES
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.MockEngineConfig
import io.ktor.client.engine.mock.respond
import io.ktor.client.request.HttpRequestData
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.content.OutgoingContent
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
class CompleteViewModelTest {
    private val dispatcher = StandardTestDispatcher()
    private val requests = mutableListOf<HttpRequestData>()
    private var storageStatus = HttpStatusCode.OK
    private var slots = 0
    private var completed = 0

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private val quest =
        """{"id":"q1","source":"catalog","title":"Прогулка","category":"walk","duration_min":30,""" +
            """"base_points":20,"state":"taken","expires_at":"2026-10-18T01:00:00Z"}"""

    private val day =
        ApiJson.decodeFromString<Day>(
            """{"local_date":"2026-10-17","checkin":null,"pool_status":"ready","quests":[$quest],""" +
                """"limits":{"taken":1,"max_taken":30,"scored":0,"max_scored":5,"replacements_left":5},""" +
                """"points_today":0,"points_week":0,""" +
                """"streak":{"current_days":13,"best_days":13,"freeze_available":true}}""",
        )

    private fun model(): CompleteViewModel {
        val engine =
            MockEngine(
                MockEngineConfig().apply {
                    dispatcher = this@CompleteViewModelTest.dispatcher
                    addHandler { request ->
                        requests += request
                        val path = request.url.encodedPath
                        when {
                            request.url.host == "storage.test" -> respond("", storageStatus)
                            path.endsWith("/media/uploads") -> {
                                slots++
                                json(
                                    """{"media_id":"m$slots",""" +
                                        """"upload_url":"https://storage.test/ayda-media/m$slots",""" +
                                        """"headers":{"Content-Type":"image/jpeg"},""" +
                                        """"expires_at":"2026-10-17T12:00:00Z"}""",
                                    HttpStatusCode.Created,
                                )
                            }
                            path.endsWith("/complete") ->
                                json(
                                    """{"quest":${quest.replace("taken", "completed")},"points_awarded":22,""" +
                                        """"points_breakdown":{"base":20,"visibility_multiplier":1,""" +
                                        """"streak_multiplier":1.1},""" +
                                        """"streak":{"current_days":14,"best_days":14,"freeze_available":true},""" +
                                        """"post_id":"p1","coop_bonus":0}""",
                                )
                            else -> error("unexpected $path")
                        }
                    }
                },
            )
        val tokens = InMemoryTokenStore().apply { kotlinx.coroutines.runBlocking { save(Tokens("a1", "r1")) } }
        return CompleteViewModel(AydaClient(TEST_BASE, tokens, engine), day.quests.first(), day) { completed++ }
    }

    @Test
    fun friendsVisibilityUploadsPhotosWithoutTheTokenThenCompletes() =
        runTest(dispatcher) {
            val model = model()
            assertTrue(model.state.value.ready)
            model.addPhoto(byteArrayOf(1, 2, 3))
            model.addPhoto(byteArrayOf(4, 5))
            model.onCaptionChange("  Дошёл до моря  ")

            model.submit()
            advanceUntilIdle()

            val puts = requests.filter { it.url.host == "storage.test" }
            assertEquals(2, puts.size)
            assertTrue(puts.all { it.headers[HttpHeaders.Authorization] == null })
            assertEquals("image/jpeg", (puts.first().body as OutgoingContent).contentType.toString())
            assertTrue(
                requests
                    .first {
                        it.url.encodedPath.endsWith(
                            "/media/uploads",
                        )
                    }.bodyText()
                    .contains(""""size_bytes":3"""),
            )
            val complete = requests.last()
            assertEquals("Bearer a1", complete.headers[HttpHeaders.Authorization])
            val body = complete.bodyText()
            assertTrue(body.contains(""""media_ids":["m1","m2"]"""), body)
            assertTrue(body.contains(""""caption":"Дошёл до моря""""), body)
            assertEquals(
                22,
                model.state.value.result
                    ?.pointsAwarded,
            )
            assertEquals(1, completed)
        }

    @Test
    fun aVideoGoesAloneAndIsUploadedAsVideo() =
        runTest(dispatcher) {
            val model = model()
            model.addVideo(byteArrayOf(1), "image/gif")
            assertEquals(PhotoError.VideoUnsupported, model.state.value.photoError)
            model.addVideo(byteArrayOf(1, 2, 3, 4), "video/quicktime")
            assertNull(model.state.value.photoError)
            assertFalse(model.state.value.canAddPhoto)
            model.addPhoto(byteArrayOf(1))
            model.addCircle(byteArrayOf(9))
            assertTrue(model.state.value.photos.isEmpty())

            model.submit()
            advanceUntilIdle()

            val slot = requests.first { it.url.encodedPath.endsWith("/media/uploads") }.bodyText()
            assertTrue(slot.contains(""""kind":"video""""), slot)
            assertTrue(slot.contains(""""content_type":"video/quicktime""""), slot)
            assertTrue(requests.last().bodyText().contains(""""media_ids":["m1"]"""))
            assertEquals(1, completed)
        }

    @Test
    fun aCircleReplacesTheChoiceUntilRemoved() =
        runTest(dispatcher) {
            val model = model()
            model.addCircle(byteArrayOf(1, 2))
            assertEquals(
                app.ayda.api.models.CreateUploadRequest.Kind.video_note,
                model.state.value.clip
                    ?.kind,
            )
            assertFalse(model.state.value.canAddClip)
            model.removeClip()
            assertTrue(model.state.value.canAddPhoto && model.state.value.canAddClip)
        }

    @Test
    fun aFeedPostCanBeTextOnly() =
        runTest(dispatcher) {
            val model = model()
            model.onCaptionChange("Прошёл 5 км")

            model.submit()
            advanceUntilIdle()

            assertEquals(0, slots)
            val body = requests.single().bodyText()
            assertTrue(body.contains(""""visibility":"friends""""), body)
            assertTrue(body.contains(""""caption":"Прошёл 5 км""""), body)
            assertEquals(1, completed)
        }

    @Test
    fun personalVisibilityNeedsNoPhotos() =
        runTest(dispatcher) {
            val model = model()
            model.addPhoto(byteArrayOf(1))
            model.onVisibilityChange(Visibility.personal)

            model.submit()
            advanceUntilIdle()

            assertEquals(0, slots)
            assertEquals("""{"visibility":"personal"}""", requests.single().bodyText())
            assertEquals(1, completed)
        }

    @Test
    fun aFailedUploadKeepsThePhotosAndShowsAnError() =
        runTest(dispatcher) {
            storageStatus = HttpStatusCode.Forbidden
            val model = model()
            model.addPhoto(byteArrayOf(1))

            model.submit()
            advanceUntilIdle()

            val state = model.state.value
            assertNull(state.result)
            assertEquals(1, state.photos.size)
            assertEquals(ErrorTexts.UPLOAD, state.error)
            assertFalse(state.busy)
            assertEquals(0, completed)
        }

    @Test
    fun photosAreCheckedAndPointsPreviewed() =
        runTest(dispatcher) {
            val model = model()
            model.addPhoto(ByteArray(MAX_PHOTO_BYTES + 1))
            assertEquals(PhotoError.TooBig, model.state.value.photoError)
            repeat(4) { model.addPhoto(byteArrayOf(it.toByte())) }
            assertEquals(3, model.state.value.photos.size)
            model.removePhoto(
                model.state.value.photos
                    .first()
                    .id,
            )
            assertEquals(2, model.state.value.photos.size)

            // 13 days plus today's first completion is two full weeks: x1.2.
            assertEquals(24, model.expectedPoints(Visibility.friends))
            assertEquals(12, model.expectedPoints(Visibility.personal))
        }
}
