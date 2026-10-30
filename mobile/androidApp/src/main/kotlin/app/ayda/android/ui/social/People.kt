package app.ayda.android.ui.social

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import app.ayda.android.R
import app.ayda.android.ui.LocalAydaColors
import app.ayda.android.ui.Unbounded
import app.ayda.android.ui.day.Russian
import app.ayda.api.models.UserSummary
import app.ayda.shared.AvatarTints
import coil3.compose.AsyncImage
import coil3.request.CachePolicy
import coil3.request.ImageRequest
import java.text.BreakIterator
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import kotlin.time.Clock
import kotlin.time.Instant

/**
 * A request for a photo behind a short-lived signed URL: kept in memory only, because the
 * URL changes on every load and people's photos have no business in the disk cache.
 */
@Composable
fun privateImage(url: String): ImageRequest =
    ImageRequest
        .Builder(LocalContext.current)
        .data(url)
        .diskCachePolicy(CachePolicy.DISABLED)
        .build()

/** First user-perceived character, so an emoji or a combined letter is never cut in half. */
fun initial(name: String): String {
    val trimmed = name.trim()
    if (trimmed.isEmpty()) return "?"
    val breaks = BreakIterator.getCharacterInstance(Russian)
    breaks.setText(trimmed)
    return trimmed.substring(0, breaks.next()).uppercase(Russian)
}

/**
 * The Telegram avatar, or the first character on one of six tints (docs/design/themes.md) when
 * there is none or it fails to load. The tint comes from the user id, so a friend keeps one colour.
 */
@Composable
fun Avatar(
    user: UserSummary,
    size: Int = 40,
) {
    val colors = LocalAydaColors.current
    val shape = RoundedCornerShape((size * 0.35f).dp)
    val url = user.avatarUrl
    var broken by remember(url) { mutableStateOf(false) }
    if (url != null && !broken) {
        AsyncImage(
            model = privateImage(url),
            contentDescription = null,
            contentScale = ContentScale.Crop,
            onError = { broken = true },
            modifier = Modifier.size(size.dp).clip(shape).background(colors.plate),
        )
    } else {
        val (tile, letter) = colors.avatars[AvatarTints.indexOf(user.id)]
        Box(Modifier.size(size.dp).background(tile, shape), contentAlignment = Alignment.Center) {
            Text(
                initial(user.firstName),
                style = TextStyle(fontFamily = Unbounded, fontWeight = FontWeight.Bold, fontSize = (size * 0.4f).sp),
                color = letter,
                maxLines = 1,
            )
        }
    }
}

private val shortDate = DateTimeFormatter.ofPattern("d MMM", Russian)

/** "20 минут назад", "вчера", or a date for anything older than a week. */
@Composable
fun formatAgo(
    instant: Instant,
    now: Instant = Clock.System.now(),
): String {
    val seconds = (now - instant).inWholeSeconds.coerceAtLeast(0)
    return when {
        seconds < MINUTE -> stringResource(R.string.time_just_now)
        seconds < HOUR -> (seconds / MINUTE).toInt().let { pluralStringResource(R.plurals.time_minutes_ago, it, it) }
        seconds < DAY -> (seconds / HOUR).toInt().let { pluralStringResource(R.plurals.time_hours_ago, it, it) }
        seconds < 2 * DAY -> stringResource(R.string.time_yesterday)
        seconds < WEEK -> (seconds / DAY).toInt().let { pluralStringResource(R.plurals.time_days_ago, it, it) }
        else ->
            shortDate.format(
                java.time.Instant
                    .ofEpochMilli(instant.toEpochMilliseconds())
                    .atZone(ZoneId.systemDefault()),
            )
    }
}

private const val MINUTE = 60L
private const val HOUR = 60 * MINUTE
private const val DAY = 24 * HOUR
private const val WEEK = 7 * DAY
