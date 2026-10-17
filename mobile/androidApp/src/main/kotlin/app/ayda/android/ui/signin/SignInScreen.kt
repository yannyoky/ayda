package app.ayda.android.ui.signin

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import app.ayda.android.R
import app.ayda.android.ui.Card
import app.ayda.android.ui.LocalAydaColors
import app.ayda.android.ui.PrimaryButton
import app.ayda.android.ui.QuietButton
import app.ayda.shared.auth.SignInState
import app.ayda.shared.auth.SignInViewModel

/** Email with a one-time code; Telegram as an extra option (ADR 0009). */
@Composable
fun SignInScreen(model: SignInViewModel) {
    val state by model.state.collectAsStateWithLifecycle()
    val colors = LocalAydaColors.current
    val uriHandler = LocalUriHandler.current

    LaunchedEffect(state.telegramUrl) {
        state.telegramUrl?.let { runCatching { uriHandler.openUri(it) } }
    }

    Column(
        modifier =
            Modifier
                .fillMaxSize()
                .background(colors.bg)
                .safeDrawingPadding()
                .imePadding()
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Card(color = colors.plate) {
            Text(
                stringResource(R.string.scaffold_title),
                style = MaterialTheme.typography.displayLarge,
                color = colors.accent,
            )
            Text(
                stringResource(R.string.tagline),
                style = MaterialTheme.typography.headlineSmall,
                color = colors.onPlate,
            )
        }
        when {
            state.telegramUrl != null -> TelegramWaiting(state.telegramUrl!!, model::cancelTelegram)
            state.step == SignInState.Step.Email -> EmailStep(state, model)
            else -> CodeStep(state, model)
        }
        state.error?.let {
            Text(
                it,
                style = MaterialTheme.typography.bodyMedium,
                color = colors.ink,
                modifier = Modifier.padding(horizontal = 8.dp),
            )
        }
    }
}

@Composable
private fun EmailStep(
    state: SignInState,
    model: SignInViewModel,
) {
    Card {
        Text(stringResource(R.string.sign_in_title), style = MaterialTheme.typography.headlineSmall)
        Text(
            stringResource(R.string.sign_in_email_hint),
            style = MaterialTheme.typography.bodyMedium,
            color = LocalAydaColors.current.muted,
        )
        Field(
            value = state.email,
            onValueChange = model::onEmailChange,
            label = stringResource(R.string.email),
            keyboardType = KeyboardType.Email,
            onDone = model::sendCode,
        )
        PrimaryButton(stringResource(R.string.send_code), onClick = model::sendCode, enabled = state.canSendCode)
    }
    QuietButton(
        stringResource(R.string.sign_in_telegram),
        onClick = model::signInWithTelegram,
        modifier = Modifier.fillMaxWidth(),
        color = LocalAydaColors.current.muted,
    )
}

@Composable
private fun CodeStep(
    state: SignInState,
    model: SignInViewModel,
) {
    Card {
        Text(stringResource(R.string.code_title), style = MaterialTheme.typography.headlineSmall)
        Text(
            stringResource(R.string.code_sent_to, state.email.trim()),
            style = MaterialTheme.typography.bodyMedium,
            color = LocalAydaColors.current.muted,
        )
        Field(
            value = state.code,
            onValueChange = model::onCodeChange,
            label = stringResource(R.string.code),
            keyboardType = KeyboardType.NumberPassword,
            onDone = model::verifyCode,
        )
        PrimaryButton(stringResource(R.string.sign_in), onClick = model::verifyCode, enabled = state.canVerify)
        QuietButton(stringResource(R.string.resend_code), onClick = model::sendCode)
        QuietButton(stringResource(R.string.change_email), onClick = model::changeEmail)
    }
}

@Composable
private fun TelegramWaiting(
    url: String,
    onCancel: () -> Unit,
) {
    val uriHandler = LocalUriHandler.current
    Card {
        Text(stringResource(R.string.telegram_title), style = MaterialTheme.typography.headlineSmall)
        Text(
            stringResource(R.string.telegram_hint),
            style = MaterialTheme.typography.bodyMedium,
            color = LocalAydaColors.current.muted,
        )
        PrimaryButton(stringResource(R.string.telegram_open), onClick = { runCatching { uriHandler.openUri(url) } })
        QuietButton(stringResource(R.string.cancel), onClick = onCancel)
    }
}

@Composable
private fun Field(
    value: String,
    onValueChange: (String) -> Unit,
    label: String,
    keyboardType: KeyboardType,
    onDone: () -> Unit,
) {
    val colors = LocalAydaColors.current
    OutlinedTextField(
        value = value,
        onValueChange = onValueChange,
        label = { Text(label) },
        singleLine = true,
        shape = MaterialTheme.shapes.medium,
        keyboardOptions = KeyboardOptions(keyboardType = keyboardType, imeAction = ImeAction.Done),
        keyboardActions = KeyboardActions(onDone = { onDone() }),
        modifier = Modifier.fillMaxWidth(),
        colors =
            OutlinedTextFieldDefaults.colors(
                focusedBorderColor = colors.ink,
                unfocusedBorderColor = colors.track,
                focusedLabelColor = colors.ink,
                cursorColor = colors.ink,
            ),
    )
}
