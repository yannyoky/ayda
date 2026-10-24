package app.ayda.shared.onboarding

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.ayda.api.models.Me
import app.ayda.api.models.ProfileUpdate
import app.ayda.shared.ApiResult
import app.ayda.shared.AydaClient
import app.ayda.shared.apiCall
import app.ayda.shared.errorText
import app.ayda.shared.profile.ProfileEditor
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

enum class OnboardingStep(
    val skippable: Boolean,
) {
    /** Only for users without a name, such as a first sign-in by email. */
    Name(skippable = false),
    City(skippable = false),
    Interests(skippable = true),
    Habits(skippable = true),
    Reminders(skippable = true),
    Theme(skippable = false),
}

data class OnboardingState(
    val me: Me,
    val steps: List<OnboardingStep>,
    val index: Int = 0,
    val name: String = me.firstName,
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
 * The step contents are edited through [editor]; every change the server confirms goes
 * to [onMeChanged], so the app theme and the session follow. The last step marks
 * onboarding finished.
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

    val editor = ProfileEditor(client, viewModelScope, me, ::changed)

    init {
        editor.load()
    }

    fun onNameChange(value: String) = mutableState.update { it.copy(name = value.take(NAME_MAX), error = null) }

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
                    OnboardingStep.Name -> editor.updateProfile(ProfileUpdate(firstName = current.name.trim()))
                    OnboardingStep.Interests -> editor.saveInterests()
                    OnboardingStep.Reminders -> editor.saveReminders()
                    else -> ApiResult.Ok(Unit)
                }
            // The editor shows the error of its own calls.
            if (saved is ApiResult.Ok) advance()
        }
    }

    private suspend fun advance() {
        editor.clearError()
        val current = state.value
        if (!current.isLast) {
            mutableState.update { it.copy(index = it.index + 1, error = null) }
            return
        }
        when (val done = apiCall { client.profile.completeOnboarding() }) {
            is ApiResult.Ok -> changed(done.value)
            else -> mutableState.update { it.copy(error = done.errorText()) }
        }
    }

    private fun changed(me: Me) {
        mutableState.update { it.copy(me = me) }
        onMeChanged(me)
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

    private companion object {
        const val NAME_MAX = 64
    }
}
