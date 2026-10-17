package app.ayda.shared.social

import app.ayda.shared.AydaClient
import app.ayda.shared.InMemoryTokenStore
import app.ayda.shared.TEST_BASE
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
class FeedViewModelTest {
    private val dispatcher = StandardTestDispatcher()
    private val calls = mutableListOf<String>()
    private var likeFails = false

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private fun post(
        id: String,
        likes: Int = 0,
        comments: Int = 0,
    ) = """{"id":"$id","author":{"id":"u1","first_name":"Аня"},"kind":"proof","quest_title":"Прогулка",""" +
        """"category":"walk","caption":null,"photos":[],"local_date":"2026-10-17",""" +
        """"created_at":"2026-10-17T10:00:00Z","like_count":$likes,"liked_by_me":false,"comment_count":$comments}"""

    private fun comment(id: String) =
        """{"id":"$id","author":{"id":"u2","first_name":"Боря"},"text":"Круто","created_at":"2026-10-17T11:00:00Z",""" +
            """"can_delete":true}"""

    private fun MockRequestHandleScope.server(request: HttpRequestData): HttpResponseData {
        val path = request.url.encodedPath.removePrefix("/api/v1")
        val call = "${request.method.value} $path"
        calls += "$call ${request.bodyText()}".trim()
        return when {
            call == "GET /feed" && request.url.parameters["cursor"] == null ->
                json("""{"items":[${post("p1", likes = 2)},${post("p2")}],"next_cursor":"c2"}""")
            call == "GET /feed" -> json("""{"items":[${post("p2")},${post("p3")}],"next_cursor":null}""")
            call == "PUT /posts/p1/like" ->
                if (likeFails) error("offline") else json("""{"like_count":5,"liked_by_me":true}""")
            call == "DELETE /posts/p2" -> respond("", HttpStatusCode.NoContent)
            call == "GET /posts/p1/comments" -> json("""{"items":[${comment("c1")}],"next_cursor":null}""")
            call.startsWith("POST /posts/p1/comments") -> json(comment("c2"), HttpStatusCode.Created)
            call == "DELETE /comments/c1" -> respond("", HttpStatusCode.NoContent)
            else -> problem(HttpStatusCode.NotFound, "not-found", "Нет такого")
        }
    }

    private fun model(): FeedViewModel {
        val engine =
            MockEngine(
                MockEngineConfig().apply {
                    dispatcher = this@FeedViewModelTest.dispatcher
                    addHandler { server(it) }
                },
            )
        return FeedViewModel(AydaClient(TEST_BASE, InMemoryTokenStore(), engine))
    }

    @Test
    fun pagesAreJoinedWithoutDuplicates() =
        runTest(dispatcher) {
            val model = model()
            advanceUntilIdle()
            assertTrue(model.state.value.hasMore)

            model.loadMore()
            advanceUntilIdle()

            assertEquals(
                listOf("p1", "p2", "p3"),
                model.state.value.posts
                    .map { it.id },
            )
            assertFalse(model.state.value.hasMore)
        }

    @Test
    fun aLikeShowsAtOnceAndSettlesOnTheServerCount() =
        runTest(dispatcher) {
            val model = model()
            advanceUntilIdle()

            model.toggleLike("p1")
            val optimistic =
                model.state.value.posts
                    .first()
            assertTrue(optimistic.likedByMe)
            assertEquals(3, optimistic.likeCount)
            advanceUntilIdle()
            assertEquals(
                5,
                model.state.value.posts
                    .first()
                    .likeCount,
            )

            likeFails = true
            model.toggleLike("p2")
            advanceUntilIdle()
            val reverted = model.state.value.posts[1]
            assertFalse(reverted.likedByMe)
            assertEquals(0, reverted.likeCount)
            assertTrue(model.state.value.error != null)
        }

    @Test
    fun deletingAnOwnPostAsksFirst() =
        runTest(dispatcher) {
            val model = model()
            advanceUntilIdle()

            model.askDelete(model.state.value.posts[1])
            model.cancelDelete()
            assertNull(model.state.value.deleting)
            model.askDelete(model.state.value.posts[1])
            model.confirmDelete()
            advanceUntilIdle()

            assertEquals(
                listOf("p1"),
                model.state.value.posts
                    .map { it.id },
            )
            assertTrue("DELETE /posts/p2" in calls)
        }

    @Test
    fun commentsAreAddedAndDeletedWithTheCount() =
        runTest(dispatcher) {
            val model = model()
            advanceUntilIdle()

            model.openComments("p1")
            advanceUntilIdle()
            assertEquals(
                listOf("c1"),
                model.state.value.comments
                    ?.items
                    ?.map { it.id },
            )

            model.onCommentTextChange("  Круто  ")
            model.sendComment()
            advanceUntilIdle()
            assertTrue(calls.any { it == """POST /posts/p1/comments {"text":"Круто"}""" })
            assertEquals(
                listOf("c1", "c2"),
                model.state.value.comments
                    ?.items
                    ?.map { it.id },
            )
            assertEquals(
                "",
                model.state.value.comments
                    ?.text,
            )
            assertEquals(
                1,
                model.state.value.posts
                    .first()
                    .commentCount,
            )

            model.deleteComment(
                model.state.value.comments!!
                    .items
                    .first(),
            )
            advanceUntilIdle()
            assertEquals(
                listOf("c2"),
                model.state.value.comments
                    ?.items
                    ?.map { it.id },
            )
            assertEquals(
                0,
                model.state.value.posts
                    .first()
                    .commentCount,
            )

            model.closeComments()
            assertNull(model.state.value.comments)
        }
}
