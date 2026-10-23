package app.ayda.android.ui.coop

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.LifecycleResumeEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import app.ayda.android.R
import app.ayda.android.ui.Card
import app.ayda.android.ui.LocalAydaColors
import app.ayda.android.ui.PrimaryButton
import app.ayda.android.ui.day.AydaIcon
import app.ayda.android.ui.day.CategoryTile
import app.ayda.android.ui.social.Avatar
import app.ayda.api.models.Coop
import app.ayda.api.models.CoopKind
import app.ayda.api.models.CoopStatus
import app.ayda.api.models.DayQuest
import app.ayda.api.models.QuestState
import app.ayda.api.models.UserSummary
import app.ayda.shared.coop.AnswerError
import app.ayda.shared.coop.CoopInviteViewModel
import app.ayda.shared.coop.CoopViewModel
import app.ayda.shared.coop.CoopsViewModel
import kotlin.time.Clock

@Composable
private fun AnswerError.text(): String =
    when (this) {
        AnswerError.Over -> stringResource(R.string.coop_over)
        AnswerError.NotFound -> stringResource(R.string.coop_not_found)
        AnswerError.DailyLimit -> stringResource(R.string.coop_limit)
        AnswerError.AlreadyAnswered -> stringResource(R.string.coop_answered)
        is AnswerError.Other -> text
    }

@Composable
private fun AnswerButtons(
    enabled: Boolean,
    onAnswer: (Boolean) -> Unit,
) {
    val colors = LocalAydaColors.current
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Button(
            onClick = { onAnswer(true) },
            enabled = enabled,
            modifier = Modifier.weight(1f).height(48.dp),
            shape = MaterialTheme.shapes.medium,
            colors = ButtonDefaults.buttonColors(containerColor = colors.accent, contentColor = colors.onAccent),
        ) { Text(stringResource(R.string.coop_accept), style = MaterialTheme.typography.titleMedium) }
        Button(
            onClick = { onAnswer(false) },
            enabled = enabled,
            modifier = Modifier.weight(1f).height(48.dp),
            shape = MaterialTheme.shapes.medium,
            colors = ButtonDefaults.buttonColors(containerColor = colors.bg, contentColor = colors.ink),
        ) { Text(stringResource(R.string.coop_decline), style = MaterialTheme.typography.titleMedium) }
    }
}

/** US-18: invitations on the Today screen, answered right there. */
@Composable
fun CoopInvites(
    model: CoopsViewModel,
    onOpen: (String) -> Unit,
) {
    val state by model.state.collectAsStateWithLifecycle()
    val colors = LocalAydaColors.current
    if (state.invites.isEmpty()) return
    Card {
        Text(stringResource(R.string.coop_invites_title), style = MaterialTheme.typography.titleMedium)
        Text(stringResource(R.string.coop_rule), style = MaterialTheme.typography.bodyMedium, color = colors.muted)
        state.invites.forEachIndexed { index, coop ->
            if (index > 0) HorizontalDivider(color = colors.bg)
            Row(
                Modifier.fillMaxWidth().clickable { onOpen(coop.id) }.padding(vertical = 4.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                Avatar(coop.owner, size = 40)
                Column(Modifier.weight(1f)) {
                    Text(
                        stringResource(R.string.coop_invited_by, coop.owner.firstName),
                        style = MaterialTheme.typography.labelLarge,
                        color = colors.muted,
                    )
                    Text(
                        coop.title,
                        style = MaterialTheme.typography.titleMedium,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Text(
                        stringResource(R.string.quest_minutes, coop.durationMin),
                        style = MaterialTheme.typography.bodyMedium,
                        color = colors.muted,
                    )
                }
            }
            AnswerButtons(enabled = state.answering == null) { model.answer(coop.id, it) }
        }
        state.error?.let { Text(it.text(), style = MaterialTheme.typography.labelLarge) }
    }
}

/** The co-op button on a quest row: opens the co-op, or offers to invite friends to a taken quest. */
@Composable
fun CoopButton(
    quest: DayQuest,
    onOpen: (String) -> Unit,
    onInvite: (DayQuest) -> Unit,
) {
    val colors = LocalAydaColors.current
    val coopId = quest.coopId
    if (coopId == null && quest.state != QuestState.taken) return
    IconButton(
        onClick = { if (coopId != null) onOpen(coopId) else onInvite(quest) },
        modifier = Modifier.size(40.dp).clip(MaterialTheme.shapes.small).background(colors.bg),
    ) {
        AydaIcon(
            R.drawable.ic_friends,
            colors.ink,
            size = 18,
            contentDescription =
                stringResource(if (coopId != null) R.string.coop_open else R.string.coop_invite_to, quest.title),
        )
    }
}

/** US-18: pick 1-3 friends to do a taken quest together. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CoopSheet(
    model: CoopInviteViewModel,
    quest: DayQuest,
    onClose: () -> Unit,
    onCreated: (Coop) -> Unit,
) {
    val state by model.state.collectAsStateWithLifecycle()
    val colors = LocalAydaColors.current
    ModalBottomSheet(onDismissRequest = onClose, containerColor = colors.bg) {
        Column(
            Modifier
                .padding(horizontal = 16.dp)
                .padding(bottom = 16.dp)
                .navigationBarsPadding()
                .imePadding()
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text(stringResource(R.string.coop_sheet_title), style = MaterialTheme.typography.headlineSmall)
            Column {
                Text(quest.title, style = MaterialTheme.typography.titleMedium)
                Text(
                    stringResource(R.string.coop_sheet_hint),
                    style = MaterialTheme.typography.bodyMedium,
                    color = colors.muted,
                )
            }
            if (state.loaded && state.friends.isEmpty()) {
                Text(
                    stringResource(R.string.coop_no_friends),
                    style = MaterialTheme.typography.labelLarge,
                    color = colors.muted,
                )
            } else {
                Text(stringResource(R.string.coop_pick_friends), style = MaterialTheme.typography.labelLarge)
                state.friends.forEach { friend ->
                    val on = friend.id in state.picked
                    val full = state.picked.size >= CoopInviteViewModel.MAX_FRIENDS
                    Row(
                        Modifier
                            .fillMaxWidth()
                            .clip(MaterialTheme.shapes.medium)
                            .background(colors.surface)
                            .toggleable(
                                value = on,
                                enabled = on || !full,
                                role = Role.Checkbox,
                            ) { model.toggle(friend.id) }
                            .padding(10.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(12.dp),
                    ) {
                        Avatar(UserSummary(friend.id, friend.firstName, friend.avatarUrl), size = 36)
                        Text(
                            friend.firstName,
                            style = MaterialTheme.typography.titleMedium,
                            modifier = Modifier.weight(1f),
                        )
                        Box(
                            Modifier.size(24.dp).background(if (on) colors.accent else colors.bg, CircleShape),
                            contentAlignment = Alignment.Center,
                        ) { if (on) AydaIcon(R.drawable.ic_check, colors.onAccent, size = 14) }
                    }
                }
            }
            state.error?.let { Text(it, style = MaterialTheme.typography.labelLarge) }
            PrimaryButton(
                if (state.picked.isEmpty()) {
                    stringResource(R.string.coop_send)
                } else {
                    stringResource(R.string.coop_send_n, state.picked.size)
                },
                onClick = { model.send(onCreated) },
                enabled = state.canSend,
            )
        }
    }
}

@Composable
private fun CoopStatus.label(): String =
    stringResource(
        when (this) {
            CoopStatus.owner -> R.string.coop_status_owner
            CoopStatus.invited -> R.string.coop_status_invited
            CoopStatus.accepted -> R.string.coop_status_accepted
            CoopStatus.declined -> R.string.coop_status_declined
        },
    )

/** US-18: one co-op, its participants, the answer and the shared chat. */
@Composable
fun CoopScreen(
    model: CoopViewModel,
    meId: String,
    myQuest: DayQuest?,
    quests: List<DayQuest>,
    onBack: () -> Unit,
    onComplete: (DayQuest) -> Unit,
    onChat: (String) -> Unit,
) {
    val state by model.state.collectAsStateWithLifecycle()
    val colors = LocalAydaColors.current
    val openedAt = remember { Clock.System.now() }
    LifecycleResumeEffect(model) {
        model.refresh()
        onPauseOrDispose {}
    }

    Column(
        Modifier
            .fillMaxSize()
            .background(colors.bg)
            .safeDrawingPadding()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            IconButton(
                onClick = onBack,
                modifier = Modifier.size(44.dp).clip(RoundedCornerShape(50)).background(colors.surface),
            ) {
                AydaIcon(
                    R.drawable.ic_back,
                    colors.ink,
                    size = 20,
                    contentDescription = stringResource(R.string.chats_back),
                )
            }
            Text(
                stringResource(R.string.coop_eyebrow),
                style = MaterialTheme.typography.labelLarge,
                color = colors.muted,
            )
        }
        if (state.notFound) {
            Card {
                Text(stringResource(R.string.coop_not_found), style = MaterialTheme.typography.bodyLarge)
                PrimaryButton(stringResource(R.string.complete_to_today), onClick = onBack)
            }
            return@Column
        }
        state.loadError?.let { error ->
            Card {
                Text(error, style = MaterialTheme.typography.bodyLarge)
                PrimaryButton(stringResource(R.string.retry), onClick = model::refresh)
            }
        }
        val coop = state.coop ?: return@Column
        Column(
            Modifier.fillMaxWidth().background(colors.accent, MaterialTheme.shapes.large).padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                CategoryTile(coop.category, background = colors.plate, tint = colors.onPlate)
                Column {
                    Text(coop.title, style = MaterialTheme.typography.headlineSmall, color = colors.onAccent)
                    Text(
                        stringResource(R.string.quest_minutes, coop.durationMin) + " · " +
                            stringResource(R.string.coop_invited_by, coop.owner.firstName),
                        style = MaterialTheme.typography.labelLarge,
                        color = colors.onAccent,
                    )
                }
            }
            Text(
                stringResource(if (coop.bonusAwarded) R.string.coop_bonus_done else R.string.coop_rule),
                style = MaterialTheme.typography.labelLarge,
                color = colors.ink,
                modifier =
                    Modifier
                        .fillMaxWidth()
                        .background(
                            colors.surface,
                            MaterialTheme.shapes.small,
                        ).padding(12.dp, 8.dp),
            )
        }
        if (coop.kind == CoopKind.parts) {
            PartsPlan(coop, model, meId, state.partError, quests, onComplete)
        } else {
            coop.place?.let { place ->
                Card {
                    Text(place.name, style = MaterialTheme.typography.titleMedium)
                    place.address?.let { Muted(it) }
                }
            }
        }
        Card {
            Text(stringResource(R.string.coop_participants), style = MaterialTheme.typography.titleMedium)
            coop.participants.forEachIndexed { index, person ->
                if (index > 0) HorizontalDivider(color = colors.bg)
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    Avatar(person.user, size = 40)
                    Text(
                        if (person.user.id ==
                            meId
                        ) {
                            stringResource(R.string.coop_you, person.user.firstName)
                        } else {
                            person.user.firstName
                        },
                        style = MaterialTheme.typography.titleMedium,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.weight(1f),
                    )
                    if (person.completed) {
                        Row(
                            Modifier.background(colors.plate, MaterialTheme.shapes.small).padding(10.dp, 4.dp),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(4.dp),
                        ) {
                            AydaIcon(R.drawable.ic_check, colors.onPlate, size = 14)
                            Text(
                                stringResource(R.string.coop_done),
                                style = MaterialTheme.typography.labelLarge,
                                color = colors.onPlate,
                            )
                        }
                    } else {
                        Text(
                            person.status.label(),
                            style = MaterialTheme.typography.labelLarge,
                            color = colors.muted,
                            textDecoration =
                                if (person.status ==
                                    CoopStatus.declined
                                ) {
                                    TextDecoration.LineThrough
                                } else {
                                    null
                                },
                        )
                    }
                }
            }
        }
        state.error?.let { Card { Text(it.text(), style = MaterialTheme.typography.labelLarge) } }
        Spacer(Modifier.height(4.dp))
        when (coop.myStatus) {
            CoopStatus.invited ->
                if (coop.expiresAt <= openedAt) {
                    Muted(stringResource(R.string.coop_over))
                } else {
                    AnswerButtons(enabled = !state.answering, onAnswer = model::answer)
                }
            CoopStatus.declined -> Muted(stringResource(R.string.coop_declined))
            else -> {}
        }
        if (myQuest?.state ==
            QuestState.taken
        ) {
            PrimaryButton(stringResource(R.string.coop_complete), onClick = { onComplete(myQuest) })
        }
        coop.conversationId?.let { chatId ->
            Button(
                onClick = { onChat(chatId) },
                modifier = Modifier.fillMaxWidth().height(52.dp),
                shape = MaterialTheme.shapes.medium,
                colors = ButtonDefaults.buttonColors(containerColor = colors.surface, contentColor = colors.ink),
            ) {
                AydaIcon(R.drawable.ic_chat, colors.ink, size = 20)
                Spacer(Modifier.size(8.dp))
                Text(stringResource(R.string.coop_to_chat), style = MaterialTheme.typography.titleMedium)
            }
        }
    }
}

@Composable
private fun Muted(text: String) =
    Text(
        text,
        style = MaterialTheme.typography.labelLarge,
        color = LocalAydaColors.current.muted,
        modifier = Modifier.fillMaxWidth(),
        textAlign = androidx.compose.ui.text.style.TextAlign.Center,
    )
