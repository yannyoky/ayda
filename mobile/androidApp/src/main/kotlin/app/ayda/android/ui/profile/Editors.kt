package app.ayda.android.ui.profile

import android.app.TimePickerDialog
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import app.ayda.android.R
import app.ayda.android.ui.Card
import app.ayda.android.ui.LocalAydaColors
import app.ayda.android.ui.QuietButton
import app.ayda.api.models.City
import app.ayda.api.models.HabitDirection
import app.ayda.api.models.Theme
import app.ayda.shared.profile.EditorState
import app.ayda.shared.profile.ProfileEditor

/** Editors shared by onboarding and the profile screen. */

@Composable
fun CityEditor(
    selected: City?,
    state: EditorState,
    editor: ProfileEditor,
    onPicked: () -> Unit = {},
) {
    val colors = LocalAydaColors.current
    selected?.let { city ->
        Card(color = colors.plate) {
            Text(
                stringResource(R.string.onboarding_city_selected),
                style = MaterialTheme.typography.labelLarge,
                color = colors.accent,
            )
            Text(city.name, style = MaterialTheme.typography.headlineSmall, color = colors.onPlate)
            if (city.regionName.isNotBlank()) {
                Text(city.regionName, style = MaterialTheme.typography.bodyMedium, color = colors.onPlate)
            }
        }
    }
    TextInput(
        value = state.cityQuery,
        onValueChange = editor::onCityQueryChange,
        label = stringResource(R.string.onboarding_city_search),
        capitalization = KeyboardCapitalization.Words,
    )
    if (state.cityQuery.trim().length >= 2 && !state.searching && state.cities.isEmpty() && state.error == null) {
        Text(
            stringResource(R.string.onboarding_city_nothing),
            style = MaterialTheme.typography.bodyMedium,
            color = colors.muted,
        )
    }
    state.cities.forEach { city ->
        Card(modifier = Modifier.clickable { editor.pickCity(city, onPicked) }) {
            Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(city.name, style = MaterialTheme.typography.titleMedium)
                Text(city.regionName, style = MaterialTheme.typography.bodyMedium, color = colors.muted)
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun GoalsEditor(
    state: EditorState,
    editor: ProfileEditor,
) {
    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        state.goals.forEach { goal ->
            Chip(goal.title, selected = goal.code in state.selectedGoals) { editor.toggleGoal(goal.code) }
        }
    }
    if (state.goalLimitReached) {
        Text(
            stringResource(R.string.onboarding_goals_limit),
            style = MaterialTheme.typography.bodyMedium,
            color = LocalAydaColors.current.muted,
        )
    }
}

@Composable
fun HabitsEditor(
    state: EditorState,
    editor: ProfileEditor,
) {
    HabitGroup(
        state,
        editor,
        HabitDirection.more,
        R.string.onboarding_habits_more,
        R.string.onboarding_habits_more_hint,
    )
    HabitGroup(
        state,
        editor,
        HabitDirection.less,
        R.string.onboarding_habits_less,
        R.string.onboarding_habits_less_hint,
    )
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun HabitGroup(
    state: EditorState,
    editor: ProfileEditor,
    direction: HabitDirection,
    title: Int,
    hint: Int,
) {
    var draft by remember(direction) { mutableStateOf("") }
    val add = {
        editor.addHabit(direction, draft)
        draft = ""
    }
    Card {
        Text(stringResource(title), style = MaterialTheme.typography.titleMedium)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            state.habits.filter { it.direction == direction }.forEach { habit ->
                val remove = stringResource(R.string.onboarding_habits_remove, habit.text)
                Chip(
                    "${habit.text}  ✕",
                    selected = true,
                    modifier = Modifier.semantics { contentDescription = remove },
                ) { editor.removeHabit(habit) }
            }
        }
        TextInput(value = draft, onValueChange = { draft = it.take(100) }, label = stringResource(hint), onDone = add)
        QuietButton(stringResource(R.string.onboarding_habits_add), onClick = add)
    }
}

@Composable
fun RemindersEditor(
    state: EditorState,
    editor: ProfileEditor,
) {
    ReminderRow(
        stringResource(R.string.onboarding_reminders_morning),
        state.reminders.morningAt,
        "08:30",
        editor::setMorning,
    )
    ReminderRow(
        stringResource(R.string.onboarding_reminders_evening),
        state.reminders.eveningAt,
        "20:30",
        editor::setEvening,
    )
}

@Composable
private fun ReminderRow(
    label: String,
    time: String?,
    fallback: String,
    onChange: (String?) -> Unit,
) {
    val colors = LocalAydaColors.current
    val context = LocalContext.current
    Card {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(label, style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
            if (time != null) {
                val (hour, minute) = time.split(":").map(String::toInt)
                QuietButton(time, onClick = {
                    TimePickerDialog(
                        context,
                        { _, h, m -> onChange("%02d:%02d".format(h, m)) },
                        hour,
                        minute,
                        true,
                    ).show()
                })
            } else {
                Text(
                    stringResource(R.string.onboarding_reminders_off),
                    style = MaterialTheme.typography.bodyMedium,
                    color = colors.muted,
                )
            }
            Switch(
                checked = time != null,
                onCheckedChange = { onChange(if (it) fallback else null) },
                colors = SwitchDefaults.colors(checkedTrackColor = colors.plate, checkedThumbColor = colors.surface),
            )
        }
    }
}

@Composable
fun ThemePicker(
    current: Theme,
    editor: ProfileEditor,
) {
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Chip(
            stringResource(R.string.theme_graphite),
            selected = current == Theme.graphite,
        ) { editor.pickTheme(Theme.graphite) }
        Chip(stringResource(R.string.theme_plum), selected = current == Theme.plum) { editor.pickTheme(Theme.plum) }
    }
}

@Composable
fun Chip(
    text: String,
    selected: Boolean,
    modifier: Modifier = Modifier,
    onClick: () -> Unit,
) {
    val colors = LocalAydaColors.current
    FilterChip(
        selected = selected,
        onClick = onClick,
        label = { Text(text, style = MaterialTheme.typography.labelLarge) },
        shape = MaterialTheme.shapes.medium,
        modifier = modifier,
        colors =
            FilterChipDefaults.filterChipColors(
                containerColor = colors.surface,
                labelColor = colors.ink,
                selectedContainerColor = colors.accent,
                selectedLabelColor = colors.onAccent,
            ),
    )
}

@Composable
fun TextInput(
    value: String,
    onValueChange: (String) -> Unit,
    label: String,
    onDone: () -> Unit = {},
    capitalization: KeyboardCapitalization = KeyboardCapitalization.Sentences,
    keyboardType: KeyboardType = KeyboardType.Text,
) {
    OutlinedTextField(
        value = value,
        onValueChange = onValueChange,
        label = { Text(label) },
        singleLine = true,
        shape = MaterialTheme.shapes.medium,
        keyboardOptions =
            KeyboardOptions(
                capitalization = capitalization,
                keyboardType = keyboardType,
                imeAction = ImeAction.Done,
            ),
        keyboardActions = KeyboardActions(onDone = { onDone() }),
        modifier = Modifier.fillMaxWidth(),
    )
}
