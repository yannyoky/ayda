package app.ayda.android.ui.day

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.LifecycleResumeEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import app.ayda.android.R
import app.ayda.android.ui.Card
import app.ayda.android.ui.LocalAydaColors
import app.ayda.android.ui.PrimaryButton
import app.ayda.android.ui.QuietButton
import app.ayda.api.models.Day
import app.ayda.api.models.DayQuest
import app.ayda.api.models.Me
import app.ayda.api.models.Mood
import app.ayda.api.models.PoolStatus
import app.ayda.api.models.QuestState
import app.ayda.api.models.Visibility
import app.ayda.api.models.Weather
import app.ayda.shared.day.TodayState
import app.ayda.shared.day.TodayViewModel
import java.text.NumberFormat
import java.time.format.DateTimeFormatter
import kotlin.math.roundToInt

/** The morning half of the loop (US-05..US-08): check-in, points, streak and the day's quests. */
@Composable
fun TodayScreen(
    model: TodayViewModel,
    me: Me,
    onPick: () -> Unit,
    onOpenProfile: () -> Unit,
) {
    val state by model.state.collectAsStateWithLifecycle()
    val colors = LocalAydaColors.current
    // A day ends at 04:00 local time, so coming back to the app may mean a new day.
    LifecycleResumeEffect(model) {
        model.refresh()
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
        Header(state.day, me, onOpenProfile)
        state.loadError?.let { error ->
            Card {
                Text(error, style = MaterialTheme.typography.bodyLarge)
                PrimaryButton(stringResource(R.string.retry), onClick = model::refresh)
            }
        }
        val day = state.day ?: return@Column
        if (state.showCheckinForm) CheckinForm(state, model) else CheckinDone(day, model)
        StatsRow(day)
        QuestsCard(state, day, onPick, model::openOwnQuest)
    }
    if (state.ownQuest != null) OwnQuestSheet(state, model)
}

private val dayTitle = DateTimeFormatter.ofPattern("EEEE, d MMMM", Russian)

@Composable
private fun Header(
    day: Day?,
    me: Me,
    onOpenProfile: () -> Unit,
) {
    val colors = LocalAydaColors.current
    Row(Modifier.fillMaxWidth().padding(horizontal = 4.dp), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            day?.let {
                val date = java.time.LocalDate.parse(it.localDate.toString())
                Text(
                    dayTitle.format(date).replaceFirstChar(Char::titlecase),
                    style = MaterialTheme.typography.labelLarge,
                    color = colors.muted,
                )
            }
            Text(
                if (me.firstName.isBlank()) {
                    stringResource(R.string.hello)
                } else {
                    stringResource(R.string.hello_name, me.firstName)
                },
                style = MaterialTheme.typography.headlineLarge,
            )
        }
        IconButton(
            onClick = onOpenProfile,
            modifier = Modifier.size(48.dp).background(colors.surface, MaterialTheme.shapes.extraLarge),
        ) {
            AydaIcon(R.drawable.ic_profile, colors.ink, contentDescription = stringResource(R.string.profile_open))
        }
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
                    focusedPlaceholderColor = colors.onPlate.copy(alpha = 0.5f),
                    unfocusedPlaceholderColor = colors.onPlate.copy(alpha = 0.5f),
                    cursorColor = colors.accent,
                ),
        )
        SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
            Mood.entries.forEachIndexed { index, mood ->
                SegmentedButton(
                    selected = state.mood == mood,
                    onClick = { model.onMoodChange(mood) },
                    shape = SegmentedButtonDefaults.itemShape(index, Mood.entries.size),
                    icon = {},
                    colors =
                        SegmentedButtonDefaults.colors(
                            activeContainerColor = colors.accent,
                            activeContentColor = colors.onAccent,
                            inactiveContainerColor = colors.plate2,
                            inactiveContentColor = colors.onPlate,
                            activeBorderColor = Color.Transparent,
                            inactiveBorderColor = Color.Transparent,
                        ),
                ) { Text(mood.label()) }
            }
        }
        Text(
            stringResource(R.string.today_checkin_hint),
            style = MaterialTheme.typography.bodyMedium,
            color = colors.onPlate.copy(alpha = 0.7f),
        )
        state.error?.let { Text(it, style = MaterialTheme.typography.labelLarge, color = colors.onPlate) }
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
) {
    val colors = LocalAydaColors.current
    val checkin = day.checkin ?: return
    Row(
        Modifier.fillMaxWidth().background(colors.plate, MaterialTheme.shapes.large).padding(16.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Box(
            Modifier.size(44.dp).background(colors.plate2, MaterialTheme.shapes.small),
            contentAlignment = Alignment.Center,
        ) { AydaIcon(R.drawable.ic_check, colors.accent) }
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
        Button(
            onClick = model::editCheckin,
            shape = MaterialTheme.shapes.medium,
            colors = ButtonDefaults.buttonColors(containerColor = colors.plate2, contentColor = colors.onPlate),
        ) { Text(stringResource(R.string.today_checkin_redo), style = MaterialTheme.typography.labelLarge) }
    }
}

@Composable
private fun StatsRow(day: Day) {
    val colors = LocalAydaColors.current
    val streak = day.streak.currentDays
    Row(Modifier.fillMaxWidth().height(136.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
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
            Row(verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("$streak", style = MaterialTheme.typography.displayLarge, color = colors.onAccent)
                Text(
                    pluralStringResource(R.plurals.today_days, streak),
                    style = MaterialTheme.typography.titleMedium,
                    color = colors.onAccent,
                    modifier = Modifier.padding(bottom = 6.dp),
                )
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
            )
            Text(
                stringResource(R.string.today_points_today, day.pointsToday),
                style = MaterialTheme.typography.labelLarge,
                modifier = Modifier.background(colors.bg, MaterialTheme.shapes.small).padding(8.dp, 4.dp),
            )
        }
    }
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

@Composable
private fun QuestsCard(
    state: TodayState,
    day: Day,
    onPick: () -> Unit,
    onOwn: () -> Unit,
) {
    val colors = LocalAydaColors.current
    Column(
        Modifier.fillMaxWidth().background(colors.surface, MaterialTheme.shapes.large).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                stringResource(R.string.today_quests_title),
                style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.weight(1f),
            )
            Text(
                stringResource(R.string.today_taken_of, day.limits.taken, day.limits.maxTaken),
                style = MaterialTheme.typography.labelLarge,
                color = colors.muted,
            )
        }
        val weather = day.weather
        if (weather != null && day.poolStatus != PoolStatus.none) {
            Text(weather.text(), style = MaterialTheme.typography.bodyMedium, color = colors.muted)
        }
        when (day.poolStatus) {
            PoolStatus.generating -> Muted(stringResource(R.string.today_generating))
            PoolStatus.failed -> Muted(stringResource(R.string.today_pool_failed))
            else -> {}
        }
        if (state.mine.isNotEmpty()) {
            state.mine.forEachIndexed { index, quest ->
                if (index > 0) HorizontalDivider(color = colors.bg)
                QuestRow(quest)
            }
        } else if (day.poolStatus == PoolStatus.ready || day.poolStatus == PoolStatus.failed) {
            Muted(stringResource(R.string.today_none_taken))
        }
        if (state.left > 0) {
            Row(Modifier.padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                if (state.offered.isNotEmpty()) {
                    Button(
                        onClick = onPick,
                        modifier = Modifier.weight(1f).height(48.dp),
                        shape = MaterialTheme.shapes.medium,
                        colors =
                            ButtonDefaults.buttonColors(
                                containerColor = colors.plate,
                                contentColor = colors.onPlate,
                            ),
                    ) {
                        Text(
                            if (state.mine.isEmpty()) {
                                stringResource(R.string.today_pick)
                            } else {
                                stringResource(R.string.today_pick_more, state.left)
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
                Button(
                    onClick = onOwn,
                    modifier = (if (state.offered.isEmpty()) Modifier.weight(1f) else Modifier).height(48.dp),
                    shape = MaterialTheme.shapes.medium,
                    colors = ButtonDefaults.buttonColors(containerColor = colors.bg, contentColor = colors.ink),
                ) {
                    AydaIcon(R.drawable.ic_plus, colors.ink, size = 18)
                    Text(stringResource(R.string.today_own), style = MaterialTheme.typography.titleMedium)
                }
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

/** A taken, completed or expired quest; an event quest shows its time, place, price and source. */
@Composable
private fun QuestRow(quest: DayQuest) {
    val colors = LocalAydaColors.current
    val completed = quest.state == QuestState.completed
    val expired = quest.state == QuestState.expired
    val event = quest.event
    val meta =
        when {
            completed ->
                stringResource(R.string.today_completed) +
                    quest.visibility?.let { " · " + it.doneText() }.orEmpty()
            expired -> stringResource(R.string.today_expired)
            event != null -> eventSummary(event)
            else ->
                listOfNotNull(
                    stringResource(R.string.quest_minutes, quest.durationMin),
                    quest.why,
                ).joinToString(" · ")
        }
    Row(
        Modifier.fillMaxWidth().heightIn(min = 64.dp).padding(vertical = 8.dp),
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
        Column(Modifier.weight(1f)) {
            Text(
                quest.title,
                style = MaterialTheme.typography.titleMedium,
                color = if (completed || expired) colors.muted else colors.ink,
                textDecoration = if (completed || expired) TextDecoration.LineThrough else null,
            )
            Text(
                meta,
                style = MaterialTheme.typography.bodyMedium,
                color = colors.muted,
                maxLines = if (event != null) 3 else 1,
                overflow = TextOverflow.Ellipsis,
            )
            if (event != null && !completed && !expired) EventLink(event)
        }
        Text(
            stringResource(R.string.quest_points, quest.pointsAwarded ?: quest.basePoints),
            style = MaterialTheme.typography.titleMedium,
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
