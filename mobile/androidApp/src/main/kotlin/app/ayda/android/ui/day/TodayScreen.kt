package app.ayda.android.ui.day

import android.content.Context
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.TransformOrigin
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.layout.layout
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.ProgressBarRangeInfo
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.progressBarRangeInfo
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.zIndex
import androidx.core.content.edit
import androidx.lifecycle.compose.LifecycleResumeEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import app.ayda.android.R
import app.ayda.android.ui.Card
import app.ayda.android.ui.EaseOutQuint
import app.ayda.android.ui.LocalAydaColors
import app.ayda.android.ui.PressButton
import app.ayda.android.ui.PrimaryButton
import app.ayda.android.ui.QuietButton
import app.ayda.android.ui.Segmented
import app.ayda.android.ui.Unbounded
import app.ayda.android.ui.assistant.EventView
import app.ayda.android.ui.coop.CoopInvites
import app.ayda.api.models.AssistantEvent
import app.ayda.api.models.Day
import app.ayda.api.models.DayQuest
import app.ayda.api.models.Me
import app.ayda.api.models.Mood
import app.ayda.api.models.PoolStatus
import app.ayda.api.models.QuestState
import app.ayda.api.models.Visibility
import app.ayda.api.models.Weather
import app.ayda.shared.Motion
import app.ayda.shared.Radii
import app.ayda.shared.coop.CoopsViewModel
import app.ayda.shared.day.DayStage
import app.ayda.shared.day.TodayState
import app.ayda.shared.day.TodayViewModel
import java.text.NumberFormat
import java.time.format.DateTimeFormatter
import kotlin.math.roundToInt

/**
 * The morning half of the loop (US-05..US-08): the check-in and the day's quests as one card,
 * under a title that says the next step. Streak and points live on the friends tab, so this
 * screen keeps its room for the day itself.
 */
@Composable
fun TodayScreen(
    model: TodayViewModel,
    me: Me,
    coops: CoopsViewModel,
    onPick: () -> Unit,
    onComplete: (DayQuest) -> Unit,
    onOpenCoop: (String) -> Unit,
    onInviteCoop: (DayQuest) -> Unit,
    onAssistant: (DayQuest?) -> Unit,
) {
    val state by model.state.collectAsStateWithLifecycle()
    val colors = LocalAydaColors.current
    LaunchedEffect(state.openPicker) {
        if (state.openPicker) {
            model.pickerOpened()
            onPick()
        }
    }
    // A day ends at 04:00 local time, so coming back to the app may mean a new day.
    LifecycleResumeEffect(model) {
        model.refresh()
        coops.refresh()
        onPauseOrDispose {}
    }

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
        Header(state, me)
        state.loadError?.let { error ->
            Card {
                Text(error, style = MaterialTheme.typography.bodyLarge)
                PrimaryButton(stringResource(R.string.retry), onClick = model::refresh)
            }
        }
        val day = state.day ?: return@Column
        // One card for the day: the check-in plate on top, the quests tucked under it
        Column(Modifier.fillMaxWidth()) {
            Box(Modifier.zIndex(1f)) {
                if (state.showCheckinForm) {
                    CheckinForm(state, model)
                } else {
                    CheckinDone(day, model, onChat = { onAssistant(null) })
                }
            }
            if (state.stage != DayStage.Checkin) {
                QuestsCard(
                    state,
                    day,
                    onPick,
                    model::openOwnQuest,
                    QuestActions(
                        onComplete = onComplete,
                        onDiscuss = { onAssistant(it) },
                        onOpenCoop = onOpenCoop,
                        onInvite = onInviteCoop,
                    ),
                )
            }
        }
        CoopInvites(coops, onOpen = onOpenCoop)
        TopEvents(state.topEvents)
    }
    if (state.ownQuest != null) OwnQuestSheet(state, model)
}

/** "Top nearby" (ADR 0016): the region's most notable events, whatever the user's tastes. */
@Composable
private fun TopEvents(items: List<AssistantEvent>) {
    if (items.isEmpty()) return
    val colors = LocalAydaColors.current
    Column(
        Modifier.fillMaxWidth().background(colors.surface, MaterialTheme.shapes.large).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Text(stringResource(R.string.today_top_events), style = MaterialTheme.typography.titleMedium)
        items.forEach { EventView(it) }
        Text(
            stringResource(R.string.today_top_events_source),
            style = MaterialTheme.typography.labelSmall,
            color = colors.muted,
        )
    }
}

private val shortDay = DateTimeFormatter.ofPattern("EE, d MMMM", Russian)

@Composable
private fun Header(
    state: TodayState,
    me: Me,
) {
    val colors = LocalAydaColors.current
    val day = state.day
    // The date, city and weather are one quiet line; the title is the next step of the day.
    Column(Modifier.fillMaxWidth().padding(horizontal = 4.dp)) {
        val date = day?.let { java.time.LocalDate.parse(it.localDate.toString()) } ?: java.time.LocalDate.now()
        val eyebrow =
            listOfNotNull(
                shortDay.format(date).replaceFirstChar(Char::titlecase),
                me.city?.name,
                day?.weather?.text(),
            ).joinToString(" · ")
        Text(eyebrow, style = MaterialTheme.typography.labelLarge, color = colors.muted)
        val title =
            when (state.stage) {
                null -> stringResource(R.string.nav_today)
                DayStage.Checkin -> stringResource(R.string.today_stage_checkin)
                DayStage.Pick -> stringResource(R.string.today_stage_pick)
                DayStage.Doing -> stringResource(R.string.today_stage_doing, state.completedCount, state.mine.size)
                DayStage.Done -> stringResource(R.string.today_stage_done)
            }
        Text(title, style = MaterialTheme.typography.headlineLarge)
    }
}

@Composable
private fun Mood.label(): String =
    stringResource(
        when (this) {
            Mood.energetic -> R.string.today_mood_energetic
            Mood.normal -> R.string.today_mood_normal
            Mood.tired -> R.string.today_mood_tired
        },
    )

/** The check-in on the dark plate (US-05). The text is private and never logged. */
@Composable
private fun CheckinForm(
    state: TodayState,
    model: TodayViewModel,
) {
    val colors = LocalAydaColors.current
    Card(color = colors.plate) {
        Text(
            stringResource(R.string.today_checkin_title),
            style = MaterialTheme.typography.headlineSmall,
            color = colors.onPlate,
        )
        OutlinedTextField(
            value = state.checkinText,
            onValueChange = model::onCheckinTextChange,
            readOnly = state.busy,
            placeholder = { Text(stringResource(R.string.today_checkin_placeholder)) },
            minLines = 3,
            shape = MaterialTheme.shapes.medium,
            modifier = Modifier.fillMaxWidth(),
            colors =
                OutlinedTextFieldDefaults.colors(
                    focusedContainerColor = colors.plate2,
                    unfocusedContainerColor = colors.plate2,
                    focusedTextColor = colors.onPlate,
                    unfocusedTextColor = colors.onPlate,
                    focusedBorderColor = colors.accent,
                    unfocusedBorderColor = Color.Transparent,
                    focusedPlaceholderColor = colors.onPlate.copy(alpha = 0.6f),
                    unfocusedPlaceholderColor = colors.onPlate.copy(alpha = 0.6f),
                    cursorColor = colors.accent,
                ),
        )
        Segmented(
            options = Mood.entries.map { it to it.label() },
            selected = state.mood,
            onSelect = model::onMoodChange,
            track = colors.plate2,
            pill = colors.accent,
            selectedText = colors.onAccent,
            text = colors.onPlate.copy(alpha = 0.7f),
        )
        Text(
            stringResource(R.string.today_checkin_hint),
            style = MaterialTheme.typography.bodyMedium,
            color = colors.onPlate.copy(alpha = 0.7f),
        )
        state.error?.let { Text(it, style = MaterialTheme.typography.labelLarge, color = colors.onPlate) }
        if (state.busy) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                CircularProgressIndicator(color = colors.accent, strokeWidth = 2.dp, modifier = Modifier.size(18.dp))
                Text(
                    stringResource(R.string.today_checkin_busy),
                    style = MaterialTheme.typography.labelLarge,
                    color = colors.onPlate,
                )
            }
        }
        PrimaryButton(
            stringResource(R.string.today_checkin_submit),
            onClick = model::submitCheckin,
            enabled = !state.busy,
        )
        if (state.editingCheckin) {
            QuietButton(stringResource(R.string.cancel), onClick = model::cancelCheckinEdit, color = colors.onPlate)
        }
    }
}

@Composable
private fun CheckinDone(
    day: Day,
    model: TodayViewModel,
    onChat: () -> Unit,
) {
    val colors = LocalAydaColors.current
    val checkin = day.checkin ?: return
    Row(
        Modifier.fillMaxWidth().background(colors.plate, MaterialTheme.shapes.large).padding(16.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Column(Modifier.weight(1f)) {
            Text(
                stringResource(R.string.today_checkin_done, checkin.mood.label().lowercase(Russian)),
                style = MaterialTheme.typography.titleMedium,
                color = colors.onPlate,
            )
            if (checkin.text.isNotBlank()) {
                Text(
                    checkin.text,
                    style = MaterialTheme.typography.bodyMedium,
                    color = colors.onPlate.copy(alpha = 0.7f),
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
        // ADR 0013: the check-in goes on as a chat with the assistant
        PressButton(
            onClick = onChat,
            containerColor = colors.accent,
            contentColor = colors.onAccent,
            contentPadding = PaddingValues(0.dp),
            modifier = Modifier.size(44.dp),
        ) {
            AydaIcon(
                R.drawable.ic_spark_filled,
                colors.onAccent,
                contentDescription = stringResource(R.string.assistant_open),
            )
        }
        PressButton(
            onClick = model::editCheckin,
            containerColor = colors.plate2,
            contentColor = colors.onPlate,
            contentPadding = PaddingValues(14.dp, 0.dp),
            modifier = Modifier.height(44.dp),
        ) { Text(stringResource(R.string.today_checkin_redo), style = MaterialTheme.typography.labelLarge) }
    }
}

private const val STREAK_PREFS = "ayda.ui"
private const val STREAK_SEEN = "streak.seen"

/** Big numbers shrink so "1000 дней" still fits the half-width tile. */
private fun streakSize(streak: Int) =
    when ("$streak".length) {
        in 0..2 -> 52.sp
        3 -> 44.sp
        else -> 36.sp
    }

/** Streak and points, shown on the friends tab next to the ladder. */
@Composable
fun StatsRow(
    day: Day,
    onToday: () -> Unit,
) {
    val colors = LocalAydaColors.current
    val streak = day.streak.currentDays
    val context = LocalContext.current
    // The number rolls up once, the first time the user sees a longer streak
    val grew =
        remember {
            val prefs = context.getSharedPreferences(STREAK_PREFS, Context.MODE_PRIVATE)
            val seen = if (prefs.contains(STREAK_SEEN)) prefs.getInt(STREAK_SEEN, 0) else null
            seen != null && streak > seen
        }
    LaunchedEffect(streak) {
        context.getSharedPreferences(STREAK_PREFS, Context.MODE_PRIVATE).edit { putInt(STREAK_SEEN, streak) }
    }
    Row(Modifier.fillMaxWidth().height(136.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        if (streak == 0) {
            Column(
                Modifier
                    .weight(1f)
                    .fillMaxSize()
                    .background(colors.plate, MaterialTheme.shapes.large)
                    .padding(16.dp),
                verticalArrangement = Arrangement.SpaceBetween,
            ) {
                Text(
                    stringResource(R.string.today_streak),
                    style = MaterialTheme.typography.labelLarge,
                    color = colors.onPlate.copy(alpha = 0.7f),
                )
                Text(
                    stringResource(R.string.today_streak_start),
                    style = MaterialTheme.typography.titleMedium.copy(fontFamily = Unbounded),
                    color = colors.onPlate,
                )
                PressButton(
                    onClick = onToday,
                    containerColor = colors.accent,
                    contentColor = colors.onAccent,
                    shape = RoundedCornerShape(Radii.CHIP.dp),
                    contentPadding = PaddingValues(10.dp, 0.dp),
                    modifier = Modifier.height(32.dp),
                ) {
                    Text(stringResource(R.string.today_streak_start_cta), style = MaterialTheme.typography.labelLarge)
                    AydaIcon(R.drawable.ic_arrow, colors.onAccent, size = 14, modifier = Modifier.padding(start = 6.dp))
                }
            }
        } else {
            Column(
                Modifier
                    .weight(1f)
                    .fillMaxSize()
                    .background(colors.accent, MaterialTheme.shapes.large)
                    .padding(16.dp),
                verticalArrangement = Arrangement.SpaceBetween,
            ) {
                Text(
                    stringResource(R.string.today_streak),
                    style = MaterialTheme.typography.labelLarge,
                    color = colors.onAccent,
                )
                Row(
                    Modifier.clipToBounds(),
                    verticalAlignment = Alignment.Bottom,
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    StreakNumber(streak, grew)
                    Text(
                        pluralStringResource(R.plurals.today_days, streak),
                        style = MaterialTheme.typography.titleMedium,
                        color = colors.onAccent,
                        maxLines = 1,
                        modifier = Modifier.padding(bottom = 6.dp),
                    )
                }
            }
        }
        Column(
            Modifier
                .weight(1f)
                .fillMaxSize()
                .background(colors.surface, MaterialTheme.shapes.large)
                .padding(16.dp),
            verticalArrangement = Arrangement.SpaceBetween,
        ) {
            Text(stringResource(R.string.today_week), style = MaterialTheme.typography.labelLarge, color = colors.muted)
            Text(
                NumberFormat.getIntegerInstance(Russian).format(day.pointsWeek),
                style = MaterialTheme.typography.headlineLarge,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            Text(
                stringResource(R.string.today_points_today, day.pointsToday),
                style = MaterialTheme.typography.labelLarge,
                modifier =
                    Modifier
                        .background(colors.bg, RoundedCornerShape(Radii.CHIP.dp))
                        .padding(8.dp, 4.dp),
            )
        }
    }
}

/** The streak number; when it grew since the last visit it rolls up into place once. */
@Composable
private fun StreakNumber(
    streak: Int,
    grew: Boolean,
) {
    val colors = LocalAydaColors.current
    val fontSize = streakSize(streak)
    val progress = remember { Animatable(if (grew) 0f else 1f) }
    LaunchedEffect(Unit) {
        if (grew) progress.animateTo(1f, tween(Motion.STREAK_ROLL, easing = EaseOutQuint))
    }
    Text(
        "$streak",
        style = MaterialTheme.typography.displayLarge.copy(fontSize = fontSize, lineHeight = fontSize),
        color = colors.onAccent,
        maxLines = 1,
        modifier =
            Modifier.graphicsLayer {
                translationY = (1f - progress.value) * size.height * 0.6f
                alpha = progress.value
            },
    )
}

@Composable
private fun Weather.text(): String {
    val condition =
        stringResource(
            when (condition) {
                Weather.Condition.clear -> R.string.weather_clear
                Weather.Condition.cloudy -> R.string.weather_cloudy
                Weather.Condition.rain -> R.string.weather_rain
                Weather.Condition.snow -> R.string.weather_snow
                Weather.Condition.storm -> R.string.weather_storm
                Weather.Condition.unknown -> R.string.weather_unknown
            },
        )
    val degrees = temperatureC.roundToInt()
    return stringResource(R.string.today_weather, condition, if (degrees > 0) "+$degrees" else "$degrees")
}

/** What a quest row on Today can do; the row itself only shows "Готово", the rest is in its sheet. */
private class QuestActions(
    val onComplete: (DayQuest) -> Unit,
    val onDiscuss: (DayQuest) -> Unit,
    val onOpenCoop: (String) -> Unit,
    val onInvite: (DayQuest) -> Unit,
)

@Composable
private fun QuestsCard(
    state: TodayState,
    day: Day,
    onPick: () -> Unit,
    onOwn: () -> Unit,
    actions: QuestActions,
) {
    val colors = LocalAydaColors.current
    // Tucked under the check-in plate: its top hides behind the plate's rounded bottom
    Column(
        Modifier
            .fillMaxWidth()
            .layout { measurable, constraints ->
                val tuck = TUCK.dp.roundToPx()
                val placeable = measurable.measure(constraints)
                layout(placeable.width, placeable.height - tuck) { placeable.place(0, -tuck) }
            }.background(
                colors.surface,
                RoundedCornerShape(bottomStart = Radii.CARD.dp, bottomEnd = Radii.CARD.dp),
            ).padding(start = 16.dp, end = 16.dp, top = (TUCK + 16).dp, bottom = 16.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                stringResource(R.string.today_quests_title),
                style = MaterialTheme.typography.titleMedium.copy(fontFamily = Unbounded),
                modifier = Modifier.weight(1f),
            )
            Text(
                stringResource(R.string.today_scored_of, day.limits.scored, day.limits.maxScored),
                style = MaterialTheme.typography.labelLarge,
                color = colors.muted,
            )
        }
        if (state.mine.isNotEmpty()) Progress(state.mine)
        when (day.poolStatus) {
            PoolStatus.generating -> Muted(stringResource(R.string.today_generating))
            PoolStatus.failed -> Muted(stringResource(R.string.today_pool_failed))
            else -> {}
        }
        if (state.mine.isNotEmpty()) {
            state.mine.forEachIndexed { index, quest ->
                if (index > 0) HorizontalDivider(color = colors.bg)
                QuestRow(quest, actions)
            }
        } else if (day.poolStatus == PoolStatus.ready || day.poolStatus == PoolStatus.failed) {
            Muted(stringResource(R.string.today_none_taken))
        }
        if (state.left > 0) {
            // Stacked, not side by side: with a large system font the two labels don't fit in a row.
            Column(Modifier.padding(top = 8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                if (state.offered.isNotEmpty()) {
                    PressButton(
                        onClick = onPick,
                        containerColor = colors.plate,
                        contentColor = colors.onPlate,
                        modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp),
                    ) {
                        Text(
                            if (state.mine.isEmpty()) {
                                stringResource(R.string.today_pick)
                            } else {
                                stringResource(R.string.today_pick_more)
                            },
                            style = MaterialTheme.typography.titleMedium,
                        )
                        AydaIcon(
                            R.drawable.ic_arrow,
                            colors.onPlate,
                            size = 18,
                            modifier = Modifier.padding(start = 8.dp),
                        )
                    }
                }
                PressButton(
                    onClick = onOwn,
                    containerColor = colors.bg,
                    contentColor = colors.ink,
                    modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp),
                ) {
                    AydaIcon(R.drawable.ic_plus, colors.ink, size = 18)
                    Text(stringResource(R.string.today_own), style = MaterialTheme.typography.titleMedium)
                }
            }
        }
    }
}

/** How far the quests card slides under the check-in plate, in dp. */
private const val TUCK = 28

/** One segment per quest taken today, filled as they are done. */
@Composable
private fun Progress(quests: List<DayQuest>) {
    val colors = LocalAydaColors.current
    val done = quests.count { it.state == QuestState.completed }
    val label = stringResource(R.string.today_progress)
    Row(
        Modifier
            .fillMaxWidth()
            .padding(bottom = 6.dp)
            .semantics {
                contentDescription = label
                progressBarRangeInfo = ProgressBarRangeInfo(done.toFloat(), 0f..quests.size.toFloat(), quests.size)
            },
        horizontalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        quests.forEach { quest ->
            val fill by animateFloatAsState(
                if (quest.state == QuestState.completed) 1f else 0f,
                tween(500, easing = EaseOutQuint),
                label = "progress",
            )
            Box(
                Modifier
                    .weight(1f)
                    .height(6.dp)
                    .clip(CircleShape)
                    .background(colors.track),
            ) {
                Box(
                    Modifier
                        .fillMaxSize()
                        .graphicsLayer {
                            scaleX = fill
                            transformOrigin = TransformOrigin(0f, 0.5f)
                        }.background(colors.accent, CircleShape),
                )
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
        modifier = Modifier.padding(vertical = 8.dp),
    )

@Composable
private fun questMeta(quest: DayQuest): String {
    val event = quest.event
    return when {
        quest.state == QuestState.completed ->
            stringResource(R.string.today_completed) + quest.visibility?.let { " · " + it.doneText() }.orEmpty()
        quest.state == QuestState.expired -> stringResource(R.string.today_expired)
        event != null -> eventSummary(event)
        else ->
            listOfNotNull(
                quest.coopId?.let { stringResource(R.string.coop_together) },
                stringResource(R.string.quest_minutes, quest.durationMin),
                quest.why,
            ).joinToString(" · ")
    }
}

/**
 * A taken, completed or expired quest. The row keeps only "Готово" so the title has room; a tap
 * on the title opens a sheet with the rest: discuss it with the assistant, do it with friends
 * (US-18) or open its co-op, and the event link (US-19).
 */
@Composable
private fun QuestRow(
    quest: DayQuest,
    actions: QuestActions,
) {
    val colors = LocalAydaColors.current
    val haptics = LocalHapticFeedback.current
    val taken = quest.state == QuestState.taken
    val completed = quest.state == QuestState.completed
    val expired = quest.state == QuestState.expired
    var open by rememberSaveable(quest.id) { mutableStateOf(false) }
    val done = {
        haptics.performHapticFeedback(HapticFeedbackType.VirtualKey)
        open = false
        actions.onComplete(quest)
    }
    Row(
        Modifier.fillMaxWidth().padding(vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        if (completed) {
            Box(
                Modifier.size(44.dp).background(colors.plate, MaterialTheme.shapes.small),
                contentAlignment = Alignment.Center,
            ) { AydaIcon(R.drawable.ic_check, colors.onPlate) }
        } else {
            CategoryTile(quest.category)
        }
        Column(
            Modifier
                .weight(1f)
                .clip(MaterialTheme.shapes.small)
                .clickable(enabled = taken, role = Role.Button, onClick = { open = true }),
            verticalArrangement = Arrangement.spacedBy(2.dp),
        ) {
            Text(
                quest.title,
                style = MaterialTheme.typography.titleMedium,
                color = if (completed || expired) colors.muted else colors.ink,
                textDecoration = if (completed || expired) TextDecoration.LineThrough else null,
                maxLines = 3,
                overflow = TextOverflow.Ellipsis,
            )
            Text(
                questMeta(quest),
                style = MaterialTheme.typography.bodyMedium,
                color = colors.muted,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
        if (taken) {
            PressButton(
                onClick = done,
                containerColor = colors.accent,
                contentColor = colors.onAccent,
                contentPadding = PaddingValues(14.dp, 0.dp),
                modifier = Modifier.height(40.dp),
            ) { Text(stringResource(R.string.today_done), style = MaterialTheme.typography.titleMedium) }
        } else {
            Text(
                stringResource(R.string.quest_points, quest.pointsAwarded ?: quest.basePoints),
                style = MaterialTheme.typography.titleMedium,
                maxLines = 1,
                softWrap = false,
            )
        }
    }
    if (open) QuestSheet(quest, actions, onClose = { open = false }, onDone = done)
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun QuestSheet(
    quest: DayQuest,
    actions: QuestActions,
    onClose: () -> Unit,
    onDone: () -> Unit,
) {
    val colors = LocalAydaColors.current
    val coopId = quest.coopId
    // ModalBottomSheet slides up, and a swipe or a flick down closes it (docs/design/themes.md)
    ModalBottomSheet(onDismissRequest = onClose, containerColor = colors.bg) {
        Column(
            Modifier
                .padding(horizontal = 16.dp)
                .padding(bottom = 16.dp)
                .navigationBarsPadding()
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(quest.title, style = MaterialTheme.typography.headlineSmall)
                Text(questMeta(quest), style = MaterialTheme.typography.labelLarge, color = colors.muted)
                quest.event?.let { EventLink(it) }
            }
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                SheetAction(
                    R.drawable.ic_spark,
                    stringResource(R.string.today_action_discuss),
                    stringResource(R.string.assistant_discuss_quest, quest.title),
                ) {
                    onClose()
                    actions.onDiscuss(quest)
                }
                if (coopId != null) {
                    SheetAction(
                        R.drawable.ic_friends,
                        stringResource(R.string.today_action_coop),
                        stringResource(R.string.coop_open, quest.title),
                    ) {
                        onClose()
                        actions.onOpenCoop(coopId)
                    }
                } else {
                    SheetAction(
                        R.drawable.ic_friends,
                        stringResource(R.string.today_action_invite),
                        stringResource(R.string.coop_invite_to, quest.title),
                    ) {
                        onClose()
                        actions.onInvite(quest)
                    }
                }
            }
            PressButton(
                onClick = onDone,
                containerColor = colors.accent,
                contentColor = colors.onAccent,
                modifier = Modifier.fillMaxWidth().height(56.dp),
            ) { Text(stringResource(R.string.today_action_done), style = MaterialTheme.typography.titleMedium) }
        }
    }
}

@Composable
private fun SheetAction(
    icon: Int,
    label: String,
    description: String,
    onClick: () -> Unit,
) {
    val colors = LocalAydaColors.current
    PressButton(
        onClick = onClick,
        containerColor = colors.surface,
        contentColor = colors.ink,
        contentPadding = PaddingValues(16.dp, 0.dp),
        modifier =
            Modifier
                .fillMaxWidth()
                .height(56.dp)
                .semantics { contentDescription = description },
    ) {
        Box(
            Modifier.size(36.dp).background(colors.bg, MaterialTheme.shapes.small),
            contentAlignment = Alignment.Center,
        ) { AydaIcon(icon, colors.ink, size = 18) }
        Text(
            label,
            style = MaterialTheme.typography.titleMedium,
            modifier = Modifier.weight(1f).padding(start = 12.dp),
        )
    }
}

@Composable
private fun Visibility.doneText(): String =
    stringResource(
        when (this) {
            Visibility.personal -> R.string.today_done_personal
            Visibility.routine -> R.string.today_done_routine
            Visibility.friends -> R.string.today_done_friends
        },
    )
