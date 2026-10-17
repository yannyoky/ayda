package app.ayda.android.ui.profile

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.RadioButton
import androidx.compose.material3.RadioButtonDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import app.ayda.android.R
import app.ayda.android.ui.Card
import app.ayda.android.ui.LocalAydaColors
import app.ayda.android.ui.PrimaryButton
import app.ayda.android.ui.QuietButton
import app.ayda.api.models.NotificationChannel
import app.ayda.api.models.SignInIdentity
import app.ayda.shared.profile.ProfileState
import app.ayda.shared.profile.ProfileViewModel

private enum class Section { Name, City, Goals, Habits, Reminders }

/** US-03 and ADR 0009: settings, sign-in methods, sign-out and account deletion. */
@Composable
fun ProfileScreen(model: ProfileViewModel) {
    val state by model.state.collectAsStateWithLifecycle()
    val editor by model.editor.state.collectAsStateWithLifecycle()
    val colors = LocalAydaColors.current
    val uriHandler = LocalUriHandler.current
    var open by rememberSaveable { mutableStateOf<Section?>(null) }
    val toggle = { section: Section -> open = if (open == section) null else section }

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
        Text(
            stringResource(R.string.profile_title),
            style = MaterialTheme.typography.headlineLarge,
            modifier = Modifier.padding(horizontal = 4.dp),
        )
        (state.error ?: editor.error)?.let { Text(it, style = MaterialTheme.typography.bodyMedium) }

        Editable(stringResource(R.string.onboarding_name_label), state.me.firstName, open == Section.Name, {
            toggle(Section.Name)
        }) {
            TextInput(
                value = state.name,
                onValueChange = model::onNameChange,
                label = stringResource(R.string.onboarding_name_label),
                onDone = model::saveName,
                capitalization = KeyboardCapitalization.Words,
            )
            PrimaryButton(stringResource(R.string.profile_save), onClick = model::saveName, enabled = state.canSaveName)
        }

        Card {
            Text(stringResource(R.string.profile_theme), style = MaterialTheme.typography.headlineSmall)
            ThemePicker(state.me.theme, model.editor)
        }

        val city = state.me.city
        Editable(
            stringResource(R.string.onboarding_city_search),
            city?.let { "${it.name}, ${it.regionName}" } ?: stringResource(R.string.profile_not_set),
            open == Section.City,
            { toggle(Section.City) },
        ) {
            CityEditor(city, editor, model.editor, onPicked = { open = null })
        }

        val goalTitles = editor.selectedGoals.map { code -> editor.goals.find { it.code == code }?.title ?: code }
        Editable(
            stringResource(R.string.profile_goals),
            goalTitles.joinToString().ifEmpty { stringResource(R.string.profile_not_set) },
            open == Section.Goals,
            { toggle(Section.Goals) },
        ) {
            GoalsEditor(editor, model.editor)
            PrimaryButton(
                stringResource(R.string.profile_save),
                onClick = model::saveGoals,
                enabled =
                    !editor.busy && !state.busy,
            )
        }

        Editable(
            stringResource(R.string.onboarding_habits_title),
            editor.habits.joinToString { it.text }.ifEmpty { stringResource(R.string.profile_not_set) },
            open == Section.Habits,
            { toggle(Section.Habits) },
        ) {
            HabitsEditor(editor, model.editor)
        }

        val off = stringResource(R.string.onboarding_reminders_off)
        Editable(
            stringResource(R.string.profile_reminders),
            "${state.me.reminders.morningAt ?: off} · ${state.me.reminders.eveningAt ?: off}",
            open == Section.Reminders,
            { toggle(Section.Reminders) },
        ) {
            RemindersEditor(editor, model.editor)
            PrimaryButton(
                stringResource(R.string.profile_save),
                onClick = model::saveReminders,
                enabled =
                    !editor.busy && !state.busy,
            )
        }

        ChannelPicker(state, model)

        SignInMethods(state, model)

        Card {
            QuietButton(stringResource(R.string.sign_out), onClick = model::signOut)
            QuietButton(stringResource(R.string.profile_delete), onClick = model::askDeletion, color = colors.muted)
        }
    }

    if (state.confirmDeletion) {
        AlertDialog(
            onDismissRequest = model::cancelDeletion,
            title = { Text(stringResource(R.string.profile_delete_title)) },
            text = { Text(stringResource(R.string.profile_delete_text)) },
            confirmButton = {
                TextButton(onClick = model::deleteAccount) { Text(stringResource(R.string.profile_delete_confirm)) }
            },
            dismissButton = { TextButton(onClick = model::cancelDeletion) { Text(stringResource(R.string.cancel)) } },
        )
    }
}

@Composable
private fun ChannelPicker(
    state: ProfileState,
    model: ProfileViewModel,
) {
    val colors = LocalAydaColors.current
    val current = state.me.notificationChannel ?: NotificationChannel.auto
    val options =
        listOf(
            Triple(NotificationChannel.auto, R.string.profile_channel_auto, R.string.profile_channel_auto_hint),
            Triple(NotificationChannel.push, R.string.profile_channel_push, R.string.profile_channel_push_hint),
            Triple(
                NotificationChannel.telegram,
                R.string.profile_channel_telegram,
                R.string.profile_channel_telegram_hint,
            ),
        )
    Card {
        Text(stringResource(R.string.profile_channel), style = MaterialTheme.typography.headlineSmall)
        Column(Modifier.selectableGroup()) {
            options.forEach { (channel, title, hint) ->
                Row(
                    Modifier
                        .fillMaxWidth()
                        .selectable(selected = channel == current, enabled = !state.busy, role = Role.RadioButton) {
                            model.pickChannel(channel)
                        }.padding(vertical = 8.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    RadioButton(
                        selected = channel == current,
                        onClick = null,
                        colors =
                            RadioButtonDefaults.colors(
                                selectedColor = colors.accent,
                                unselectedColor = colors.muted,
                            ),
                    )
                    Column {
                        Text(stringResource(title), style = MaterialTheme.typography.titleMedium)
                        Text(stringResource(hint), style = MaterialTheme.typography.bodyMedium, color = colors.muted)
                    }
                }
            }
        }
    }
}

@Composable
private fun SignInMethods(
    state: ProfileState,
    model: ProfileViewModel,
) {
    val colors = LocalAydaColors.current
    val uriHandler = LocalUriHandler.current
    Card {
        Text(stringResource(R.string.profile_sign_in), style = MaterialTheme.typography.headlineSmall)
        state.identities.forEach { identity ->
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    if (identity.provider ==
                        SignInIdentity.Provider.email
                    ) {
                        identity.label
                    } else {
                        stringResource(R.string.profile_telegram)
                    },
                    style = MaterialTheme.typography.titleMedium,
                    modifier = Modifier.weight(1f),
                )
                if (state.canUnlink) {
                    QuietButton(
                        stringResource(R.string.profile_unlink),
                        onClick = { model.unlink(identity) },
                        color = colors.muted,
                    )
                }
            }
        }
        val link = state.emailLink
        when {
            state.telegramUrl != null -> {
                Text(
                    stringResource(R.string.telegram_hint),
                    style = MaterialTheme.typography.bodyMedium,
                    color = colors.muted,
                )
                PrimaryButton(stringResource(R.string.telegram_open), onClick = {
                    runCatching { uriHandler.openUri(state.telegramUrl!!) }
                })
                QuietButton(stringResource(R.string.cancel), onClick = model::cancelTelegram)
            }
            link != null && !link.codeSent -> {
                TextInput(
                    value = link.email,
                    onValueChange = model::onLinkEmailChange,
                    label = stringResource(R.string.email),
                    onDone = model::sendLinkCode,
                    capitalization = KeyboardCapitalization.None,
                    keyboardType = KeyboardType.Email,
                )
                PrimaryButton(stringResource(R.string.send_code), onClick = model::sendLinkCode, enabled = !state.busy)
                QuietButton(stringResource(R.string.cancel), onClick = model::cancelEmailLink)
            }
            link != null -> {
                Text(
                    stringResource(R.string.code_sent_to, link.email.trim()),
                    style = MaterialTheme.typography.bodyMedium,
                    color = colors.muted,
                )
                TextInput(
                    value = link.code,
                    onValueChange = model::onLinkCodeChange,
                    label = stringResource(R.string.code),
                    onDone = model::confirmEmailLink,
                    keyboardType = KeyboardType.NumberPassword,
                )
                PrimaryButton(
                    stringResource(R.string.profile_link),
                    onClick = model::confirmEmailLink,
                    enabled = !state.busy,
                )
                QuietButton(stringResource(R.string.cancel), onClick = model::cancelEmailLink)
            }
            else -> {
                if (!state.hasEmail) {
                    QuietButton(
                        stringResource(R.string.profile_link_email),
                        onClick = model::startEmailLink,
                    )
                }
                if (!state.hasTelegram) {
                    QuietButton(
                        stringResource(R.string.profile_link_telegram),
                        onClick = model::linkTelegram,
                    )
                }
            }
        }
    }
}

@Composable
private fun Editable(
    title: String,
    summary: String,
    open: Boolean,
    onToggle: () -> Unit,
    content: @Composable ColumnScope.() -> Unit,
) {
    val colors = LocalAydaColors.current
    Card {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(modifier = Modifier.weight(1f)) {
                Text(title, style = MaterialTheme.typography.headlineSmall)
                Text(summary, style = MaterialTheme.typography.bodyMedium, color = colors.muted, maxLines = 2)
            }
            QuietButton(
                stringResource(if (open) R.string.profile_done else R.string.profile_change),
                onClick = onToggle,
            )
        }
        if (open) {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp), content = content)
        }
    }
}
