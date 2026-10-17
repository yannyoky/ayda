package app.ayda.android.ui.onboarding

import android.app.TimePickerDialog
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
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
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import app.ayda.android.R
import app.ayda.android.ui.Card
import app.ayda.android.ui.LocalAydaColors
import app.ayda.android.ui.PrimaryButton
import app.ayda.android.ui.QuietButton
import app.ayda.api.models.HabitDirection
import app.ayda.api.models.Theme
import app.ayda.shared.onboarding.OnboardingState
import app.ayda.shared.onboarding.OnboardingStep
import app.ayda.shared.onboarding.OnboardingViewModel

/** US-02: name (email users), city, goals, own habits, reminder times and theme. */
@Composable
fun OnboardingScreen(model: OnboardingViewModel) {
    val state by model.state.collectAsStateWithLifecycle()
    val colors = LocalAydaColors.current
    val texts = state.step.texts()
    Column(
        modifier =
            Modifier
                .fillMaxSize()
                .background(colors.bg)
                .safeDrawingPadding()
                .imePadding()
                .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Progress(state, onBack = model::back)
        Text(stringResource(texts.first), style = MaterialTheme.typography.headlineLarge)
        Text(stringResource(texts.second), style = MaterialTheme.typography.bodyLarge, color = colors.muted)
        Column(
            modifier = Modifier.weight(1f).verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            when (state.step) {
                OnboardingStep.Name -> NameStep(state, model)
                OnboardingStep.City -> CityStep(state, model)
                OnboardingStep.Goals -> GoalsStep(state, model)
                OnboardingStep.Habits -> HabitsStep(state, model)
                OnboardingStep.Reminders -> RemindersStep(state, model)
                OnboardingStep.Theme -> ThemeStep(state, model)
            }
            state.error?.let { Text(it, style = MaterialTheme.typography.bodyMedium) }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
            if (state.step.skippable) {
                QuietButton(stringResource(R.string.onboarding_skip), onClick = model::skip)
            }
            PrimaryButton(
                stringResource(if (state.isLast) R.string.onboarding_finish else R.string.onboarding_next),
                onClick = model::next,
                enabled = state.ready,
                modifier = Modifier.weight(1f),
            )
        }
    }
}

private fun OnboardingStep.texts(): Pair<Int, Int> =
    when (this) {
        OnboardingStep.Name -> R.string.onboarding_name_title to R.string.onboarding_name_text
        OnboardingStep.City -> R.string.onboarding_city_title to R.string.onboarding_city_text
        OnboardingStep.Goals -> R.string.onboarding_goals_title to R.string.onboarding_goals_text
        OnboardingStep.Habits -> R.string.onboarding_habits_title to R.string.onboarding_habits_text
        OnboardingStep.Reminders -> R.string.onboarding_reminders_title to R.string.onboarding_reminders_text
        OnboardingStep.Theme -> R.string.onboarding_theme_title to R.string.onboarding_theme_text
    }

@Composable
private fun Progress(
    state: OnboardingState,
    onBack: () -> Unit,
) {
    val colors = LocalAydaColors.current
    val label = stringResource(R.string.onboarding_progress, state.index + 1, state.steps.size)
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        if (state.index > 0) {
            QuietButton(stringResource(R.string.onboarding_back), onClick = onBack)
        }
        Row(
            modifier = Modifier.weight(1f).semantics { contentDescription = label },
            horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            state.steps.indices.forEach { i ->
                Box(
                    Modifier
                        .weight(1f)
                        .height(6.dp)
                        .background(if (i <= state.index) colors.ink else colors.track, CircleShape),
                )
            }
        }
    }
}

@Composable
private fun NameStep(
    state: OnboardingState,
    model: OnboardingViewModel,
) {
    TextInput(
        value = state.name,
        onValueChange = model::onNameChange,
        label = stringResource(R.string.onboarding_name_label),
        onDone = model::next,
        capitalization = KeyboardCapitalization.Words,
    )
}

@Composable
private fun CityStep(
    state: OnboardingState,
    model: OnboardingViewModel,
) {
    val colors = LocalAydaColors.current
    state.me.city?.let { city ->
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
        onValueChange = model::onCityQueryChange,
        label = stringResource(R.string.onboarding_city_search),
        onDone = {},
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
        Card(modifier = Modifier.clickable { model.pickCity(city) }) {
            Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(city.name, style = MaterialTheme.typography.titleMedium)
                Text(city.regionName, style = MaterialTheme.typography.bodyMedium, color = colors.muted)
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun GoalsStep(
    state: OnboardingState,
    model: OnboardingViewModel,
) {
    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        state.goals.forEach { goal ->
            Chip(goal.title, selected = goal.code in state.selectedGoals) { model.toggleGoal(goal.code) }
        }
    }
    if (state.selectedGoals.size >= 5) {
        Text(
            stringResource(R.string.onboarding_goals_limit),
            style = MaterialTheme.typography.bodyMedium,
            color = LocalAydaColors.current.muted,
        )
    }
}

@Composable
private fun HabitsStep(
    state: OnboardingState,
    model: OnboardingViewModel,
) {
    HabitGroup(state, model, HabitDirection.more, R.string.onboarding_habits_more, R.string.onboarding_habits_more_hint)
    HabitGroup(state, model, HabitDirection.less, R.string.onboarding_habits_less, R.string.onboarding_habits_less_hint)
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun HabitGroup(
    state: OnboardingState,
    model: OnboardingViewModel,
    direction: HabitDirection,
    title: Int,
    hint: Int,
) {
    var draft by remember(direction) { mutableStateOf("") }
    val add = {
        model.addHabit(direction, draft)
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
                ) { model.removeHabit(habit) }
            }
        }
        TextInput(value = draft, onValueChange = { draft = it.take(100) }, label = stringResource(hint), onDone = add)
        QuietButton(stringResource(R.string.onboarding_habits_add), onClick = add)
    }
}

@Composable
private fun RemindersStep(
    state: OnboardingState,
    model: OnboardingViewModel,
) {
    ReminderRow(
        stringResource(R.string.onboarding_reminders_morning),
        state.reminders.morningAt,
        "08:30",
        model::setMorning,
    )
    ReminderRow(
        stringResource(R.string.onboarding_reminders_evening),
        state.reminders.eveningAt,
        "20:30",
        model::setEvening,
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
private fun ThemeStep(
    state: OnboardingState,
    model: OnboardingViewModel,
) {
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Chip(stringResource(R.string.theme_graphite), selected = state.me.theme == Theme.graphite) {
            model.pickTheme(Theme.graphite)
        }
        Chip(
            stringResource(R.string.theme_plum),
            selected = state.me.theme == Theme.plum,
        ) { model.pickTheme(Theme.plum) }
    }
}

@Composable
private fun Chip(
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
private fun TextInput(
    value: String,
    onValueChange: (String) -> Unit,
    label: String,
    onDone: () -> Unit,
    capitalization: KeyboardCapitalization = KeyboardCapitalization.Sentences,
) {
    OutlinedTextField(
        value = value,
        onValueChange = onValueChange,
        label = { Text(label) },
        singleLine = true,
        shape = MaterialTheme.shapes.medium,
        keyboardOptions = KeyboardOptions(capitalization = capitalization, imeAction = ImeAction.Done),
        keyboardActions = KeyboardActions(onDone = { onDone() }),
        modifier = Modifier.fillMaxWidth(),
    )
}
