package app.ayda.shared.chat

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.ayda.api.models.ChatUploadInput
import app.ayda.api.models.Conversation
import app.ayda.api.models.MarkConversationReadRequest
import app.ayda.api.models.Message
import app.ayda.api.models.MessageEdit
import app.ayda.api.models.MessageInput
import app.ayda.shared.ApiResult
import app.ayda.shared.AydaClient
import app.ayda.shared.apiCall
import app.ayda.shared.errorText
import app.ayda.shared.media.uploadRecording
import app.ayda.shared.realtime.LiveEvent
import app.ayda.shared.realtime.Realtime
import app.ayda.shared.realtime.pollWhileOffline
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlin.time.Clock
import kotlin.time.Duration.Companion.hours
import kotlin.time.Duration.Companion.seconds
import kotlin.time.Instant
import kotlin.uuid.ExperimentalUuidApi
import kotlin.uuid.Uuid

/** A voice message or a circle (MP4) on its way to the chat. Not a data class: it holds bytes. */
class Recording(
    val kind: ChatUploadInput.Kind,
    val bytes: ByteArray,
)

/** A message the user wrote that the server has not confirmed yet. */
data class PendingMessage(
    val clientId: String,
    val text: String,
    val failed: Boolean = false,
    /** A recording to upload first; kept until the message is saved, so a retry resends it. */
    val recording: Recording? = null,
    /** Set once the recording is uploaded, so a retry does not upload it again. */
    val attachmentId: String? = null,
)

data class ChatState(
    val conversation: Conversation? = null,
    /** Oldest first. */
    val messages: List<Message> = emptyList(),
    val loaded: Boolean = false,
    val olderCursor: String? = null,
    val loadingOlder: Boolean = false,
    val pending: List<PendingMessage> = emptyList(),
    val text: String = "",
    /** The own message whose actions are shown. */
    val selected: Long? = null,
    /** The own message being edited in the composer (ADR 0019). */
    val editing: Message? = null,
    /** An edit came too late: more than 24 hours since sending (409). */
    val editTooLate: Boolean = false,
    /** The message the user is asked to confirm deleting. */
    val deleting: Message? = null,
    /** The user is asked to confirm "Удалить у себя". */
    val askingHide: Boolean = false,
    /** The chat was deleted for this user: the screen closes. */
    val hidden: Boolean = false,
    /** Too many messages a minute (429). */
    val tooFast: Boolean = false,
    val error: String? = null,
) {
    val hasOlder: Boolean get() = olderCursor != null
    val canSend: Boolean get() = conversation?.canSend == true && text.isNotBlank()
}

/** US-17/US-18: one chat. Messages arrive over Centrifugo, or by polling while realtime is down. */
class ChatViewModel(
    private val client: AydaClient,
    private val realtime: Realtime,
    private val conversationId: String,
    /** Called after the chat was marked read, so the chat list can clear its badge at once. */
    private val onRead: (conversationId: String, lastReadMessageId: Long) -> Unit = { _, _ -> },
    /** Called after the chat was deleted for this user, so the chat list drops it at once. */
    private val onHidden: (conversationId: String) -> Unit = {},
) : ViewModel() {
    private val mutableState = MutableStateFlow(ChatState())
    val state: StateFlow<ChatState> = mutableState.asStateFlow()

    private var readUpTo = 0L

    init {
        refresh()
        viewModelScope.launch {
            realtime.events.collect { event ->
                when (event) {
                    is LiveEvent.MessageCreated ->
                        if (event.message.conversationId == conversationId) {
                            upsert(event.message)
                            markRead()
                        }
                    is LiveEvent.MessageUpdated ->
                        if (event.message.conversationId == conversationId) upsert(event.message)
                    is LiveEvent.MessageDeleted ->
                        if (event.conversationId == conversationId) remove(event.messageId)
                    LiveEvent.Resync -> refresh()
                    else -> {}
                }
            }
        }
        viewModelScope.pollWhileOffline(realtime, POLL) { loadNewest() }
    }

    fun refresh() {
        viewModelScope.launch { loadConversation() }
        viewModelScope.launch { loadNewest() }
    }

    fun loadOlder() {
        val cursor = state.value.olderCursor ?: return
        if (state.value.loadingOlder) return
        mutableState.update { it.copy(loadingOlder = true) }
        viewModelScope.launch {
            val page = apiCall { client.chat.listMessages(conversationId, cursor, PAGE) }
            mutableState.update { s ->
                if (page !is ApiResult.Ok) return@update s.copy(loadingOlder = false, error = page.errorText())
                val known = s.messages.mapTo(HashSet()) { it.id }
                val older =
                    page.value.items
                        .filter { it.id !in known }
                        .reversed()
                s.copy(messages = older + s.messages, olderCursor = page.value.nextCursor, loadingOlder = false)
            }
        }
    }

    fun onTextChange(text: String) = mutableState.update { it.copy(text = text.take(MAX_LENGTH)) }

    fun send() {
        val text = state.value.text.trim()
        if (text.isEmpty() || state.value.conversation?.canSend != true) return
        state.value.editing?.let { target ->
            saveEdit(target, text)
            return
        }
        mutableState.update { it.copy(text = "", tooFast = false) }
        deliver(PendingMessage(newClientId(), text))
    }

    /** ADR 0019: sends a voice message or a circle; the server re-encodes it before anyone plays it. */
    fun sendRecording(
        kind: ChatUploadInput.Kind,
        bytes: ByteArray,
    ) {
        if (bytes.isEmpty() || state.value.conversation?.canSend != true) return
        mutableState.update { it.copy(tooFast = false) }
        deliver(PendingMessage(newClientId(), "", recording = Recording(kind, bytes)))
    }

    /** Sends a failed message again with the same client id, so the server never saves it twice. */
    fun retry(message: PendingMessage) = deliver(message)

    fun select(message: Message) =
        mutableState.update {
            it.copy(
                selected =
                    if (it.selected ==
                        message.id
                    ) {
                        null
                    } else {
                        message.id
                    },
            )
        }

    /** Whether an own message can still be edited: up to 24 hours after sending. */
    fun canEdit(
        message: Message,
        now: Instant = Clock.System.now(),
    ): Boolean = now - message.createdAt < EDIT_WINDOW

    fun startEdit(message: Message) =
        mutableState.update { it.copy(editing = message, text = message.text, selected = null, editTooLate = false) }

    fun cancelEdit() = mutableState.update { it.copy(editing = null, text = "") }

    private fun saveEdit(
        target: Message,
        text: String,
    ) {
        mutableState.update { it.copy(editing = null, text = "") }
        if (text == target.text) return
        viewModelScope.launch {
            val edited = apiCall { client.chat.editMessage(conversationId, target.id, MessageEdit(text)) }
            when {
                edited is ApiResult.Ok -> upsert(edited.value)
                edited is ApiResult.Failed && edited.problem.status == 409 ->
                    mutableState.update { it.copy(editTooLate = true) }
                else -> mutableState.update { it.copy(error = edited.errorText()) }
            }
        }
    }

    fun askDelete(message: Message) = mutableState.update { it.copy(deleting = message, selected = null) }

    fun cancelDelete() = mutableState.update { it.copy(deleting = null) }

    /** Deletes the message for everyone in the chat. */
    fun confirmDelete() {
        val message = state.value.deleting ?: return
        mutableState.update { it.copy(deleting = null) }
        viewModelScope.launch {
            when (val removed = apiCall({ client.chat.deleteMessage(conversationId, message.id) }) {}) {
                is ApiResult.Ok -> remove(message.id)
                else -> mutableState.update { it.copy(error = removed.errorText()) }
            }
        }
    }

    fun askHide() = mutableState.update { it.copy(askingHide = true) }

    fun cancelHide() = mutableState.update { it.copy(askingHide = false) }

    /** "Удалить у себя": the chat leaves this user's list; the others keep it. */
    fun confirmHide() {
        mutableState.update { it.copy(askingHide = false) }
        viewModelScope.launch {
            when (val hidden = apiCall({ client.chat.hideConversation(conversationId) }) {}) {
                is ApiResult.Ok -> {
                    mutableState.update { it.copy(hidden = true) }
                    onHidden(conversationId)
                }
                else -> mutableState.update { it.copy(error = hidden.errorText()) }
            }
        }
    }

    fun dismissError() = mutableState.update { it.copy(error = null) }

    private fun deliver(message: PendingMessage) {
        mutableState.update { s ->
            s.copy(pending = s.pending.filterNot { it.clientId == message.clientId } + message.copy(failed = false))
        }
        viewModelScope.launch {
            var attachmentId = message.attachmentId
            val recording = message.recording
            if (recording != null && attachmentId == null) {
                when (val uploaded = client.uploadRecording(conversationId, recording.kind, recording.bytes)) {
                    is ApiResult.Ok -> {
                        attachmentId = uploaded.value
                        mutableState.update { s ->
                            s.copy(
                                pending =
                                    s.pending.map {
                                        if (it.clientId ==
                                            message.clientId
                                        ) {
                                            it.copy(attachmentId = uploaded.value)
                                        } else {
                                            it
                                        }
                                    },
                            )
                        }
                    }
                    else -> {
                        failed(message, uploaded)
                        return@launch
                    }
                }
            }
            val input =
                if (attachmentId != null) {
                    MessageInput(clientId = message.clientId, attachmentId = attachmentId)
                } else {
                    MessageInput(clientId = message.clientId, text = message.text)
                }
            when (val sent = apiCall { client.chat.sendMessage(conversationId, input) }) {
                is ApiResult.Ok -> upsert(sent.value)
                else -> failed(message, sent)
            }
        }
    }

    private fun failed(
        message: PendingMessage,
        result: ApiResult<*>,
    ) {
        mutableState.update { s ->
            s.copy(
                pending = s.pending.map { if (it.clientId == message.clientId) it.copy(failed = true) else it },
                tooFast = result is ApiResult.Failed && result.problem.status == 429,
            )
        }
        // 403: the friendship was removed and the chat is now read-only.
        if (result is ApiResult.Failed && result.problem.status == 403) {
            viewModelScope.launch { loadConversation() }
        }
    }

    /** Adds a message or replaces the same one (by id, or by client id for the user's own). */
    private fun upsert(message: Message) =
        mutableState.update { s ->
            val same = { m: Message ->
                m.id == message.id ||
                    (message.clientId != null && m.clientId == message.clientId)
            }
            val messages =
                if (s.messages.any(same)) {
                    s.messages.map {
                        if (same(it)) message else it
                    }
                } else {
                    (s.messages + message).sortedBy { it.id }
                }
            s.copy(messages = messages, pending = s.pending.filterNot { it.clientId == message.clientId })
        }

    private fun remove(messageId: Long) =
        mutableState.update { s ->
            s.copy(
                messages = s.messages.filterNot { it.id == messageId },
                selected =
                    s.selected.takeIf {
                        it !=
                            messageId
                    },
            )
        }

    private suspend fun loadConversation() {
        val loaded = apiCall { client.chat.getConversation(conversationId) }
        mutableState.update {
            if (loaded is ApiResult.Ok) it.copy(conversation = loaded.value) else it.copy(error = loaded.errorText())
        }
        if (loaded is ApiResult.Ok) readUpTo = maxOf(readUpTo, loaded.value.lastReadMessageId ?: 0)
    }

    /** Reloads the newest page and keeps the older messages already shown. */
    private suspend fun loadNewest() {
        val page = apiCall { client.chat.listMessages(conversationId, null, PAGE) }
        mutableState.update { s ->
            if (page !is ApiResult.Ok) return@update if (s.loaded) s else s.copy(error = page.errorText())
            val newest = page.value.items.reversed()
            val oldestShown = newest.firstOrNull()?.id
            val older = if (oldestShown == null) emptyList() else s.messages.filter { it.id < oldestShown }
            val confirmed = newest.mapNotNullTo(HashSet()) { it.clientId }
            s.copy(
                messages = older + newest,
                loaded = true,
                // Paging further back starts from the first page's cursor only the first time.
                olderCursor = if (s.loaded) s.olderCursor else page.value.nextCursor,
                pending = s.pending.filterNot { it.clientId in confirmed },
            )
        }
        markRead()
    }

    private suspend fun markRead() {
        val newest =
            state.value.messages
                .lastOrNull()
                ?.id ?: return
        if (newest <= readUpTo) return
        readUpTo = newest
        onRead(conversationId, newest)
        apiCall({ client.chat.markConversationRead(conversationId, MarkConversationReadRequest(newest)) }) {}
    }

    companion object {
        const val PAGE = 30
        const val MAX_LENGTH = 2000
        val EDIT_WINDOW = 24.hours
        val POLL = 5.seconds

        @OptIn(ExperimentalUuidApi::class)
        private fun newClientId(): String = Uuid.random().toString()
    }
}
