package app.ayda.shared.onboarding

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.ayda.api.models.City
import app.ayda.api.models.Goal
import app.ayda.api.models.GoalSelection
import app.ayda.api.models.Habit
import app.ayda.api.models.HabitCreate
import app.ayda.api.models.HabitDirection
import app.ayda.api.models.Me
import app.ayda.api.models.ProfileUpdate
import app.ayda.api.models.Reminders
import app.ayda.api.models.Theme
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
import kotlin.time.Duration.Companion.milliseconds

enum class OnboardingStep(
    val skippable: Boolean,
) {
    /** Only for users without a name, such as a first sign-in by email. */
    Name(skippable = false),
    City(skippable = false),
    Goals(skippable = true),
    Habits(skippable = true),
    Reminders(skippable = true),
    Theme(skippable = false),
}

data class OnboardingState(
    val me: Me,
    val steps: List<OnboardingStep>,
    val index: Int = 0,
    val name: String = me.firstName,
    val cityQuery: String = "",
    val cities: List<City> = emptyList(),
    val searching: Boolean = false,
    val goals: List<Goal> = emptyList(),
    val selectedGoals: List<String> = emptyList(),
    val habits: List<Habit> = emptyList(),
    val reminders: Reminders = me.reminders,
    val busy: Boolean = false,
    val error: String? = null,
) {
    val step: OnboardingStep get() = steps[index]
    val isLast: Boolean get() = index == steps.lastIndex

    val ready: Boolean
        get() =
            !busy &&
                when (step) {
                    OnboardingStep.Name -> name.trim().isNotEmpty()
                    OnboardingStep.City -> me.city != null
                    else -> true
                }
}

/**
 * US-02 on native apps, the same steps as the Mini App plus a name for email users.
 * Every change the server confirms goes to [onMeChanged], so the app theme and the
 * session follow; the last step marks onboarding finished.
 */
class OnboardingViewModel(
    private val client: AydaClient,
    me: Me,
    private val onMeChanged: (Me) -> Unit,
) : ViewModel() {
    private val mutableState =
        MutableStateFlow(
            OnboardingState(
                me = me,
                steps = OnboardingStep.entries.filter { it != OnboardingStep.Name || me.firstName.isBlank() },
            ),
        )
    val state: StateFlow<OnboardingState> = mutableState.asStateFlow()

    private var search: Job? = null

    init {
        viewModelScope.launch {
            (apiCall { client.reference.listGoals() } as? ApiResult.Ok)?.let { goals ->
                mutableState.update { it.copy(goals = goals.value.items) }
            }
        }
        viewModelScope.launch {
            (apiCall { client.profile.listMyGoals() } as? ApiResult.Ok)?.let { mine ->
                mutableState.update { it.copy(selectedGoals = mine.value.goalCodes.toList()) }
            }
        }
        viewModelScope.launch {
            (apiCall { client.profile.listMyHabits() } as? ApiResult.Ok)?.let { habits ->
                mutableState.update { it.copy(habits = habits.value.items) }
            }
        }
    }

    fun onNameChange(value: String) = mutableState.update { it.copy(name = value.take(NAME_MAX), error = null) }

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
            viewModelScope.launch {
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

    fun pickCity(city: City) =
        saveProfile(ProfileUpdate(cityId = city.id)) {
            it.copy(cityQuery = "", cities = emptyList())
        }

    fun toggleGoal(code: String) =
        mutableState.update {
            val selected = it.selectedGoals
            when {
                code in selected -> it.copy(selectedGoals = selected - code)
                selected.size >= GOALS_MAX -> it
                else -> it.copy(selectedGoals = selected + code)
            }
        }

    fun addHabit(
        direction: HabitDirection,
        text: String,
    ) {
        val clean = text.trim().take(HABIT_MAX)
        if (clean.isEmpty()) return
        busy {
            when (val added = apiCall { client.profile.addMyHabit(HabitCreate(direction, clean)) }) {
                is ApiResult.Ok -> mutableState.update { it.copy(habits = it.habits + added.value) }
                else -> fail(added)
            }
        }
    }

    fun removeHabit(habit: Habit) =
        busy {
            when (val removed = apiCall({ client.profile.deleteMyHabit(habit.id) }) {}) {
                is ApiResult.Ok -> mutableState.update { it.copy(habits = it.habits - habit) }
                else -> fail(removed)
            }
        }

    /** `null` turns the reminder off. */
    fun setMorning(time: String?) = mutableState.update { it.copy(reminders = it.reminders.copy(morningAt = time)) }

    fun setEvening(time: String?) = mutableState.update { it.copy(reminders = it.reminders.copy(eveningAt = time)) }

    fun pickTheme(theme: Theme) = saveProfile(ProfileUpdate(theme = theme))

    fun back() = mutableState.update { if (it.index > 0) it.copy(index = it.index - 1, error = null) else it }

    fun skip() {
        if (!state.value.step.skippable) return
        busy { advance() }
    }

    /** Saves what the current step collected, then moves on (or finishes on the last step). */
    fun next() {
        val current = state.value
        if (!current.ready) return
        busy {
            val saved: ApiResult<*> =
                when (current.step) {
                    OnboardingStep.Name -> updateProfile(ProfileUpdate(firstName = current.name.trim()))
                    OnboardingStep.Goals ->
                        apiCall({ client.profile.setMyGoals(GoalSelection(current.selectedGoals.toSet())) }) {}
                    OnboardingStep.Reminders -> updateProfile(ProfileUpdate(reminders = current.reminders))
                    else -> ApiResult.Ok(Unit)
                }
            if (saved !is ApiResult.Ok) return@busy fail(saved)
            advance()
        }
    }

    private suspend fun advance() {
        val current = state.value
        if (!current.isLast) {
            mutableState.update { it.copy(index = it.index + 1, error = null) }
            return
        }
        when (val done = apiCall { client.profile.completeOnboarding() }) {
            is ApiResult.Ok -> changed(done.value)
            else -> fail(done)
        }
    }

    private fun saveProfile(
        update: ProfileUpdate,
        alsoUpdate: (OnboardingState) -> OnboardingState = { it },
    ) = busy {
        when (val saved = updateProfile(update)) {
            is ApiResult.Ok -> mutableState.update(alsoUpdate)
            else -> fail(saved)
        }
    }

    private suspend fun updateProfile(update: ProfileUpdate): ApiResult<Me> {
        val saved = apiCall { client.profile.updateProfile(update) }
        if (saved is ApiResult.Ok) changed(saved.value)
        return saved
    }

    private fun changed(me: Me) {
        mutableState.update { it.copy(me = me) }
        onMeChanged(me)
    }

    private fun busy(block: suspend () -> Unit) {
        if (state.value.busy) return
        mutableState.update { it.copy(busy = true, error = null) }
        viewModelScope.launch {
            block()
            mutableState.update { it.copy(busy = false) }
        }
    }

    private fun fail(result: ApiResult<*>) = mutableState.update { it.copy(error = result.errorText()) }

    private companion object {
        const val NAME_MAX = 64
        const val HABIT_MAX = 100
        const val GOALS_MAX = 5
        val SEARCH_PAUSE = 300.milliseconds
    }
}
