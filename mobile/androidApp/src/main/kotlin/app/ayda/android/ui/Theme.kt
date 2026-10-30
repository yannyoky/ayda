package app.ayda.android.ui

import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.ColorScheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.Typography
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.ExperimentalTextApi
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontVariation
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import app.ayda.android.R
import app.ayda.api.models.Theme
import app.ayda.shared.Palette
import app.ayda.shared.Palettes
import app.ayda.shared.Radii

/** Every token of docs/design/themes.md, for places Material roles don't cover (plates, tracks). */
@Immutable
data class AydaColors(
    val bg: Color,
    val surface: Color,
    val plate: Color,
    val plate2: Color,
    val ink: Color,
    val muted: Color,
    val track: Color,
    val accent: Color,
    val onPlate: Color,
    val onAccent: Color,
    /** Letter avatar tints as (tile, letter), picked per user with [app.ayda.shared.AvatarTints]. */
    val avatars: List<Pair<Color, Color>>,
)

fun Palette.toColors() =
    AydaColors(
        bg = Color(bg),
        surface = Color(surface),
        plate = Color(plate),
        plate2 = Color(plate2),
        ink = Color(ink),
        muted = Color(muted),
        track = Color(track),
        accent = Color(accent),
        onPlate = Color(onPlate),
        onAccent = Color(onAccent),
        avatars = avatars.map { Color(it.tile) to Color(it.letter) },
    )

fun AydaColors.toColorScheme(): ColorScheme =
    lightColorScheme(
        primary = accent,
        onPrimary = onAccent,
        background = bg,
        onBackground = ink,
        surface = surface,
        onSurface = ink,
        surfaceVariant = track,
        onSurfaceVariant = muted,
        inverseSurface = plate,
        inverseOnSurface = onPlate,
        outline = muted,
    )

@OptIn(ExperimentalTextApi::class)
private fun variable(
    res: Int,
    weight: Int,
) = Font(res, FontWeight(weight), variationSettings = FontVariation.Settings(FontVariation.weight(weight)))

/** Headings and big numbers. */
val Unbounded =
    FontFamily(variable(R.font.unbounded, 500), variable(R.font.unbounded, 700), variable(R.font.unbounded, 800))

/** Body text. */
val Manrope =
    FontFamily(
        variable(R.font.manrope, 500),
        variable(R.font.manrope, 600),
        variable(R.font.manrope, 700),
        variable(R.font.manrope, 800),
    )

private val AydaTypography =
    Typography(
        displayLarge =
            TextStyle(
                fontFamily = Unbounded,
                fontWeight = FontWeight.ExtraBold,
                fontSize = 44.sp,
                lineHeight = 48.sp,
            ),
        headlineLarge =
            TextStyle(
                fontFamily = Unbounded,
                fontWeight = FontWeight.Bold,
                fontSize = 28.sp,
                lineHeight = 34.sp,
            ),
        headlineSmall =
            TextStyle(
                fontFamily = Unbounded,
                fontWeight = FontWeight.Bold,
                fontSize = 20.sp,
                lineHeight = 26.sp,
            ),
        titleMedium =
            TextStyle(
                fontFamily = Manrope,
                fontWeight = FontWeight.Bold,
                fontSize = 16.sp,
                lineHeight = 22.sp,
            ),
        bodyLarge =
            TextStyle(
                fontFamily = Manrope,
                fontWeight = FontWeight.Medium,
                fontSize = 16.sp,
                lineHeight = 24.sp,
            ),
        bodyMedium =
            TextStyle(
                fontFamily = Manrope,
                fontWeight = FontWeight.Medium,
                fontSize = 14.sp,
                lineHeight = 20.sp,
            ),
        labelLarge =
            TextStyle(
                fontFamily = Manrope,
                fontWeight = FontWeight.SemiBold,
                fontSize = 14.sp,
                lineHeight = 20.sp,
            ),
    )

private val AydaShapes =
    Shapes(
        small = RoundedCornerShape(Radii.ICON_TILE.dp),
        medium = RoundedCornerShape(Radii.FIELD.dp),
        large = RoundedCornerShape(Radii.CARD.dp),
        extraLarge = RoundedCornerShape(Radii.TAB_BAR.dp),
    )

val LocalAydaColors = staticCompositionLocalOf { Palettes.Graphite.toColors() }

@Composable
fun AydaTheme(
    theme: Theme,
    content: @Composable () -> Unit,
) {
    val colors = Palettes.of(theme).toColors()
    CompositionLocalProvider(LocalAydaColors provides colors) {
        MaterialTheme(
            colorScheme = colors.toColorScheme(),
            typography = AydaTypography,
            shapes = AydaShapes,
            content = content,
        )
    }
}
