package app.ayda.shared.profile

import app.ayda.api.models.City
import app.ayda.api.models.Habit
import app.ayda.api.models.HabitCreate
import app.ayda.api.models.HabitDirection
import app.ayda.api.models.Interest
import app.ayda.api.models.InterestSelection
import app.ayda.api.models.Me
import app.ayda.api.models.ProfileUpdate
import app.ayda.api.models.Reminders
import app.ayda.api.models.Theme
import app.ayda.shared.ApiResult
import app.ayda.shared.AydaClient
import app.ayda.shared.apiCall
import app.ayda.shared.errorText
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlin.time.Duration.Companion.milliseconds

/** What the profile editors show: city search, interests, own habits and reminder times. */
data class EditorState(
    val cityQuery: String = "",
    val cities: List<City> = emptyList(),
    val searching: Boolean = false,
    val interests: List<Interest> = emptyList(),
    val selectedInterests: List<String> = emptyList(),
    val interestTags: List<String> = emptyList(),
    val habits: List<Habit> = emptyList(),
    val reminders: Reminders,
    val busy: Boolean = false,
    val error: String? = null,
) {
    val interestLimitReached: Boolean get() = selectedInterests.size >= INTERESTS_MAX
    val tagLimitReached: Boolean get() = interestTags.size >= TAGS_MAX

    companion object {
        const val INTERESTS_MAX = 8
        const val TAGS_MAX = 5
        const val TAG_MAX = 30
    }
}

/**
 * The editing logic shared by onboarding and the profile screen. Lives in its owner's
 * [scope]; every profile change the server confirms goes to [onMeChanged].
 */
class ProfileEditor(
    private val client: AydaClient,
    private val scope: CoroutineScope,
    me: Me,
    private val onMeChanged: (Me) -> Unit,
) {
    private val mutableState = MutableStateFlow(EditorState(reminders = me.reminders))
    val state: StateFlow<EditorState> = mutableState.asStateFlow()

    private var search: Job? = null

    /** Loads the interest catalog and the user's interests and habits. */
    fun load() {
        scope.launch {
            (apiCall { client.reference.listInterests() } as? ApiResult.Ok)?.let { interests ->
                mutableState.update { it.copy(interests = interests.value.items) }
            }
        }
        scope.launch {
            (apiCall { client.profile.listMyInterests() } as? ApiResult.Ok)?.let { mine ->
                mutableState.update {
                    it.copy(selectedInterests = mine.value.codes.toList(), interestTags = mine.value.tags.toList())
                }
            }
        }
        scope.launch {
            (apiCall { client.profile.listMyHabits() } as? ApiResult.Ok)?.let { habits ->
                mutableState.update { it.copy(habits = habits.value.items) }
            }
        }
    }

    /** Searches after a short pause in typing; two letters at least. */
    fun onCityQueryChange(value: String) {
        mutableState.update { it.copy(cityQuery = value, error = null) }
        search?.cancel()
        val query = value.trim()
        if (query.length < 2) {
            mutableState.update { it.copy(cities = emptyList(), searching = false) }
            return
        }
        search =
            scope.launch {
                delay(SEARCH_PAUSE)
                mutableState.update { it.copy(searching = true) }
                val found = apiCall { client.reference.searchCities(query = query) }
                mutableState.update {
                    when (found) {
                        is ApiResult.Ok -> it.copy(cities = found.value.items, searching = false)
                        else -> it.copy(searching = false, error = found.errorText())
                    }
                }
            }
    }

    fun pickCity(
        city: City,
        then: () -> Unit = {},
    ) = busy {
        if (updateProfile(ProfileUpdate(cityId = city.id)) is ApiResult.Ok) {
            mutableState.update { it.copy(cityQuery = "", cities = emptyList()) }
            then()
        }
    }

    fun toggleInterest(code: String) =
        mutableState.update {
            val selected = it.selectedInterests
            when {
                code in selected -> it.copy(selectedInterests = selected - code)
                it.interestLimitReached -> it
                else -> it.copy(selectedInterests = selected + code)
            }
        }

    /** Adds one of the user's own words; blank, repeated and over-limit words are ignored. */
    fun addInterestTag(text: String) {
        val clean = text.trim().lowercase().take(EditorState.TAG_MAX)
        mutableState.update {
            if (clean.isEmpty() ||
                clean in it.interestTags ||
                it.tagLimitReached
            ) {
                it
            } else {
                it.copy(interestTags = it.interestTags + clean)
            }
        }
    }

    fun removeInterestTag(tag: String) = mutableState.update { it.copy(interestTags = it.interestTags - tag) }

    suspend fun saveInterests(): ApiResult<Unit> =
        report(
            apiCall({
                client.profile.setMyInterests(
                    InterestSelection(state.value.selectedInterests.toSet(), state.value.interestTags),
                )
            }) {},
        )

    fun addHabit(
        direction: HabitDirection,
        text: String,
    ) {
        val clean = text.trim().take(HABIT_MAX)
        if (clean.isEmpty()) return
        busy {
            val added = report(apiCall { client.profile.addMyHabit(HabitCreate(direction, clean)) })
            if (added is ApiResult.Ok) mutableState.update { it.copy(habits = it.habits + added.value) }
        }
    }

    fun removeHabit(habit: Habit) =
        busy {
            if (report(apiCall({ client.profile.deleteMyHabit(habit.id) }) {}) is ApiResult.Ok) {
                mutableState.update { it.copy(habits = it.habits - habit) }
            }
        }

    /** `null` turns the reminder off. */
    fun setMorning(time: String?) = mutableState.update { it.copy(reminders = it.reminders.copy(morningAt = time)) }

    fun setEvening(time: String?) = mutableState.update { it.copy(reminders = it.reminders.copy(eveningAt = time)) }

    suspend fun saveReminders(): ApiResult<Me> = updateProfile(ProfileUpdate(reminders = state.value.reminders))

    fun pickTheme(theme: Theme) = busy { updateProfile(ProfileUpdate(theme = theme)) }

    suspend fun updateProfile(update: ProfileUpdate): ApiResult<Me> {
        val saved = report(apiCall { client.profile.updateProfile(update) })
        if (saved is ApiResult.Ok) onMeChanged(saved.value)
        return saved
    }

    fun clearError() = mutableState.update { it.copy(error = null) }

    private fun <T> report(result: ApiResult<T>): ApiResult<T> {
        mutableState.update { it.copy(error = if (result is ApiResult.Ok) null else result.errorText()) }
        return result
    }

    private fun busy(block: suspend () -> Unit) {
        if (state.value.busy) return
        mutableState.update { it.copy(busy = true, error = null) }
        scope.launch {
            try {
                block()
            } finally {
                mutableState.update { it.copy(busy = false) }
            }
        }
    }

    private companion object {
        const val HABIT_MAX = 100
        val SEARCH_PAUSE = 300.milliseconds
    }
}
