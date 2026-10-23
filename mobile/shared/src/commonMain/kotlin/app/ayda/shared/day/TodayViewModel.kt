package app.ayda.shared.day

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.ayda.api.models.Category
import app.ayda.api.models.CheckinInput
import app.ayda.api.models.Day
import app.ayda.api.models.DayQuest
import app.ayda.api.models.Mood
import app.ayda.api.models.OwnQuestInput
import app.ayda.api.models.PoolStatus
import app.ayda.api.models.QuestState
import app.ayda.api.models.RejectReason
import app.ayda.api.models.ReplaceQuestRequest
import app.ayda.shared.ApiResult
import app.ayda.shared.AydaClient
import app.ayda.shared.apiCall
import app.ayda.shared.errorText
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlin.time.Duration
import kotlin.time.Duration.Companion.milliseconds

/** A quest the user words themselves (US-08); it is taken right away. */
data class OwnQuestDraft(
    val title: String = "",
    val category: Category = Category.project,
    val durationMin: Int = 30,
) {
    val canAdd: Boolean get() = title.isNotBlank()
}

/** One-off messages on the picker; the screen turns them into text. */
sealed interface Notice {
    data class ReplacementsLeft(
        val count: Int,
    ) : Notice

    data object NoAlternative : Notice

    data object NoReplacements : Notice

    data class Error(
        val text: String,
    ) : Notice
}

data class TodayState(
    val day: Day? = null,
    /** Set when today could not be loaded at all; the screen offers a retry. */
    val loadError: String? = null,
    val editingCheckin: Boolean = false,
    val checkinText: String = "",
    val mood: Mood = Mood.normal,
    /** Offered quests picked on the picker, in the order the user tapped them. */
    val selected: List<String> = emptyList(),
    /** The offered quest the user is about to swap ("Не сегодня"), waiting for a reason. */
    val replacing: DayQuest? = null,
    /** Non-null while the own quest sheet is open. */
    val ownQuest: OwnQuestDraft? = null,
    val notice: Notice? = null,
    val busy: Boolean = false,
    val error: String? = null,
    /** Set after a check-in with nothing taken yet: the next step is the picker. */
    val openPicker: Boolean = false,
) {
    val quests: List<DayQuest> get() = day?.quests.orEmpty()
    val offered: List<DayQuest> get() = quests.filter { it.state == QuestState.offered }

    /** Taken, completed and expired quests; replaced ones never come from the server. */
    val mine: List<DayQuest> get() = quests.filter { it.state != QuestState.offered }
    val left: Int get() = day?.let { (it.limits.maxTaken - it.limits.taken).coerceAtLeast(0) } ?: 0
    val chosen: List<String> get() = selected.filter { id -> offered.any { it.id == id } }
    val chosenPoints: Int get() = offered.filter { it.id in chosen }.sumOf { it.basePoints }
    val canReplace: Boolean get() = !busy && (day?.limits?.replacementsLeft ?: 0) > 0
    val showCheckinForm: Boolean get() = day != null && (day.checkin == null || editingCheckin)
    val generating: Boolean get() = day?.poolStatus == PoolStatus.generating
}

/**
 * The Today screen and the quest picker (US-05..US-08, US-19): morning check-in, the daily
 * pool, taking up to the limit, "not today" swaps with a reason and own quests.
 */
class TodayViewModel(
    private val client: AydaClient,
    private val pollEvery: Duration = POLL_EVERY,
) : ViewModel() {
    private val mutableState = MutableStateFlow(TodayState())
    val state: StateFlow<TodayState> = mutableState.asStateFlow()

    private var polling: Job? = null

    init {
        refresh()
    }

    /** Loads today again; the app calls it on resume because a day ends at 04:00 local time. */
    fun refresh() {
        viewModelScope.launch {
            when (val loaded = apiCall { client.day.getToday() }) {
                is ApiResult.Ok -> show(loaded.value)
                else -> mutableState.update { it.copy(loadError = if (it.day == null) loaded.errorText() else null) }
            }
        }
    }

    fun editCheckin() {
        val checkin = state.value.day?.checkin
        mutableState.update {
            it.copy(
                editingCheckin = true,
                checkinText = checkin?.text.orEmpty(),
                mood = checkin?.mood ?: Mood.normal,
                error = null,
            )
        }
    }

    /** The screen opened the picker after a check-in. */
    fun pickerOpened() = mutableState.update { it.copy(openPicker = false) }

    fun cancelCheckinEdit() = mutableState.update { it.copy(editingCheckin = false, error = null) }

    fun onCheckinTextChange(value: String) = mutableState.update { it.copy(checkinText = value.take(CHECKIN_MAX)) }

    fun onMoodChange(value: Mood) = mutableState.update { it.copy(mood = value) }

    /** The text is private and never logged; the server starts building the pool. */
    fun submitCheckin() =
        busy {
            val input = CheckinInput(mood = state.value.mood, text = state.value.checkinText.trim())
            val submitted = apiCall { client.day.submitCheckin(input) }
            if (submitted is ApiResult.Ok) {
                mutableState.update {
                    it.copy(editingCheckin = false, openPicker = submitted.value.limits.taken == 0)
                }
                show(submitted.value)
            } else {
                mutableState.update { it.copy(error = submitted.errorText()) }
            }
        }

    fun toggle(questId: String) =
        mutableState.update {
            val chosen = it.chosen
            val selected =
                when {
                    questId in chosen -> chosen - questId
                    chosen.size < it.left -> chosen + questId
                    else -> chosen
                }
            it.copy(selected = selected)
        }

    /** Takes the chosen quests one by one and stops at the first refusal, so its reason shows. */
    fun takeSelected(onTaken: () -> Unit) =
        busy {
            var failure: ApiResult<*>? = null
            for (id in state.value.chosen) {
                val taken = apiCall { client.day.takeQuest(id) }
                if (taken !is ApiResult.Ok) {
                    failure = taken
                    break
                }
            }
            reload()
            if (failure == null) {
                mutableState.update { it.copy(selected = emptyList(), notice = null) }
                onTaken()
            } else {
                mutableState.update { it.copy(notice = failure.toNotice()) }
            }
        }

    fun askReplace(quest: DayQuest) = mutableState.update { it.copy(replacing = quest) }

    fun cancelReplace() = mutableState.update { it.copy(replacing = null) }

    /** "Not today": swaps the quest for one of another category or duration. */
    fun replace(reason: RejectReason?) {
        val quest = state.value.replacing ?: return
        mutableState.update { it.copy(replacing = null, selected = it.selected - quest.id) }
        busy {
            val replaced = apiCall { client.day.replaceQuest(quest.id, ReplaceQuestRequest(reason)) }
            val notice =
                when (replaced) {
                    is ApiResult.Ok ->
                        if (replaced.value.replacement == null) {
                            Notice.NoAlternative
                        } else {
                            Notice.ReplacementsLeft(replaced.value.replacementsLeft)
                        }
                    is ApiResult.Failed ->
                        if (replaced.problem.status == CONFLICT) {
                            Notice.NoReplacements
                        } else {
                            Notice.Error(replaced.errorText())
                        }
                    is ApiResult.Offline -> Notice.Error(replaced.errorText())
                }
            mutableState.update { it.copy(notice = notice) }
            reload()
        }
    }

    fun dismissNotice() = mutableState.update { it.copy(notice = null) }

    fun openOwnQuest() = mutableState.update { it.copy(ownQuest = OwnQuestDraft(), error = null) }

    fun closeOwnQuest() = mutableState.update { it.copy(ownQuest = null, error = null) }

    fun editOwnQuest(change: (OwnQuestDraft) -> OwnQuestDraft) =
        mutableState.update {
            val draft = it.ownQuest ?: return@update it
            it.copy(ownQuest = change(draft).let { d -> d.copy(title = d.title.take(OWN_TITLE_MAX)) }, error = null)
        }

    fun addOwnQuest(onAdded: () -> Unit = {}) {
        val draft = state.value.ownQuest ?: return
        if (!draft.canAdd) return
        busy {
            val input = OwnQuestInput(draft.title.trim(), draft.category, draft.durationMin)
            val added = apiCall { client.day.addOwnQuest(input) }
            if (added is ApiResult.Ok) {
                mutableState.update { it.copy(ownQuest = null) }
                reload()
                onAdded()
            } else {
                val limit = added is ApiResult.Failed && added.problem.status == CONFLICT
                mutableState.update { it.copy(error = if (limit) LIMIT_REACHED else added.errorText()) }
            }
        }
    }

    private suspend fun reload() {
        val loaded = apiCall { client.day.getToday() }
        if (loaded is ApiResult.Ok) show(loaded.value)
    }

    private fun show(day: Day) {
        mutableState.update { it.copy(day = day, loadError = null) }
        if (day.poolStatus == PoolStatus.generating && polling?.isActive != true) {
            // The contract asks to poll every 1-2 s while the assistant builds the pool.
            polling =
                viewModelScope.launch {
                    while (state.value.generating) {
                        delay(pollEvery)
                        reload()
                    }
                }
        }
    }

    private fun ApiResult<*>.toNotice(): Notice =
        if (this is ApiResult.Failed && problem.status == CONFLICT) {
            Notice.Error(problem.message.ifBlank { LIMIT_REACHED })
        } else {
            Notice.Error(errorText())
        }

    private fun busy(block: suspend () -> Unit) {
        if (state.value.busy) return
        mutableState.update { it.copy(busy = true, error = null) }
        viewModelScope.launch {
            try {
                block()
            } finally {
                mutableState.update { it.copy(busy = false) }
            }
        }
    }

    companion object {
        const val CHECKIN_MAX = 1000
        const val OWN_TITLE_MAX = 120
        val DURATIONS = listOf(15, 30, 45, 60, 90)
        private val POLL_EVERY = 1500.milliseconds
        private const val CONFLICT = 409
        private const val LIMIT_REACHED = "Уже взято три квеста на сегодня"
    }
}
