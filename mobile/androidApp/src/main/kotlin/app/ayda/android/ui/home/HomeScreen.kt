package app.ayda.android.ui.home

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import app.ayda.android.R
import app.ayda.android.ui.Card
import app.ayda.android.ui.LocalAydaColors
import app.ayda.android.ui.QuietButton
import app.ayda.api.models.Me

/** Placeholder until onboarding and the Today screen land (#93, #94). */
@Composable
fun HomeScreen(
    me: Me,
    onOpenProfile: () -> Unit,
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
        Card(color = colors.plate) {
            Text(
                if (me.firstName.isBlank()) {
                    stringResource(
                        R.string.hello,
                    )
                } else {
                    stringResource(R.string.hello_name, me.firstName)
                },
                style = MaterialTheme.typography.headlineLarge,
                color = colors.onPlate,
            )
            Text(
                stringResource(R.string.scaffold_body),
                style = MaterialTheme.typography.bodyLarge,
                color = colors.onPlate,
            )
        }
        QuietButton(stringResource(R.string.profile_open), onClick = onOpenProfile)
    }
}
