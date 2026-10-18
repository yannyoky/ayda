package app.ayda.android.ui.social

import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.res.stringResource
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import app.ayda.android.R
import app.ayda.android.ui.LocalAydaColors
import app.ayda.shared.social.InviteState
import app.ayda.shared.social.InviteViewModel

/** US-12: the answer to opening an invite link, shown over whatever screen the user is on. */
@Composable
fun InviteDialog(
    model: InviteViewModel,
    onClose: () -> Unit,
    onFriends: () -> Unit,
) {
    val state by model.state.collectAsStateWithLifecycle()
    val current = state
    val text =
        when (current) {
            InviteState.Accepting -> null
            is InviteState.Accepted -> stringResource(R.string.invite_accepted, current.friend.firstName)
            InviteState.Own -> stringResource(R.string.invite_own)
            InviteState.Expired -> stringResource(R.string.invite_expired)
            InviteState.Unknown -> stringResource(R.string.invite_unknown)
            is InviteState.Failed -> current.text
        }
    AlertDialog(
        onDismissRequest = { if (current != InviteState.Accepting) onClose() },
        text = {
            if (text == null) {
                CircularProgressIndicator(color = LocalAydaColors.current.accent)
            } else {
                Text(text)
            }
        },
        confirmButton = {
            when (current) {
                InviteState.Accepting -> {}
                is InviteState.Accepted ->
                    TextButton(
                        onClick = onFriends,
                    ) { Text(stringResource(R.string.invite_friends)) }
                is InviteState.Failed -> TextButton(onClick = model::accept) { Text(stringResource(R.string.retry)) }
                else -> TextButton(onClick = onClose) { Text(stringResource(R.string.close)) }
            }
        },
        dismissButton = {
            if (current is InviteState.Accepted || current is InviteState.Failed) {
                TextButton(onClick = onClose) { Text(stringResource(R.string.close)) }
            }
        },
    )
}
