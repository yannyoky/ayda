package app.ayda.android.ui.day

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import app.ayda.android.R
import app.ayda.android.ui.LocalAydaColors
import app.ayda.android.ui.PrimaryButton
import app.ayda.android.ui.profile.Chip
import app.ayda.android.ui.profile.TextInput
import app.ayda.api.models.Category
import app.ayda.shared.day.TodayState
import app.ayda.shared.day.TodayViewModel

/** US-08: a quest the user words themselves; it is taken right away. */
@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
fun OwnQuestSheet(
    state: TodayState,
    model: TodayViewModel,
    onAdded: () -> Unit = {},
) {
    val draft = state.ownQuest ?: return
    val colors = LocalAydaColors.current
    ModalBottomSheet(onDismissRequest = model::closeOwnQuest, containerColor = colors.bg) {
        Column(
            Modifier.padding(horizontal = 16.dp).padding(bottom = 16.dp).navigationBarsPadding(),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Text(stringResource(R.string.own_title), style = MaterialTheme.typography.headlineSmall)
            TextInput(
                value = draft.title,
                onValueChange = { title -> model.editOwnQuest { it.copy(title = title) } },
                label = stringResource(R.string.own_name),
                placeholder = stringResource(R.string.own_name_placeholder),
            )
            Text(stringResource(R.string.own_category), style = MaterialTheme.typography.titleMedium)
            FlowRow(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Category.entries.forEach { category ->
                    Chip(stringResource(category.label()), selected = draft.category == category) {
                        model.editOwnQuest { it.copy(category = category) }
                    }
                }
            }
            Text(stringResource(R.string.own_duration), style = MaterialTheme.typography.titleMedium)
            FlowRow(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                TodayViewModel.DURATIONS.forEach { minutes ->
                    Chip(stringResource(R.string.quest_minutes, minutes), selected = draft.durationMin == minutes) {
                        model.editOwnQuest { it.copy(durationMin = minutes) }
                    }
                }
            }
            state.error?.let { Text(it, style = MaterialTheme.typography.labelLarge) }
            PrimaryButton(
                stringResource(R.string.own_add),
                onClick = { model.addOwnQuest(onAdded) },
                enabled = draft.canAdd && !state.busy,
            )
        }
    }
}
