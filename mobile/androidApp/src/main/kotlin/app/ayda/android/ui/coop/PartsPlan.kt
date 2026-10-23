package app.ayda.android.ui.coop

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.selection.toggleable
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp
import app.ayda.android.R
import app.ayda.android.ui.Card
import app.ayda.android.ui.LocalAydaColors
import app.ayda.android.ui.PrimaryButton
import app.ayda.android.ui.social.Avatar
import app.ayda.api.models.Coop
import app.ayda.api.models.CoopPart
import app.ayda.api.models.CoopStatus
import app.ayda.api.models.DayQuest
import app.ayda.shared.coop.CoopViewModel
import app.ayda.shared.coop.PartError

@Composable
private fun PartError.text(): String =
    when (this) {
        PartError.NotAssignee -> stringResource(R.string.plan_err_assignee)
        PartError.Locked -> stringResource(R.string.plan_err_locked)
        PartError.Done -> stringResource(R.string.plan_err_done)
        PartError.Pending -> stringResource(R.string.plan_err_pending)
        PartError.Full -> stringResource(R.string.plan_err_full)
        PartError.NotFound -> stringResource(R.string.coop_not_found)
        is PartError.Other -> text
    }

@Composable
private fun CoopPart.State.label(): String =
    when (this) {
        CoopPart.State.locked -> stringResource(R.string.plan_state_locked)
        CoopPart.State.open -> stringResource(R.string.plan_state_open)
        CoopPart.State.done -> stringResource(R.string.plan_state_done)
    }

/** The parts of a shared plan: who does what, the live checklist and hand-offs (ADR 0010). */
@Composable
fun PartsPlan(
    coop: Coop,
    model: CoopViewModel,
    meId: String,
    error: PartError?,
    quests: List<DayQuest>,
    onComplete: (DayQuest) -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text(stringResource(R.string.plan_title), style = MaterialTheme.typography.titleMedium)
        coop.parts.orEmpty().forEach { part ->
            Part(
                coop,
                part,
                mine = part.assignee.id == meId,
                model = model,
                quest = quests.firstOrNull { it.id == part.myQuestId },
                onComplete = onComplete,
            )
        }
        error?.let { Card { Text(it.text(), style = MaterialTheme.typography.labelLarge) } }
    }
}

@Composable
private fun Part(
    coop: Coop,
    part: CoopPart,
    mine: Boolean,
    model: CoopViewModel,
    quest: DayQuest?,
    onComplete: (DayQuest) -> Unit,
) {
    val colors = LocalAydaColors.current
    var choosing by remember(part.id) { mutableStateOf(false) }
    val handoff = part.handoff
    val others =
        coop.participants.filter {
            (it.status == CoopStatus.owner || it.status == CoopStatus.accepted) && it.user.id != part.assignee.id
        }
    val canTick = mine && part.state == CoopPart.State.open
    Card {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Avatar(part.assignee, size = 36)
            Column(Modifier.weight(1f)) {
                Text(part.title, style = MaterialTheme.typography.titleMedium)
                Text(
                    if (mine) {
                        stringResource(R.string.plan_you)
                    } else {
                        stringResource(R.string.plan_assignee, part.assignee.firstName)
                    },
                    style = MaterialTheme.typography.labelLarge,
                    color = colors.muted,
                )
            }
            Text(
                part.state.label(),
                style = MaterialTheme.typography.labelLarge,
                modifier = Modifier.background(colors.bg, MaterialTheme.shapes.small).padding(10.dp, 4.dp),
            )
        }
        part.place?.let { place ->
            Text(
                listOfNotNull(place.name, place.address).joinToString(", "),
                style = MaterialTheme.typography.bodyMedium,
                color = colors.muted,
            )
        }
        if (part.state == CoopPart.State.locked) {
            Text(
                stringResource(R.string.plan_after_previous),
                style = MaterialTheme.typography.bodyMedium,
                color = colors.muted,
            )
        }
        part.items.forEach { item ->
            Row(
                Modifier
                    .fillMaxWidth()
                    .heightIn(min = 48.dp)
                    .toggleable(
                        value = item.done,
                        enabled = canTick,
                        role = Role.Checkbox,
                        onValueChange = { model.tick(part.id, item.id, it) },
                    ),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Checkbox(checked = item.done, onCheckedChange = null, enabled = canTick)
                Text(
                    item.text,
                    style = MaterialTheme.typography.bodyLarge,
                    color = if (item.done) colors.muted else colors.ink,
                    textDecoration = if (item.done) TextDecoration.LineThrough else null,
                )
            }
        }
        if (handoff?.forMe == true) {
            Column(
                Modifier.fillMaxWidth().background(colors.bg, MaterialTheme.shapes.medium).padding(12.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Text(
                    stringResource(R.string.plan_incoming, part.assignee.firstName),
                    style = MaterialTheme.typography.titleSmall,
                )
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    PlanButton(stringResource(R.string.plan_accept_part), Modifier.weight(1f), primary = true) {
                        model.answerHandoff(part.id, true)
                    }
                    PlanButton(stringResource(R.string.plan_decline_part), Modifier.weight(1f)) {
                        model.answerHandoff(part.id, false)
                    }
                }
            }
        }
        if (mine && part.state != CoopPart.State.done && handoff != null && !handoff.forMe) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Text(
                    stringResource(R.string.plan_offered, handoff.to.firstName),
                    style = MaterialTheme.typography.bodyMedium,
                    color = colors.muted,
                    modifier = Modifier.weight(1f),
                )
                PlanButton(stringResource(R.string.plan_withdraw), Modifier) { model.withdrawHandoff(part.id) }
            }
        }
        if (mine && part.state != CoopPart.State.done && handoff == null) {
            if (choosing) {
                if (others.isEmpty()) {
                    Text(
                        stringResource(R.string.plan_nobody),
                        style = MaterialTheme.typography.bodyMedium,
                        color = colors.muted,
                    )
                }
                others.forEach { person ->
                    PlanButton(stringResource(R.string.plan_hand_to, person.user.firstName), Modifier.fillMaxWidth()) {
                        model.offerHandoff(part.id, person.user.id)
                        choosing = false
                    }
                }
            } else {
                PlanButton(stringResource(R.string.plan_hand_off), Modifier) { choosing = true }
            }
        }
        if (quest != null) {
            PrimaryButton(stringResource(R.string.plan_complete), onClick = { onComplete(quest) })
        }
    }
}

@Composable
private fun PlanButton(
    text: String,
    modifier: Modifier,
    primary: Boolean = false,
    onClick: () -> Unit,
) {
    val colors = LocalAydaColors.current
    Button(
        onClick = onClick,
        modifier = modifier.height(48.dp),
        shape = MaterialTheme.shapes.medium,
        colors =
            ButtonDefaults.buttonColors(
                containerColor = if (primary) colors.accent else colors.bg,
                contentColor = if (primary) colors.onAccent else colors.ink,
            ),
    ) { Text(text, style = MaterialTheme.typography.titleSmall) }
}
