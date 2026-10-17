package app.ayda.android.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import app.ayda.android.R
import app.ayda.api.models.Theme

/** Placeholder start screen: shows the theme and fonts until sign-in lands (#93). */
@Composable
fun WelcomeScreen(
    theme: Theme,
    onThemeChange: (Theme) -> Unit,
) {
    val colors = LocalAydaColors.current
    Column(
        modifier =
            Modifier
                .fillMaxSize()
                .background(colors.bg)
                .safeDrawingPadding()
                .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Column(
            modifier =
                Modifier
                    .fillMaxWidth()
                    .background(colors.plate, MaterialTheme.shapes.large)
                    .padding(24.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text(
                stringResource(R.string.scaffold_title),
                style = MaterialTheme.typography.displayLarge,
                color = colors.accent,
            )
            Text(
                stringResource(R.string.tagline),
                style = MaterialTheme.typography.headlineSmall,
                color = colors.onPlate,
            )
        }
        Column(
            modifier =
                Modifier
                    .fillMaxWidth()
                    .background(colors.surface, MaterialTheme.shapes.large)
                    .padding(24.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Text(stringResource(R.string.scaffold_body), style = MaterialTheme.typography.bodyLarge, color = colors.ink)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                ThemeChip(Theme.graphite, R.string.theme_graphite, theme, onThemeChange)
                ThemeChip(Theme.plum, R.string.theme_plum, theme, onThemeChange)
            }
        }
    }
}

@Composable
private fun ThemeChip(
    value: Theme,
    label: Int,
    current: Theme,
    onSelect: (Theme) -> Unit,
) {
    val colors = LocalAydaColors.current
    FilterChip(
        selected = value == current,
        onClick = { onSelect(value) },
        label = { Text(stringResource(label), style = MaterialTheme.typography.labelLarge) },
        shape = MaterialTheme.shapes.medium,
        colors =
            FilterChipDefaults.filterChipColors(
                containerColor = colors.bg,
                labelColor = colors.ink,
                selectedContainerColor = colors.accent,
                selectedLabelColor = colors.onAccent,
            ),
    )
}

@Preview
@Composable
private fun WelcomePlumPreview() {
    AydaTheme(Theme.plum) { WelcomeScreen(Theme.plum) {} }
}
