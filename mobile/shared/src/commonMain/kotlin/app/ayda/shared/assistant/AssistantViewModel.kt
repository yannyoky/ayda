package app.ayda.shared.assistant

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.ayda.api.models.AssistantMessage
import app.ayda.api.models.AssistantMessageInput
import app.ayda.api.models.QuestState
import app.ayda.shared.ApiResult
import app.ayda.shared.AydaClient
import app.ayda.shared.apiCall
import app.ayda.shared.errorText
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class AssistantState(
    /** Oldest first. */
    val messages: List<AssistantMessage> = emptyList(),
    val loaded: Boolean = false,
    val messagesLeft: Int = 0,
    val text: String = "",
    /** The message on its way; the assistant is typing while it is set. */
    val waiting: String? = null,
    /** A message that got no answer and can be sent again. */
    val failed: String? = null,
    /** Quest ids taken from a card in this chat. */
    val taken: Set<String> = emptySet(),
    /** Places reported here as not working ("Не работает"). */
    val closedPlaces: Set<Long> = emptySet(),
    val error: String? = null,
) {
    val typing: Boolean get() = waiting != null
    val limitReached: Boolean get() = loaded && messagesLeft == 0
    val canSend: Boolean get() = text.isNotBlank() && !typing && !limitReached
    val showHints: Boolean get() = loaded && messages.size <= 2 && !typing && !limitReached
}

/**
 * The day chat with the assistant (ADR 0013): the check-in opens it and every quest of the day
 * has its own topic. Cards carry facts from code: places, recipes, a new quest to take.
 */
class AssistantViewModel(
    private val client: AydaClient,
    /** A quest of today, or null for the day topic. */
    val questId: String?,
    /** Called after a quest from a card was taken, so Today can refresh. */
    private val onQuestTaken: () -> Unit = {},
) : ViewModel() {
    private val mutableState = MutableStateFlow(AssistantState())
    val state: StateFlow<AssistantState> = mutableState.asStateFlow()

    init {
        refresh()
    }

    fun refresh() {
        viewModelScope.launch {
            val thread = apiCall { client.assistant.listAssistantMessages(questId) }
            mutableState.update {
                if (thread is ApiResult.Ok) {
                    it.copy(
                        messages = thread.value.items,
                        messagesLeft = thread.value.messagesLeft,
                        loaded = true,
                        error = null,
                    )
                } else {
                    it.copy(error = thread.errorText())
                }
            }
        }
    }

    fun onTextChange(text: String) = mutableState.update { it.copy(text = text.take(MAX_LENGTH)) }

    fun send() {
        val text = state.value.text.trim()
        if (text.isEmpty() || !state.value.canSend) return
        mutableState.update { it.copy(text = "") }
        deliver(text)
    }

    /** One of the ready questions under an empty chat. */
    fun ask(hint: String) {
        if (state.value.typing || state.value.limitReached) return
        deliver(hint)
    }

    fun retry() {
        val text = state.value.failed ?: return
        deliver(text)
    }

    private fun deliver(text: String) {
        mutableState.update { it.copy(waiting = text, failed = null, error = null) }
        viewModelScope.launch {
            val exchange =
                apiCall { client.assistant.sendAssistantMessage(AssistantMessageInput(text = text, questId = questId)) }
            mutableState.update {
                when {
                    exchange is ApiResult.Ok ->
                        it.copy(
                            messages = it.messages + exchange.value.sent + exchange.value.reply,
                            messagesLeft = exchange.value.messagesLeft,
                            waiting = null,
                        )
                    exchange is ApiResult.Failed && exchange.problem.status == 429 ->
                        it.copy(waiting = null, messagesLeft = 0)
                    else -> it.copy(waiting = null, failed = text)
                }
            }
        }
    }

    /** Takes the quest the assistant offered on a card. */
    fun take(questId: String) {
        viewModelScope.launch {
            val taken = apiCall { client.day.takeQuest(questId) }
            if (taken is ApiResult.Ok) {
                mutableState.update { it.copy(taken = it.taken + questId) }
                onQuestTaken()
            } else {
                mutableState.update { it.copy(error = taken.errorText()) }
            }
        }
    }

    /**
     * "Не работает" on a place card: the map knows opening hours, not a place closed for a while.
     * The server leaves it out of this user's picks, and everyone's once a second person reports it.
     */
    fun reportClosed(venueId: Long) {
        if (venueId in state.value.closedPlaces) return
        viewModelScope.launch {
            val reported = apiCall { client.events.reportVenueClosed(venueId) }
            mutableState.update {
                if (reported is ApiResult.Ok) {
                    it.copy(closedPlaces = it.closedPlaces + venueId)
                } else {
                    it.copy(error = reported.errorText())
                }
            }
        }
    }

    /** Whether a quest card can still be taken: a snapshot says offered, and it was not taken here. */
    fun canTake(
        questId: String,
        state: QuestState,
    ): Boolean = state == QuestState.offered && questId !in this.state.value.taken

    companion object {
        const val MAX_LENGTH = 1000
    }
}
