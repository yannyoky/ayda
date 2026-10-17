package app.ayda.android.ui.onboarding

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import app.ayda.android.R
import app.ayda.android.ui.LocalAydaColors
import app.ayda.android.ui.PrimaryButton
import app.ayda.android.ui.QuietButton
import app.ayda.android.ui.profile.CityEditor
import app.ayda.android.ui.profile.GoalsEditor
import app.ayda.android.ui.profile.HabitsEditor
import app.ayda.android.ui.profile.RemindersEditor
import app.ayda.android.ui.profile.TextInput
import app.ayda.android.ui.profile.ThemePicker
import app.ayda.shared.onboarding.OnboardingState
import app.ayda.shared.onboarding.OnboardingStep
import app.ayda.shared.onboarding.OnboardingViewModel

/** US-02: name (email users), city, goals, own habits, reminder times and theme. */
@Composable
fun OnboardingScreen(model: OnboardingViewModel) {
    val state by model.state.collectAsStateWithLifecycle()
    val editor by model.editor.state.collectAsStateWithLifecycle()
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
                OnboardingStep.Name ->
                    TextInput(
                        value = state.name,
                        onValueChange = model::onNameChange,
                        label = stringResource(R.string.onboarding_name_label),
                        onDone = model::next,
                        capitalization = KeyboardCapitalization.Words,
                    )
                OnboardingStep.City -> CityEditor(state.me.city, editor, model.editor)
                OnboardingStep.Goals -> GoalsEditor(editor, model.editor)
                OnboardingStep.Habits -> HabitsEditor(editor, model.editor)
                OnboardingStep.Reminders -> RemindersEditor(editor, model.editor)
                OnboardingStep.Theme -> ThemePicker(state.me.theme, model.editor)
            }
            (state.error ?: editor.error)?.let { Text(it, style = MaterialTheme.typography.bodyMedium) }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
            if (state.step.skippable) {
                QuietButton(stringResource(R.string.onboarding_skip), onClick = model::skip)
            }
            PrimaryButton(
                stringResource(if (state.isLast) R.string.onboarding_finish else R.string.onboarding_next),
                onClick = model::next,
                enabled = state.ready && !editor.busy,
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
