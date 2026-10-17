package app.ayda.shared.profile

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.ayda.api.models.Me
import app.ayda.api.models.NotificationChannel
import app.ayda.api.models.ProfileUpdate
import app.ayda.api.models.SignInIdentity
import app.ayda.api.models.StartEmailSignInRequest
import app.ayda.api.models.VerifyEmailSignInRequest
import app.ayda.shared.ApiResult
import app.ayda.shared.AydaClient
import app.ayda.shared.apiCall
import app.ayda.shared.auth.SignIn
import app.ayda.shared.errorText
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** Linking an email: enter the address, then the code from the letter. */
data class EmailLink(
    val email: String = "",
    val code: String = "",
    val codeSent: Boolean = false,
)

data class ProfileState(
    val me: Me,
    val name: String = me.firstName,
    val identities: List<SignInIdentity> = emptyList(),
    /** Non-null while the user links an email. */
    val emailLink: EmailLink? = null,
    /** Set while waiting for the user to confirm linking in the bot. */
    val telegramUrl: String? = null,
    val confirmDeletion: Boolean = false,
    val busy: Boolean = false,
    val error: String? = null,
) {
    val canSaveName: Boolean get() = !busy && name.trim().isNotEmpty() && name.trim() != me.firstName
    val hasEmail: Boolean get() = identities.any { it.provider == SignInIdentity.Provider.email }
    val hasTelegram: Boolean get() = identities.any { it.provider == SignInIdentity.Provider.telegram }

    /** The server refuses to remove the last way to sign in; the screen hides the button. */
    val canUnlink: Boolean get() = identities.size > 1
}

/**
 * The profile (US-03, ADR 0009): name, theme, city, goals, habits, reminders, sign-in
 * methods, sign-out and account deletion. [onSignedOut] ends the session in the app.
 */
class ProfileViewModel(
    private val client: AydaClient,
    me: Me,
    private val onMeChanged: (Me) -> Unit,
    private val onSignedOut: () -> Unit,
) : ViewModel() {
    private val mutableState = MutableStateFlow(ProfileState(me))
    val state: StateFlow<ProfileState> = mutableState.asStateFlow()

    val editor = ProfileEditor(client, viewModelScope, me, ::changed)

    private val signIn = SignIn(client)
    private var telegram: Job? = null

    init {
        editor.load()
        viewModelScope.launch { loadIdentities() }
    }

    fun onNameChange(value: String) = mutableState.update { it.copy(name = value.take(NAME_MAX), error = null) }

    fun saveName() {
        if (!state.value.canSaveName) return
        busy { editor.updateProfile(ProfileUpdate(firstName = state.value.name.trim())).orFail() }
    }

    fun saveGoals() = busy { editor.saveGoals().orFail() }

    fun saveReminders() = busy { editor.saveReminders().orFail() }

    /** Where reminders and notices go: `auto` pushes to phones with the app and uses the bot otherwise. */
    fun pickChannel(channel: NotificationChannel) {
        if (channel == (state.value.me.notificationChannel ?: NotificationChannel.auto)) return
        busy { editor.updateProfile(ProfileUpdate(notificationChannel = channel)).orFail() }
    }

    fun startEmailLink() = mutableState.update { it.copy(emailLink = EmailLink(), error = null) }

    fun cancelEmailLink() = mutableState.update { it.copy(emailLink = null, error = null) }

    fun onLinkEmailChange(value: String) =
        mutableState.update { it.copy(emailLink = it.emailLink?.copy(email = value), error = null) }

    fun onLinkCodeChange(value: String) =
        mutableState.update {
            it.copy(emailLink = it.emailLink?.copy(code = value.filter(Char::isDigit).take(CODE_LENGTH)), error = null)
        }

    fun sendLinkCode() {
        val link = state.value.emailLink ?: return
        if (link.email.isBlank()) return
        busy {
            val sent = apiCall({ client.auth.startEmailSignIn(StartEmailSignInRequest(link.email.trim())) }) {}
            if (sent.orFail()) {
                mutableState.update {
                    it.copy(
                        emailLink = it.emailLink?.copy(codeSent = true, code = ""),
                    )
                }
            }
        }
    }

    fun confirmEmailLink() {
        val link = state.value.emailLink ?: return
        if (link.code.length != CODE_LENGTH) return
        busy {
            val linked = apiCall { client.profile.linkMyEmail(VerifyEmailSignInRequest(link.email.trim(), link.code)) }
            if (linked.orFail()) {
                mutableState.update { it.copy(emailLink = null) }
                loadIdentities()
            }
        }
    }

    fun linkTelegram() {
        if (state.value.busy || telegram?.isActive == true) return
        telegram =
            viewModelScope.launch {
                mutableState.update { it.copy(busy = true, error = null) }
                val request =
                    when (val created = signIn.startTelegram()) {
                        is ApiResult.Ok -> created.value
                        else -> return@launch finish(created.errorText())
                    }
                mutableState.update { it.copy(telegramUrl = request.botUrl) }
                when (val result = signIn.awaitTelegram(request)) {
                    is ApiResult.Ok -> {
                        changed(result.value)
                        loadIdentities()
                        finish(null)
                    }
                    null -> finish(TELEGRAM_EXPIRED)
                    else -> finish(result.errorText())
                }
            }
    }

    fun cancelTelegram() {
        telegram?.cancel()
        finish(null)
    }

    fun unlink(identity: SignInIdentity) =
        busy {
            if (apiCall({ client.profile.unlinkMyIdentity(identity.id) }) {}.orFail()) loadIdentities()
        }

    fun signOut() = onSignedOut()

    fun askDeletion() = mutableState.update { it.copy(confirmDeletion = true) }

    fun cancelDeletion() = mutableState.update { it.copy(confirmDeletion = false) }

    /** The server signs the user out everywhere and erases the data within 30 days (152-FZ). */
    fun deleteAccount() =
        busy {
            if (apiCall({ client.profile.requestAccountDeletion() }) {}.orFail()) onSignedOut()
        }

    private suspend fun loadIdentities() {
        val loaded = apiCall { client.profile.listMyIdentities() }
        if (loaded is ApiResult.Ok) mutableState.update { it.copy(identities = loaded.value.items) }
    }

    private fun changed(me: Me) {
        mutableState.update { it.copy(me = me, name = if (it.name.isBlank()) me.firstName else it.name) }
        onMeChanged(me)
    }

    private fun ApiResult<*>.orFail(): Boolean {
        if (this !is ApiResult.Ok) mutableState.update { it.copy(error = errorText()) }
        return this is ApiResult.Ok
    }

    private fun finish(error: String?) =
        mutableState.update { it.copy(busy = false, telegramUrl = null, error = error) }

    private fun busy(block: suspend () -> Unit) {
        if (state.value.busy) return
        mutableState.update { it.copy(busy = true, error = null, confirmDeletion = false) }
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
        const val CODE_LENGTH = 6
        const val TELEGRAM_EXPIRED = "Telegram не подтвердил привязку. Попробуйте ещё раз."
    }
}
