package app.ayda.android.ui.day

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.GridItemSpan
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import app.ayda.android.R
import app.ayda.android.ui.LocalAydaColors
import app.ayda.api.models.DayQuest
import app.ayda.api.models.RejectReason
import app.ayda.shared.day.Notice
import app.ayda.shared.day.TodayState
import app.ayda.shared.day.TodayViewModel

/** Quest picker (US-07): take any number (points for the first few completed), swap what does not fit. */
@Composable
fun PickScreen(
    model: TodayViewModel,
    onClose: () -> Unit,
    onDiscuss: (DayQuest) -> Unit,
) {
    val state by model.state.collectAsStateWithLifecycle()
    val colors = LocalAydaColors.current
    Column(Modifier.fillMaxSize().background(colors.bg).safeDrawingPadding()) {
        LazyVerticalGrid(
            columns = GridCells.Fixed(2),
            modifier = Modifier.weight(1f),
            contentPadding = PaddingValues(16.dp),
            horizontalArrangement = Arrangement.spacedBy(10.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            item(
                span = { GridItemSpan(maxLineSpan) },
            ) { PickHeader(state.left, state.day?.limits?.maxScored ?: 0, onClose) }
            state.notice?.let { notice ->
                item(span = { GridItemSpan(maxLineSpan) }) {
                    Text(
                        notice.text(),
                        style = MaterialTheme.typography.labelLarge,
                        color = colors.onPlate,
                        modifier =
                            Modifier
                                .fillMaxWidth()
                                .background(colors.plate, MaterialTheme.shapes.medium)
                                .clickable(onClick = model::dismissNotice)
                                .padding(16.dp, 12.dp),
                    )
                }
            }
            if (state.offered.isEmpty()) {
                item(span = { GridItemSpan(maxLineSpan) }) {
                    Text(
                        stringResource(if (state.generating) R.string.today_generating else R.string.pick_empty),
                        style = MaterialTheme.typography.bodyLarge,
                        color = colors.muted,
                        modifier =
                            Modifier
                                .fillMaxWidth()
                                .background(
                                    colors.surface,
                                    MaterialTheme.shapes.large,
                                ).padding(16.dp),
                    )
                }
            }
            items(state.offered, key = { it.id }) { quest ->
                QuestCard(
                    quest,
                    selected = quest.id in state.chosen,
                    enabled = state.left > 0,
                    canReplace = state.canReplace,
                    onToggle = { model.toggle(quest.id) },
                    onReplace = { model.askReplace(quest) },
                    onDiscuss = { onDiscuss(quest) },
                )
            }
        }
        BottomBar(state, model, onClose)
    }
    state.replacing?.let { ReasonSheet(it, state, model) }
    if (state.ownQuest != null) OwnQuestSheet(state, model, onAdded = onClose)
}

@Composable
private fun PickHeader(
    left: Int,
    maxScored: Int,
    onClose: () -> Unit,
) {
    val colors = LocalAydaColors.current
    Row(Modifier.fillMaxWidth().padding(4.dp), verticalAlignment = Alignment.Top) {
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(stringResource(R.string.pick_title), style = MaterialTheme.typography.headlineSmall)
            Text(
                if (left >
                    0
                ) {
                    stringResource(R.string.pick_subtitle, maxScored)
                } else {
                    stringResource(R.string.pick_limit_reached)
                },
                style = MaterialTheme.typography.labelLarge,
                color = colors.muted,
            )
        }
        IconButton(onClick = onClose, modifier = Modifier.size(44.dp).background(colors.surface, CircleShape)) {
            AydaIcon(R.drawable.ic_close, colors.ink, contentDescription = stringResource(R.string.close))
        }
    }
}

@Composable
private fun Notice.text(): String =
    when (this) {
        is Notice.ReplacementsLeft -> stringResource(R.string.pick_replacements_left, count)
        Notice.NoAlternative -> stringResource(R.string.pick_no_alternative)
        Notice.NoReplacements -> stringResource(R.string.pick_no_replacements)
        is Notice.Error -> text
    }

@Composable
private fun QuestCard(
    quest: DayQuest,
    selected: Boolean,
    enabled: Boolean,
    canReplace: Boolean,
    onToggle: () -> Unit,
    onReplace: () -> Unit,
    onDiscuss: () -> Unit,
) {
    val colors = LocalAydaColors.current
    val background = if (selected) colors.accent else colors.surface
    val ink = if (selected) colors.onAccent else colors.ink
    val muted = if (selected) colors.onAccent else colors.muted
    val shape = RoundedCornerShape(24.dp)
    Column(Modifier.fillMaxWidth().heightIn(min = 160.dp).background(background, shape)) {
        Column(
            Modifier
                .fillMaxWidth()
                .clickable(enabled = enabled || selected, role = Role.Checkbox, onClick = onToggle)
                .padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    stringResource(quest.category.label()).uppercase(Russian),
                    style = MaterialTheme.typography.labelLarge,
                    color = colors.ink,
                    modifier =
                        Modifier
                            .background(if (selected) colors.surface else colors.bg, MaterialTheme.shapes.small)
                            .padding(8.dp, 4.dp),
                )
                Spacer(Modifier.weight(1f))
                if (selected) {
                    Box(
                        Modifier.size(28.dp).background(colors.plate, CircleShape),
                        contentAlignment = Alignment.Center,
                    ) {
                        AydaIcon(R.drawable.ic_check, colors.onPlate, size = 16)
                    }
                } else {
                    Box(Modifier.size(28.dp).border(2.dp, colors.track, CircleShape))
                }
            }
            Text(quest.title, style = MaterialTheme.typography.titleMedium, color = ink)
            quest.why?.let { Text(it, style = MaterialTheme.typography.bodyMedium, color = muted) }
            quest.event?.let { Text(eventSummary(it), style = MaterialTheme.typography.labelLarge, color = ink) }
            Text(
                stringResource(R.string.quest_minutes, quest.durationMin) + " · " +
                    stringResource(R.string.quest_points, quest.basePoints),
                style = MaterialTheme.typography.labelLarge,
                color = muted,
            )
        }
        quest.event?.let { EventLink(it, color = ink) }
        val discuss = stringResource(R.string.assistant_discuss_quest, quest.title)
        Button(
            onClick = onDiscuss,
            modifier =
                Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 8.dp)
                    .padding(top = 8.dp)
                    .height(36.dp)
                    .semantics { contentDescription = discuss },
            shape = MaterialTheme.shapes.small,
            contentPadding = PaddingValues(0.dp),
            colors = ButtonDefaults.buttonColors(containerColor = Color.Black.copy(alpha = 0.06f), contentColor = ink),
        ) {
            AydaIcon(R.drawable.ic_chat, ink, size = 14)
            Spacer(Modifier.size(6.dp))
            Text(stringResource(R.string.assistant_discuss), style = MaterialTheme.typography.labelLarge)
        }
        if (!canReplace) Spacer(Modifier.size(8.dp))
        if (canReplace) {
            Button(
                onClick = onReplace,
                modifier = Modifier.fillMaxWidth().padding(8.dp).height(36.dp),
                shape = MaterialTheme.shapes.small,
                contentPadding = PaddingValues(0.dp),
                colors =
                    ButtonDefaults.buttonColors(
                        containerColor = Color.Black.copy(alpha = 0.06f),
                        contentColor = ink,
                    ),
            ) {
                AydaIcon(R.drawable.ic_refresh, ink, size = 14)
                Spacer(Modifier.size(6.dp))
                Text(stringResource(R.string.pick_not_today), style = MaterialTheme.typography.labelLarge)
            }
        }
    }
}

@Composable
private fun BottomBar(
    state: TodayState,
    model: TodayViewModel,
    onClose: () -> Unit,
) {
    val colors = LocalAydaColors.current
    Row(
        Modifier.fillMaxWidth().padding(16.dp, 12.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Button(
            onClick = model::openOwnQuest,
            enabled = state.left > 0,
            modifier = Modifier.height(56.dp),
            shape = RoundedCornerShape(20.dp),
            colors = ButtonDefaults.buttonColors(containerColor = colors.surface, contentColor = colors.ink),
        ) {
            AydaIcon(R.drawable.ic_plus, colors.ink, size = 18)
            Text(stringResource(R.string.today_own), style = MaterialTheme.typography.titleMedium)
        }
        val count = state.chosen.size
        Button(
            onClick = { model.takeSelected(onClose) },
            enabled = count > 0 && !state.busy,
            modifier = Modifier.weight(1f).height(56.dp),
            shape = RoundedCornerShape(20.dp),
            colors =
                ButtonDefaults.buttonColors(
                    containerColor = colors.plate,
                    contentColor = colors.onPlate,
                    disabledContainerColor = colors.plate.copy(alpha = 0.5f),
                    disabledContentColor = colors.onPlate,
                ),
        ) {
            Text(
                if (count ==
                    0
                ) {
                    stringResource(R.string.pick_choose)
                } else {
                    pluralStringResource(R.plurals.pick_take, count, count)
                },
                style = MaterialTheme.typography.titleMedium,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.weight(1f, fill = false),
            )
            if (state.chosenPoints > 0) {
                Spacer(Modifier.size(8.dp))
                Text(
                    stringResource(R.string.quest_points, state.chosenPoints),
                    style = MaterialTheme.typography.labelLarge,
                    color = colors.onAccent,
                    maxLines = 1,
                    softWrap = false,
                    modifier = Modifier.background(colors.accent, MaterialTheme.shapes.small).padding(8.dp, 2.dp),
                )
            }
        }
    }
}

/** "Not today" asks why, so the assistant learns what does not fit (US-07). */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ReasonSheet(
    quest: DayQuest,
    state: TodayState,
    model: TodayViewModel,
) {
    val colors = LocalAydaColors.current
    val reasons =
        listOf(
            RejectReason.no_time to R.string.pick_reason_no_time,
            RejectReason.dont_want to R.string.pick_reason_dont_want,
            RejectReason.cant to R.string.pick_reason_cant,
        )
    ModalBottomSheet(onDismissRequest = model::cancelReplace, containerColor = colors.bg) {
        Column(
            Modifier.padding(horizontal = 16.dp).padding(bottom = 16.dp).navigationBarsPadding(),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text(stringResource(R.string.pick_reason_title), style = MaterialTheme.typography.headlineSmall)
            Text(quest.title, style = MaterialTheme.typography.bodyLarge, color = colors.muted)
            reasons.chunked(2).forEach { row ->
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    row.forEach { (reason, label) ->
                        ReasonButton(stringResource(label), colors.surface, colors.ink) { model.replace(reason) }
                    }
                    if (row.size == 1) {
                        ReasonButton(
                            stringResource(R.string.pick_no_reason),
                            colors.plate,
                            colors.onPlate,
                        ) { model.replace(null) }
                    }
                }
            }
            Text(
                stringResource(R.string.pick_replacements_left, state.day?.limits?.replacementsLeft ?: 0),
                style = MaterialTheme.typography.labelLarge,
                color = colors.muted,
            )
        }
    }
}

@Composable
private fun androidx.compose.foundation.layout.RowScope.ReasonButton(
    text: String,
    background: Color,
    content: Color,
    onClick: () -> Unit,
) = Button(
    onClick = onClick,
    modifier = Modifier.weight(1f).height(48.dp),
    shape = MaterialTheme.shapes.medium,
    colors = ButtonDefaults.buttonColors(containerColor = background, contentColor = content),
) { Text(text, style = MaterialTheme.typography.titleMedium) }
