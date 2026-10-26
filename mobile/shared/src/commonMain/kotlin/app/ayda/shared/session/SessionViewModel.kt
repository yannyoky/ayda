package app.ayda.shared.session

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.ayda.api.models.Me
import app.ayda.shared.ApiResult
import app.ayda.shared.AydaClient
import app.ayda.shared.apiCall
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/** Which top-level screen the app shows. */
sealed interface SessionState {
    data object Loading : SessionState

    data object SignedOut : SessionState

    /** Signed in, but the profile could not be loaded; the app offers to retry. */
    data object Offline : SessionState

    data class SignedIn(
        val me: Me,
    ) : SessionState
}

/** Shared by Android and iOS: restores the session on launch and follows sign-in and sign-out. */
class SessionViewModel(
    private val client: AydaClient,
    /** Runs while the session is still valid, e.g. to stop pushes to this phone. */
    private val beforeSignOut: suspend () -> Unit = {},
) : ViewModel() {
    private val mutableState = MutableStateFlow<SessionState>(SessionState.Loading)
    val state: StateFlow<SessionState> = mutableState.asStateFlow()

    init {
        viewModelScope.launch {
            // The refresh token was rejected somewhere in the app: back to sign-in.
            client.signedOut.collect { mutableState.value = SessionState.SignedOut }
        }
        viewModelScope.launch {
            // A 409 may be `consent-required`: the profile then says which consent to show.
            client.conflicts.collect { recheckConsent() }
        }
        restore()
    }

    fun restore() {
        viewModelScope.launch {
            mutableState.value = SessionState.Loading
            if (!client.isSignedIn()) {
                mutableState.value = SessionState.SignedOut
                return@launch
            }
            mutableState.value =
                when (val result = apiCall { client.profile.getMe() }) {
                    is ApiResult.Ok -> SessionState.SignedIn(result.value)
                    is ApiResult.Offline -> SessionState.Offline
                    is ApiResult.Failed ->
                        if (client.isSignedIn()) SessionState.Offline else SessionState.SignedOut
                }
        }
    }

    private suspend fun recheckConsent() {
        val current = mutableState.value as? SessionState.SignedIn ?: return
        val fresh = (apiCall { client.profile.getMe() } as? ApiResult.Ok)?.value ?: return
        if (fresh.consentRequired != current.me.consentRequired) mutableState.value = SessionState.SignedIn(fresh)
    }

    fun onSignedIn(me: Me) {
        mutableState.value = SessionState.SignedIn(me)
    }

    /** After a profile change the screens show the fresh copy. */
    fun onProfileChanged(me: Me) = onSignedIn(me)

    fun signOut() {
        viewModelScope.launch {
            beforeSignOut()
            client.signOut()
            mutableState.value = SessionState.SignedOut
        }
    }
}
