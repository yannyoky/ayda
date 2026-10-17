package app.ayda.android.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import app.ayda.android.R
import app.ayda.android.ui.day.AydaIcon

enum class Tab(
    val icon: Int,
    val label: Int,
) {
    Today(R.drawable.ic_today, R.string.nav_today),
    Feed(R.drawable.ic_feed, R.string.nav_feed),
    Friends(R.drawable.ic_friends, R.string.nav_friends),
    Profile(R.drawable.ic_profile, R.string.nav_profile),
}

/** The dark pill at the bottom; the open tab shows its name on the accent. */
@Composable
fun TabBar(
    current: Tab,
    onSelect: (Tab) -> Unit,
) {
    val colors = LocalAydaColors.current
    Row(
        Modifier
            .fillMaxWidth()
            .background(colors.bg)
            .navigationBarsPadding()
            .padding(16.dp, 8.dp)
            .height(64.dp)
            .background(colors.plate, MaterialTheme.shapes.extraLarge)
            .padding(horizontal = 8.dp),
        horizontalArrangement = Arrangement.SpaceAround,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Tab.entries.forEach { tab ->
            val active = tab == current
            val label = stringResource(tab.label)
            Box(
                Modifier
                    .height(48.dp)
                    .clip(MaterialTheme.shapes.extraLarge)
                    .background(if (active) colors.accent else colors.plate)
                    .clickable(role = Role.Tab, onClickLabel = label) { onSelect(tab) }
                    .padding(horizontal = if (active) 16.dp else 13.dp),
                contentAlignment = Alignment.Center,
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    AydaIcon(
                        tab.icon,
                        if (active) colors.onAccent else colors.onPlate,
                        size = if (active) 20 else 22,
                        contentDescription = if (active) null else label,
                    )
                    if (active) {
                        Spacer(Modifier.width(6.dp))
                        Text(label, style = MaterialTheme.typography.titleMedium, color = colors.onAccent)
                    }
                }
            }
        }
    }
}
