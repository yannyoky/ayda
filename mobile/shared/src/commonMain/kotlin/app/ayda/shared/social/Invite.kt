package app.ayda.shared.social

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.ayda.api.models.Friend
import app.ayda.shared.ApiResult
import app.ayda.shared.AydaClient
import app.ayda.shared.apiCall
import app.ayda.shared.errorText
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** An invite link `https://<domain>/i/<code>` (US-12, ADR 0009). */
object InviteLink {
    private val code = Regex("^[A-Za-z0-9_-]{10,64}$")

    /** The code in the path of a link, or null when the path is not an invite. */
    fun codeFrom(path: String?): String? {
        val parts = path.orEmpty().split('/').filter { it.isNotEmpty() }
        return parts.takeIf { it.size == 2 && it[0] == "i" }?.get(1)?.takeIf { code.matches(it) }
    }
}

sealed interface InviteState {
    data object Accepting : InviteState

    /** Friends now, or already were: accepting twice is fine. */
    data class Accepted(
        val friend: Friend,
    ) : InviteState

    /** The user opened their own link. */
    data object Own : InviteState

    data object Expired : InviteState

    data object Unknown : InviteState

    data class Failed(
        val text: String,
    ) : InviteState
}

/** Accepts the invite behind a link the app was opened with. */
class InviteViewModel(
    private val client: AydaClient,
    private val code: String,
) : ViewModel() {
    private val mutableState = MutableStateFlow<InviteState>(InviteState.Accepting)
    val state: StateFlow<InviteState> = mutableState.asStateFlow()

    init {
        accept()
    }

    fun accept() {
        mutableState.update { InviteState.Accepting }
        viewModelScope.launch {
            val accepted = apiCall { client.social.acceptInvite(code) }
            mutableState.update {
                when {
                    accepted is ApiResult.Ok -> InviteState.Accepted(accepted.value)
                    accepted is ApiResult.Failed && accepted.problem.status == 409 -> InviteState.Own
                    accepted is ApiResult.Failed && accepted.problem.status == 410 -> InviteState.Expired
                    accepted is ApiResult.Failed && accepted.problem.status == 404 -> InviteState.Unknown
                    else -> InviteState.Failed(accepted.errorText())
                }
            }
        }
    }
}
