package app.ayda.shared.social

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.ayda.api.apis.SocialApi.WeekGetLadder
import app.ayda.api.models.Friend
import app.ayda.api.models.Invite
import app.ayda.api.models.Ladder
import app.ayda.shared.ApiResult
import app.ayda.shared.AydaClient
import app.ayda.shared.apiCall
import app.ayda.shared.errorText
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class FriendsState(
    val week: WeekGetLadder = WeekGetLadder.current,
    val ladder: Ladder? = null,
    val friends: List<Friend> = emptyList(),
    val inviting: Boolean = false,
    /** Set after an invite link was handed to the share sheet. */
    val inviteShared: Boolean = false,
    /** The friend the user is asked to confirm removing. */
    val removing: Friend? = null,
    val error: String? = null,
) {
    /** Only the user is on the ladder: nobody to compete with yet. */
    val alone: Boolean get() = ladder != null && ladder.propertyEntries.size <= 1
}

/** US-12/US-16: the weekly ladder among friends, the friends list and invite links. */
class FriendsViewModel(
    private val client: AydaClient,
) : ViewModel() {
    private val mutableState = MutableStateFlow(FriendsState())
    val state: StateFlow<FriendsState> = mutableState.asStateFlow()

    init {
        refresh()
    }

    fun refresh() {
        viewModelScope.launch { loadLadder(state.value.week) }
        viewModelScope.launch { loadFriends() }
    }

    fun selectWeek(week: WeekGetLadder) {
        if (week == state.value.week) return
        mutableState.update { it.copy(week = week, ladder = null) }
        viewModelScope.launch { loadLadder(week) }
    }

    /** Creates a reusable 7-day link and hands it to [share] (the system share sheet). */
    fun invite(share: (Invite) -> Unit) {
        if (state.value.inviting) return
        mutableState.update { it.copy(inviting = true, error = null) }
        viewModelScope.launch {
            when (val created = apiCall { client.social.createInvite() }) {
                is ApiResult.Ok -> {
                    share(created.value)
                    mutableState.update { it.copy(inviting = false, inviteShared = true) }
                }
                else -> mutableState.update { it.copy(inviting = false, error = created.errorText()) }
            }
        }
    }

    fun askRemove(friend: Friend) = mutableState.update { it.copy(removing = friend) }

    fun cancelRemove() = mutableState.update { it.copy(removing = null) }

    /** The former friend stops seeing the user's posts at once. */
    fun confirmRemove() {
        val friend = state.value.removing ?: return
        mutableState.update { it.copy(removing = null) }
        viewModelScope.launch {
            when (val removed = apiCall({ client.social.removeFriend(friend.id) }) {}) {
                is ApiResult.Ok -> {
                    mutableState.update { s -> s.copy(friends = s.friends.filterNot { it.id == friend.id }) }
                    loadLadder(state.value.week)
                }
                else -> mutableState.update { it.copy(error = removed.errorText()) }
            }
        }
    }

    private suspend fun loadLadder(week: WeekGetLadder) {
        val loaded = apiCall { client.social.getLadder(week) }
        mutableState.update {
            when {
                it.week != week -> it
                loaded is ApiResult.Ok -> it.copy(ladder = loaded.value)
                else -> it.copy(error = loaded.errorText())
            }
        }
    }

    private suspend fun loadFriends() {
        val loaded = apiCall { client.social.listFriends() }
        mutableState.update {
            if (loaded is ApiResult.Ok) it.copy(friends = loaded.value.items) else it.copy(error = loaded.errorText())
        }
    }
}
