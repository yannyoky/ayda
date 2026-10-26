package app.ayda.android.ui.onboarding

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CheckboxDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.res.stringArrayResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import app.ayda.android.BuildConfig
import app.ayda.android.R
import app.ayda.android.ui.Card
import app.ayda.android.ui.LocalAydaColors
import app.ayda.android.ui.PrimaryButton
import app.ayda.shared.onboarding.ConsentViewModel

/** The privacy policy page Caddy serves next to the Mini App (docs/privacy.md is the source). */
internal val PRIVACY_URL = "https://${BuildConfig.INVITE_HOST}/privacy.html"

/** Consent to personal data processing, before anything else (152-FZ). */
@Composable
fun ConsentScreen(model: ConsentViewModel) {
    val state by model.state.collectAsStateWithLifecycle()
    val colors = LocalAydaColors.current
    Column(
        modifier =
            Modifier
                .fillMaxSize()
                .background(colors.bg)
                .safeDrawingPadding()
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(
            stringResource(R.string.consent_title),
            style = MaterialTheme.typography.headlineLarge,
            modifier = Modifier.padding(4.dp),
        )
        ConsentText()
        Card(
            modifier =
                Modifier.toggleable(value = state.agreed, role = Role.Checkbox, onValueChange = model::onAgreedChange),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Checkbox(
                    checked = state.agreed,
                    onCheckedChange = null,
                    colors = CheckboxDefaults.colors(checkedColor = colors.ink, checkmarkColor = colors.surface),
                )
                Text(stringResource(R.string.consent_accept), style = MaterialTheme.typography.titleMedium)
            }
        }
        state.error?.let { Text(it, style = MaterialTheme.typography.bodyMedium) }
        PrimaryButton(stringResource(R.string.consent_continue), onClick = model::accept, enabled = state.canContinue)
    }
}

/** The consent text itself, shared by the consent screen and the profile. */
@Composable
fun ConsentText() {
    val colors = LocalAydaColors.current
    Card {
        Text(stringResource(R.string.consent_intro), style = MaterialTheme.typography.bodyLarge)
        stringArrayResource(R.array.consent_items).forEach {
            Text("•  $it", style = MaterialTheme.typography.bodyLarge)
        }
    }
    Card(color = colors.plate) {
        Text(
            stringResource(R.string.consent_llm),
            style = MaterialTheme.typography.bodyLarge,
            color = colors.onPlate,
        )
        Text(
            stringResource(R.string.consent_storage),
            style = MaterialTheme.typography.bodyLarge,
            color = colors.onPlate,
        )
    }
    val uriHandler = LocalUriHandler.current
    Text(
        stringResource(R.string.consent_policy),
        style = MaterialTheme.typography.bodyMedium,
        color = colors.muted,
        modifier = Modifier.padding(horizontal = 4.dp),
    )
    TextButton(onClick = { runCatching { uriHandler.openUri(PRIVACY_URL) } }) {
        Text(stringResource(R.string.consent_policy_link), color = colors.ink)
    }
}
