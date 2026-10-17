package app.ayda.shared.onboarding

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.ayda.api.models.AcceptConsentRequest
import app.ayda.api.models.Me
import app.ayda.shared.ApiResult
import app.ayda.shared.AydaClient
import app.ayda.shared.apiCall
import app.ayda.shared.errorText
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class ConsentState(
    val agreed: Boolean = false,
    val busy: Boolean = false,
    val error: String? = null,
) {
    val canContinue: Boolean get() = agreed && !busy
}

/** The personal data consent shown before anything else (152-FZ). */
class ConsentViewModel(
    private val client: AydaClient,
    private val version: String,
    private val onMeChanged: (Me) -> Unit,
) : ViewModel() {
    private val mutableState = MutableStateFlow(ConsentState())
    val state: StateFlow<ConsentState> = mutableState.asStateFlow()

    fun onAgreedChange(value: Boolean) = mutableState.update { it.copy(agreed = value, error = null) }

    fun accept() {
        if (!state.value.canContinue) return
        mutableState.update { it.copy(busy = true, error = null) }
        viewModelScope.launch {
            val accepted = apiCall({ client.profile.acceptConsent(AcceptConsentRequest(version)) }) {}
            val error =
                if (accepted !is ApiResult.Ok) {
                    accepted.errorText()
                } else {
                    when (val me = apiCall { client.profile.getMe() }) {
                        is ApiResult.Ok -> null.also { onMeChanged(me.value) }
                        else -> me.errorText()
                    }
                }
            mutableState.update { it.copy(busy = false, error = error) }
        }
    }
}
