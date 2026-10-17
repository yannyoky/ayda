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
) : ViewModel() {
    private val mutableState = MutableStateFlow<SessionState>(SessionState.Loading)
    val state: StateFlow<SessionState> = mutableState.asStateFlow()

    init {
        viewModelScope.launch {
            // The refresh token was rejected somewhere in the app: back to sign-in.
            client.signedOut.collect { mutableState.value = SessionState.SignedOut }
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

    fun onSignedIn(me: Me) {
        mutableState.value = SessionState.SignedIn(me)
    }

    /** After a profile change the screens show the fresh copy. */
    fun onProfileChanged(me: Me) = onSignedIn(me)

    fun signOut() {
        viewModelScope.launch {
            client.signOut()
            mutableState.value = SessionState.SignedOut
        }
    }
}
