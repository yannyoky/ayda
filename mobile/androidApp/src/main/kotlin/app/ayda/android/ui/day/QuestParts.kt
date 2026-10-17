package app.ayda.android.ui.day

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import app.ayda.android.R
import app.ayda.android.ui.LocalAydaColors
import app.ayda.api.models.Category
import app.ayda.api.models.EventInfo
import java.text.NumberFormat
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

val Russian: Locale = Locale.forLanguageTag("ru-RU")

fun Category.icon(): Int =
    when (this) {
        Category.sport -> R.drawable.ic_sport
        Category.walk -> R.drawable.ic_walk
        Category.city -> R.drawable.ic_city
        Category.rest -> R.drawable.ic_rest
        Category.project -> R.drawable.ic_project
        Category.social -> R.drawable.ic_social
        Category.home -> R.drawable.ic_home
        Category.learning -> R.drawable.ic_learning
    }

fun Category.label(): Int =
    when (this) {
        Category.sport -> R.string.category_sport
        Category.walk -> R.string.category_walk
        Category.city -> R.string.category_city
        Category.rest -> R.string.category_rest
        Category.project -> R.string.category_project
        Category.social -> R.string.category_social
        Category.home -> R.string.category_home
        Category.learning -> R.string.category_learning
    }

/** A 24-dp stroke icon from the design canvas, tinted with the given color. */
@Composable
fun AydaIcon(
    icon: Int,
    tint: Color,
    modifier: Modifier = Modifier,
    size: Int = 20,
    contentDescription: String? = null,
) = Icon(painterResource(icon), contentDescription = contentDescription, tint = tint, modifier = modifier.size(size.dp))

@Composable
fun CategoryTile(
    category: Category,
    background: Color = LocalAydaColors.current.bg,
    tint: Color = LocalAydaColors.current.ink,
) {
    Box(
        Modifier.size(44.dp).background(background, MaterialTheme.shapes.small),
        contentAlignment = Alignment.Center,
    ) { AydaIcon(category.icon(), tint) }
}

private val clock = DateTimeFormatter.ofPattern("HH:mm", Russian)

/** "в 19:00 · Дом искусств · Советск · Бесплатно" (US-19: place, time, price). */
@Composable
fun eventSummary(event: EventInfo): String {
    val starts =
        java.time.Instant
            .ofEpochMilli(event.startsAt.toEpochMilliseconds())
            .atZone(ZoneId.systemDefault())
    val price =
        when {
            event.isFree -> stringResource(R.string.event_free)
            event.priceMin != null ->
                stringResource(R.string.event_from, NumberFormat.getIntegerInstance(Russian).format(event.priceMin))
            else -> stringResource(R.string.event_paid)
        }
    return listOfNotNull(
        stringResource(R.string.event_at, clock.format(starts)),
        event.venue ?: event.address,
        event.city,
        price,
    ).joinToString(" · ")
}

fun EventInfo.Source.title(): String =
    when (this) {
        EventInfo.Source.timepad -> "Timepad"
        EventInfo.Source.kudago -> "KudaGo"
        EventInfo.Source.culture -> "Культура.РФ"
    }

/** Opens the event page at its source in the browser and names the source (ADR 0008). */
@Composable
fun EventLink(
    event: EventInfo,
    color: Color = LocalAydaColors.current.ink,
) {
    val uri = LocalUriHandler.current
    TextButton(onClick = { runCatching { uri.openUri(event.url) } }) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                stringResource(R.string.event_open, event.source.title()),
                style = MaterialTheme.typography.labelLarge,
                color = color,
            )
            Spacer(Modifier.width(4.dp))
            AydaIcon(R.drawable.ic_external, color, size = 14)
        }
    }
}
