package app.ayda.shared.plans

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.ayda.api.models.Coop
import app.ayda.api.models.MeetupOffer
import app.ayda.api.models.MeetupPick
import app.ayda.shared.ApiResult
import app.ayda.shared.AydaClient
import app.ayda.shared.apiCall
import app.ayda.shared.errorText
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class MeetupState(
    val loading: Boolean = true,
    val offer: MeetupOffer? = null,
    val picking: Boolean = false,
    val error: String? = null,
)

/**
 * "Айда, организуй" (M5): the assistant reads the last messages of the chat once, when this screen
 * opens after an explicit tap; code returns the places. Choosing one creates the plan.
 */
class MeetupViewModel(
    private val client: AydaClient,
    private val conversationId: String,
) : ViewModel() {
    private val mutableState = MutableStateFlow(MeetupState())
    val state: StateFlow<MeetupState> = mutableState.asStateFlow()

    init {
        load()
    }

    fun load() {
        mutableState.update { MeetupState() }
        viewModelScope.launch {
            val loaded = apiCall { client.chat.suggestMeetup(conversationId) }
            mutableState.update {
                if (loaded is ApiResult.Ok) {
                    it.copy(loading = false, offer = loaded.value)
                } else {
                    it.copy(loading = false, error = loaded.errorText())
                }
            }
        }
    }

    /** Picks a venue from the offer, or the online activity when [venueId] is null. */
    fun pick(
        venueId: Long?,
        onCreated: (Coop) -> Unit,
    ) {
        val offer = state.value.offer ?: return
        val startsAt = offer.startsAt ?: return
        if (state.value.picking) return
        mutableState.update { it.copy(picking = true, error = null) }
        viewModelScope.launch {
            val activity = offer.activity.takeIf { venueId == null }
            val body = MeetupPick(startsAt = startsAt, venueId = venueId, activity = activity)
            val created = apiCall { client.chat.pickMeetup(conversationId, body) }
            mutableState.update {
                it.copy(picking = false, error = if (created is ApiResult.Ok) null else created.errorText())
            }
            if (created is ApiResult.Ok) onCreated(created.value)
        }
    }
}
