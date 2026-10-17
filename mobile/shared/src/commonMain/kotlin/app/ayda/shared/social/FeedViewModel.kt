package app.ayda.shared.social

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.ayda.api.models.AddCommentRequest
import app.ayda.api.models.Comment
import app.ayda.api.models.Post
import app.ayda.shared.ApiResult
import app.ayda.shared.AydaClient
import app.ayda.shared.apiCall
import app.ayda.shared.errorText
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** The comments sheet of one post. */
data class CommentsState(
    val postId: String,
    val items: List<Comment> = emptyList(),
    val loaded: Boolean = false,
    val text: String = "",
    val sending: Boolean = false,
    val error: String? = null,
) {
    val canSend: Boolean get() = !sending && text.isNotBlank()
}

data class FeedState(
    val posts: List<Post> = emptyList(),
    val nextCursor: String? = null,
    val loaded: Boolean = false,
    val loadingMore: Boolean = false,
    val error: String? = null,
    val comments: CommentsState? = null,
    /** The own post the user is asked to confirm deleting. */
    val deleting: Post? = null,
) {
    val empty: Boolean get() = loaded && posts.isEmpty()
    val hasMore: Boolean get() = nextCursor != null
}

/** US-13/US-14: proofs and routines of the user and their friends, likes and comments. */
class FeedViewModel(
    private val client: AydaClient,
) : ViewModel() {
    private val mutableState = MutableStateFlow(FeedState())
    val state: StateFlow<FeedState> = mutableState.asStateFlow()

    init {
        refresh()
    }

    fun refresh() {
        viewModelScope.launch {
            when (val page = apiCall { client.social.getFeed() }) {
                is ApiResult.Ok ->
                    mutableState.update {
                        it.copy(
                            posts = page.value.items,
                            nextCursor = page.value.nextCursor,
                            loaded = true,
                            error = null,
                        )
                    }
                else -> mutableState.update { it.copy(error = page.errorText()) }
            }
        }
    }

    fun loadMore() {
        val cursor = state.value.nextCursor ?: return
        if (state.value.loadingMore) return
        mutableState.update { it.copy(loadingMore = true) }
        viewModelScope.launch {
            val page = apiCall { client.social.getFeed(cursor = cursor) }
            mutableState.update { s ->
                if (page is ApiResult.Ok) {
                    // A post can move to the next page when new ones arrive; keep each once.
                    val known = s.posts.map { it.id }.toSet()
                    s.copy(
                        posts = s.posts + page.value.items.filterNot { it.id in known },
                        nextCursor = page.value.nextCursor,
                        loadingMore = false,
                    )
                } else {
                    s.copy(loadingMore = false, error = page.errorText())
                }
            }
        }
    }

    /** Shows the new like at once and settles on the server's count. */
    fun toggleLike(postId: String) {
        val post = state.value.posts.firstOrNull { it.id == postId } ?: return
        val like = !post.likedByMe
        updatePost(
            postId,
        ) { it.copy(likedByMe = like, likeCount = (it.likeCount + if (like) 1 else -1).coerceAtLeast(0)) }
        viewModelScope.launch {
            val result = apiCall { if (like) client.social.likePost(postId) else client.social.unlikePost(postId) }
            when (result) {
                is ApiResult.Ok ->
                    updatePost(postId) {
                        it.copy(likedByMe = result.value.likedByMe, likeCount = result.value.likeCount)
                    }
                else -> {
                    updatePost(postId) { it.copy(likedByMe = post.likedByMe, likeCount = post.likeCount) }
                    mutableState.update { it.copy(error = result.errorText()) }
                }
            }
        }
    }

    fun askDelete(post: Post) = mutableState.update { it.copy(deleting = post) }

    fun cancelDelete() = mutableState.update { it.copy(deleting = null) }

    /** Its photos are deleted from storage; the points stay. */
    fun confirmDelete() {
        val post = state.value.deleting ?: return
        mutableState.update { it.copy(deleting = null) }
        viewModelScope.launch {
            when (val deleted = apiCall({ client.social.deletePost(post.id) }) {}) {
                is ApiResult.Ok -> mutableState.update { s -> s.copy(posts = s.posts.filterNot { it.id == post.id }) }
                else -> mutableState.update { it.copy(error = deleted.errorText()) }
            }
        }
    }

    fun dismissError() = mutableState.update { it.copy(error = null) }

    fun openComments(postId: String) {
        mutableState.update { it.copy(comments = CommentsState(postId)) }
        viewModelScope.launch {
            val page = apiCall { client.social.listComments(postId, limit = COMMENTS_PAGE) }
            updateComments(postId) {
                when (page) {
                    is ApiResult.Ok -> it.copy(items = page.value.items, loaded = true)
                    else -> it.copy(loaded = true, error = page.errorText())
                }
            }
        }
    }

    fun closeComments() = mutableState.update { it.copy(comments = null) }

    fun onCommentTextChange(value: String) =
        mutableState.update { it.copy(comments = it.comments?.copy(text = value.take(COMMENT_MAX), error = null)) }

    fun sendComment() {
        val comments = state.value.comments ?: return
        if (!comments.canSend) return
        val postId = comments.postId
        updateComments(postId) { it.copy(sending = true, error = null) }
        viewModelScope.launch {
            val added = apiCall { client.social.addComment(postId, AddCommentRequest(comments.text.trim())) }
            if (added is ApiResult.Ok) {
                updateComments(postId) { it.copy(items = it.items + added.value, text = "", sending = false) }
                updatePost(postId) { it.copy(commentCount = it.commentCount + 1) }
            } else {
                updateComments(postId) { it.copy(sending = false, error = added.errorText()) }
            }
        }
    }

    fun deleteComment(comment: Comment) {
        val postId = state.value.comments?.postId ?: return
        viewModelScope.launch {
            val deleted = apiCall({ client.social.deleteComment(comment.id) }) {}
            if (deleted is ApiResult.Ok) {
                updateComments(postId) { s -> s.copy(items = s.items.filterNot { it.id == comment.id }) }
                updatePost(postId) { it.copy(commentCount = (it.commentCount - 1).coerceAtLeast(0)) }
            } else {
                updateComments(postId) { it.copy(error = deleted.errorText()) }
            }
        }
    }

    private fun updatePost(
        postId: String,
        change: (Post) -> Post,
    ) = mutableState.update { s -> s.copy(posts = s.posts.map { if (it.id == postId) change(it) else it }) }

    /** Changes the sheet only while it still shows the same post. */
    private fun updateComments(
        postId: String,
        change: (CommentsState) -> CommentsState,
    ) = mutableState.update { s ->
        val current = s.comments
        if (current?.postId == postId) s.copy(comments = change(current)) else s
    }

    companion object {
        const val COMMENT_MAX = 500
        private const val COMMENTS_PAGE = 50
    }
}
