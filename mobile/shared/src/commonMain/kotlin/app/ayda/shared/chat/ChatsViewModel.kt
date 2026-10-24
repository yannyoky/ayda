package app.ayda.shared.chat

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.ayda.api.models.Conversation
import app.ayda.api.models.Friend
import app.ayda.api.models.OpenDirectConversationRequest
import app.ayda.shared.ApiResult
import app.ayda.shared.AydaClient
import app.ayda.shared.apiCall
import app.ayda.shared.errorText
import app.ayda.shared.realtime.Realtime
import app.ayda.shared.realtime.pollWhileOffline
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlin.time.Duration.Companion.seconds

data class ChatsState(
    val conversations: List<Conversation> = emptyList(),
    val loaded: Boolean = false,
    /** Friends to start a chat with. */
    val friends: List<Friend> = emptyList(),
    val opening: Boolean = false,
    val error: String? = null,
) {
    /** For the badge on the tab bar. */
    val unread: Int get() = conversations.sumOf { it.unreadCount }
}

/** US-17: the chat list with live unread counts. Lives for the whole signed-in session. */
class ChatsViewModel(
    private val client: AydaClient,
    private val realtime: Realtime,
) : ViewModel() {
    private val mutableState = MutableStateFlow(ChatsState())
    val state: StateFlow<ChatsState> = mutableState.asStateFlow()

    init {
        refresh()
        viewModelScope.launch {
            // Any chat event can change the order, the last message or an unread count.
            realtime.events.collect { loadConversations() }
        }
        viewModelScope.pollWhileOffline(realtime, POLL) { loadConversations() }
    }

    fun refresh() {
        viewModelScope.launch { loadConversations() }
        viewModelScope.launch {
            val loaded = apiCall { client.social.listFriends() }
            if (loaded is ApiResult.Ok) mutableState.update { it.copy(friends = loaded.value.items) }
        }
    }

    /** Opens (or creates on first use) the direct chat with a friend. */
    fun openDirect(
        userId: String,
        onOpened: (Conversation) -> Unit,
    ) {
        if (state.value.opening) return
        mutableState.update { it.copy(opening = true, error = null) }
        viewModelScope.launch {
            val opened = apiCall { client.chat.openDirectConversation(OpenDirectConversationRequest(userId)) }
            mutableState.update {
                it.copy(
                    opening = false,
                    error = if (opened is ApiResult.Ok) null else opened.errorText(),
                )
            }
            if (opened is ApiResult.Ok) {
                onOpened(opened.value)
                loadConversations()
            }
        }
    }

    /** A chat deleted for this user leaves the list without a reload. */
    fun hidden(conversationId: String) =
        mutableState.update { s -> s.copy(conversations = s.conversations.filterNot { it.id == conversationId }) }

    /** The open chat was read up to [lastReadMessageId]: clear its badge without waiting for the server. */
    fun markedRead(
        conversationId: String,
        lastReadMessageId: Long,
    ) = mutableState.update { s ->
        s.copy(
            conversations =
                s.conversations.map {
                    if (it.id != conversationId) {
                        it
                    } else {
                        it.copy(
                            unreadCount = 0,
                            lastReadMessageId = maxOf(lastReadMessageId, it.lastReadMessageId ?: 0),
                        )
                    }
                },
        )
    }

    private suspend fun loadConversations() {
        val loaded = apiCall { client.chat.listConversations() }
        mutableState.update {
            when (loaded) {
                is ApiResult.Ok -> it.copy(conversations = loaded.value.items, loaded = true, error = null)
                // A failed background reload keeps what is shown.
                else -> if (it.loaded) it else it.copy(error = loaded.errorText())
            }
        }
    }

    companion object {
        val POLL = 15.seconds
    }
}
