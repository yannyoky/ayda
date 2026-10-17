package app.ayda.android.ui.social

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
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
import coil3.compose.AsyncImage
import coil3.request.CachePolicy
import coil3.request.ImageRequest
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

/** The Telegram avatar, or the first letter on a plate when there is none. */
@Composable
fun Avatar(
    user: UserSummary,
    size: Int = 40,
) {
    val colors = LocalAydaColors.current
    val shape = RoundedCornerShape((size * 0.35f).dp)
    val url = user.avatarUrl
    if (url != null) {
        AsyncImage(
            model = privateImage(url),
            contentDescription = null,
            contentScale = ContentScale.Crop,
            modifier = Modifier.size(size.dp).clip(shape).background(colors.plate),
        )
    } else {
        Box(Modifier.size(size.dp).background(colors.plate, shape), contentAlignment = Alignment.Center) {
            Text(
                user.firstName.take(1).uppercase(Russian),
                style = TextStyle(fontFamily = Unbounded, fontWeight = FontWeight.Bold, fontSize = (size * 0.36f).sp),
                color = colors.accent,
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
