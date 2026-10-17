package app.ayda.shared.auth

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.ayda.api.models.Me
import app.ayda.shared.ApiResult
import app.ayda.shared.errorText
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** What the sign-in screen shows. Errors are ready-to-show Russian texts from the server or the app. */
data class SignInState(
    val step: Step = Step.Email,
    val email: String = "",
    val code: String = "",
    val busy: Boolean = false,
    val error: String? = null,
    /** Set while waiting for the user to confirm in the bot; the screen opens it in Telegram. */
    val telegramUrl: String? = null,
) {
    enum class Step { Email, Code }

    val canSendCode: Boolean get() = !busy && EMAIL.matches(email.trim())
    val canVerify: Boolean get() = !busy && CODE.matches(code)

    private companion object {
        val EMAIL = Regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$")
        val CODE = Regex("^[0-9]{6}$")
    }
}

/** Shared by Android and iOS: the email-code flow and the optional Telegram flow. */
class SignInViewModel(
    private val signIn: SignIn,
    private val onSignedIn: (Me) -> Unit,
) : ViewModel() {
    private val mutableState = MutableStateFlow(SignInState())
    val state: StateFlow<SignInState> = mutableState.asStateFlow()

    private var telegram: Job? = null

    fun onEmailChange(value: String) = mutableState.update { it.copy(email = value, error = null) }

    fun onCodeChange(value: String) {
        val digits = value.filter(Char::isDigit).take(CODE_LENGTH)
        mutableState.update { it.copy(code = digits, error = null) }
        if (digits.length == CODE_LENGTH) verifyCode()
    }

    fun sendCode() {
        val current = state.value
        if (!current.canSendCode) return
        launchBusy {
            when (val result = signIn.sendCode(current.email)) {
                is ApiResult.Ok -> mutableState.update { it.copy(step = SignInState.Step.Code, code = "") }
                else -> fail(result)
            }
        }
    }

    fun verifyCode() {
        val current = state.value
        if (!current.canVerify) return
        launchBusy {
            when (val result = signIn.verifyCode(current.email, current.code)) {
                is ApiResult.Ok -> signedIn(result.value)
                else -> {
                    mutableState.update { it.copy(code = "") }
                    fail(result)
                }
            }
        }
    }

    /** Back from the code step to fix the address. */
    fun changeEmail() = mutableState.update { it.copy(step = SignInState.Step.Email, code = "", error = null) }

    fun signInWithTelegram() {
        if (state.value.busy || telegram?.isActive == true) return
        telegram =
            viewModelScope.launch {
                mutableState.update { it.copy(busy = true, error = null) }
                val request =
                    when (val created = signIn.startTelegram()) {
                        is ApiResult.Ok -> created.value
                        else -> return@launch fail(created)
                    }
                mutableState.update { it.copy(telegramUrl = request.botUrl) }
                when (val result = signIn.awaitTelegram(request)) {
                    is ApiResult.Ok -> signedIn(result.value)
                    null -> fail(TELEGRAM_EXPIRED)
                    else -> fail(result)
                }
            }
    }

    fun cancelTelegram() {
        telegram?.cancel()
        mutableState.update { it.copy(busy = false, telegramUrl = null) }
    }

    /** Start clean if the user signs out later and comes back to this screen. */
    private fun signedIn(me: Me) {
        mutableState.value = SignInState()
        onSignedIn(me)
    }

    private fun launchBusy(block: suspend () -> Unit) {
        if (state.value.busy) return
        mutableState.update { it.copy(busy = true, error = null) }
        viewModelScope.launch {
            block()
            mutableState.update { it.copy(busy = false) }
        }
    }

    private fun fail(result: ApiResult<*>) = fail(result.errorText())

    private fun fail(message: String) =
        mutableState.update { it.copy(busy = false, telegramUrl = null, error = message) }

    private companion object {
        const val CODE_LENGTH = 6
        const val TELEGRAM_EXPIRED = "Вход через Telegram не подтверждён. Попробуйте ещё раз или войдите по почте."
    }
}
