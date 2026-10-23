package app.ayda.shared.coop

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.ayda.api.infrastructure.HttpResponse
import app.ayda.api.models.Coop
import app.ayda.api.models.CoopStatus
import app.ayda.api.models.CreateCoopRequest
import app.ayda.api.models.Friend
import app.ayda.api.models.OfferHandoffRequest
import app.ayda.api.models.SetCoopItemRequest
import app.ayda.shared.ApiResult
import app.ayda.shared.AydaClient
import app.ayda.shared.apiCall
import app.ayda.shared.errorText
import app.ayda.shared.realtime.LiveEvent
import app.ayda.shared.realtime.Realtime
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** Why accepting or declining an invitation failed. */
sealed interface AnswerError {
    /** The owner's day ended (410). */
    data object Over : AnswerError

    data object NotFound : AnswerError

    /** Accepting would be a fourth taken quest today. */
    data object DailyLimit : AnswerError

    data object AlreadyAnswered : AnswerError

    data class Other(
        val text: String,
    ) : AnswerError
}

/** Why ticking a list item or handing a part over failed (ADR 0010). */
sealed interface PartError {
    /** The part belongs to someone else now. */
    data object NotAssignee : PartError

    /** The part waits for an earlier one. */
    data object Locked : PartError

    data object Done : PartError

    /** An offer for this part is already waiting for an answer. */
    data object Pending : PartError

    /** The plan already has four people. */
    data object Full : PartError

    data object NotFound : PartError

    data class Other(
        val text: String,
    ) : PartError
}

internal fun ApiResult<*>.partError(): PartError =
    when {
        this !is ApiResult.Failed -> PartError.Other(errorText())
        problem.code == "not-part-assignee" -> PartError.NotAssignee
        problem.code == "part-locked" -> PartError.Locked
        problem.code == "part-done" -> PartError.Done
        problem.code == "handoff-pending" -> PartError.Pending
        problem.code == "coop-full" -> PartError.Full
        problem.status == 404 -> PartError.NotFound
        else -> PartError.Other(errorText())
    }

internal fun ApiResult<*>.answerError(): AnswerError =
    when {
        this !is ApiResult.Failed -> AnswerError.Other(errorText())
        problem.status == 410 -> AnswerError.Over
        problem.status == 404 -> AnswerError.NotFound
        problem.status == 409 && problem.code == "daily-limit-reached" -> AnswerError.DailyLimit
        problem.status == 409 -> AnswerError.AlreadyAnswered
        else -> AnswerError.Other(errorText())
    }

/** Accepts or declines the invitation. */
internal suspend fun AydaClient.answerCoop(
    id: String,
    accept: Boolean,
): ApiResult<Coop> = apiCall { if (accept) coop.acceptCoop(id) else coop.declineCoop(id) }

data class CoopsState(
    val coops: List<Coop> = emptyList(),
    val answering: String? = null,
    val error: AnswerError? = null,
) {
    /** Invitations waiting for the user's answer, shown on the Today screen. */
    val invites: List<Coop> get() = coops.filter { it.myStatus == CoopStatus.invited }
}

/**
 * US-18: the user's co-ops for the Today screen. [onDayChanged] reloads the day, since an accepted
 * invitation adds a quest and a finished co-op adds bonus points.
 */
class CoopsViewModel(
    private val client: AydaClient,
    private val realtime: Realtime,
    private val onDayChanged: () -> Unit = {},
) : ViewModel() {
    private val mutableState = MutableStateFlow(CoopsState())
    val state: StateFlow<CoopsState> = mutableState.asStateFlow()

    init {
        refresh()
        viewModelScope.launch {
            realtime.events.collect {
                if (it is LiveEvent.CoopUpdated || it == LiveEvent.Resync) {
                    load()
                    onDayChanged()
                }
            }
        }
    }

    fun refresh() {
        viewModelScope.launch { load() }
    }

    fun answer(
        id: String,
        accept: Boolean,
    ) {
        if (state.value.answering != null) return
        mutableState.update { it.copy(answering = id, error = null) }
        viewModelScope.launch {
            val answered = client.answerCoop(id, accept)
            mutableState.update { s ->
                when (answered) {
                    is ApiResult.Ok ->
                        s.copy(
                            answering = null,
                            coops =
                                s.coops.map {
                                    if (it.id ==
                                        id
                                    ) {
                                        answered.value
                                    } else {
                                        it
                                    }
                                },
                        )
                    else -> s.copy(answering = null, error = answered.answerError())
                }
            }
            if (answered is ApiResult.Ok && accept) onDayChanged()
            if (answered !is ApiResult.Ok) load()
        }
    }

    /** Keeps the list in step after a co-op was changed on its own screen. */
    fun updated(coop: Coop) =
        mutableState.update { s ->
            s.copy(
                coops =
                    if (s.coops.any { it.id == coop.id }) {
                        s.coops.map {
                            if (it.id ==
                                coop.id
                            ) {
                                coop
                            } else {
                                it
                            }
                        }
                    } else {
                        s.coops + coop
                    },
            )
        }

    private suspend fun load() {
        val loaded = apiCall { client.coop.listCoops() }
        if (loaded is ApiResult.Ok) mutableState.update { it.copy(coops = loaded.value.items) }
    }
}

data class CoopState(
    val coop: Coop? = null,
    val notFound: Boolean = false,
    val answering: Boolean = false,
    val error: AnswerError? = null,
    val loadError: String? = null,
    val partError: PartError? = null,
)

/** US-18: one co-op with its participants, the answer buttons and the way to the shared chat. */
class CoopViewModel(
    private val client: AydaClient,
    private val realtime: Realtime,
    private val coopId: String,
    private val onChanged: (Coop) -> Unit = {},
) : ViewModel() {
    private val mutableState = MutableStateFlow(CoopState())
    val state: StateFlow<CoopState> = mutableState.asStateFlow()

    init {
        refresh()
        viewModelScope.launch {
            realtime.events.collect {
                if ((it is LiveEvent.CoopUpdated && it.coopId == coopId) || it == LiveEvent.Resync) load()
            }
        }
    }

    fun refresh() {
        viewModelScope.launch { load() }
    }

    fun answer(accept: Boolean) {
        if (state.value.answering) return
        mutableState.update { it.copy(answering = true, error = null) }
        viewModelScope.launch {
            val answered = client.answerCoop(coopId, accept)
            mutableState.update {
                if (answered is ApiResult.Ok) {
                    it.copy(answering = false, coop = answered.value)
                } else {
                    it.copy(answering = false, error = answered.answerError())
                }
            }
            if (answered is ApiResult.Ok) onChanged(answered.value) else load()
        }
    }

    /** Ticks or unticks an item of a part the user does. */
    fun tick(
        partId: String,
        itemId: String,
        done: Boolean,
    ) = changePart { client.coop.setCoopItem(coopId, partId, itemId, SetCoopItemRequest(done)) }

    /** Offers a part to a friend who is in the plan. */
    fun offerHandoff(
        partId: String,
        friendId: String,
    ) = changePart { client.coop.offerHandoff(coopId, partId, OfferHandoffRequest(friendId)) }

    fun withdrawHandoff(partId: String) = changePart { client.coop.withdrawHandoff(coopId, partId) }

    /** Takes over a part offered to the user, or declines it. */
    fun answerHandoff(
        partId: String,
        accept: Boolean,
    ) = changePart {
        if (accept) client.coop.acceptHandoff(coopId, partId) else client.coop.declineHandoff(coopId, partId)
    }

    private fun changePart(call: suspend () -> HttpResponse<Coop>) {
        mutableState.update { it.copy(partError = null) }
        viewModelScope.launch {
            val changed = apiCall { call() }
            mutableState.update {
                if (changed is ApiResult.Ok) {
                    it.copy(coop = changed.value, partError = null)
                } else {
                    it.copy(partError = changed.partError())
                }
            }
            if (changed is ApiResult.Ok) onChanged(changed.value) else load()
        }
    }

    private suspend fun load() {
        val loaded = apiCall { client.coop.getCoop(coopId) }
        mutableState.update {
            when {
                loaded is ApiResult.Ok -> it.copy(coop = loaded.value, loadError = null)
                loaded is ApiResult.Failed && loaded.problem.status == 404 -> it.copy(notFound = true)
                else -> it.copy(loadError = loaded.errorText())
            }
        }
    }
}

data class CoopInviteState(
    val friends: List<Friend> = emptyList(),
    val loaded: Boolean = false,
    val picked: Set<String> = emptySet(),
    val creating: Boolean = false,
    val error: String? = null,
) {
    val canSend: Boolean get() = picked.isNotEmpty() && !creating
}

/** US-18: turn a taken quest into a co-op by inviting 1-3 friends. */
class CoopInviteViewModel(
    private val client: AydaClient,
    private val questId: String,
) : ViewModel() {
    private val mutableState = MutableStateFlow(CoopInviteState())
    val state: StateFlow<CoopInviteState> = mutableState.asStateFlow()

    init {
        viewModelScope.launch {
            val loaded = apiCall { client.social.listFriends() }
            mutableState.update {
                if (loaded is ApiResult.Ok) {
                    it.copy(friends = loaded.value.items, loaded = true)
                } else {
                    it.copy(error = loaded.errorText())
                }
            }
        }
    }

    /** Up to [MAX_FRIENDS]; a fourth pick is ignored. */
    fun toggle(friendId: String) =
        mutableState.update {
            when {
                friendId in it.picked -> it.copy(picked = it.picked - friendId)
                it.picked.size < MAX_FRIENDS -> it.copy(picked = it.picked + friendId)
                else -> it
            }
        }

    fun send(onCreated: (Coop) -> Unit) {
        val current = state.value
        if (!current.canSend) return
        mutableState.update { it.copy(creating = true, error = null) }
        viewModelScope.launch {
            val created = apiCall { client.coop.createCoop(questId, CreateCoopRequest(current.picked)) }
            mutableState.update {
                it.copy(
                    creating = false,
                    error = if (created is ApiResult.Ok) null else created.errorText(),
                )
            }
            if (created is ApiResult.Ok) onCreated(created.value)
        }
    }

    companion object {
        const val MAX_FRIENDS = 3
    }
}
