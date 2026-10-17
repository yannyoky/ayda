package app.ayda.shared

import app.ayda.api.models.Theme

/**
 * Colour tokens of the two themes, as in docs/design/themes.md.
 * Values are ARGB so both Compose and SwiftUI can use them.
 */
data class Palette(
    val bg: Long,
    val surface: Long,
    val plate: Long,
    val plate2: Long,
    val ink: Long,
    val muted: Long,
    val track: Long,
    val accent: Long,
    val onPlate: Long,
    val onAccent: Long,
)

object Palettes {
    val Graphite =
        Palette(
            bg = 0xFFE9E9E7,
            surface = 0xFFFFFFFF,
            plate = 0xFF222326,
            plate2 = 0xFF34363B,
            ink = 0xFF18191B,
            muted = 0xFF5B5D62,
            track = 0xFFD6D6D3,
            accent = 0xFFFF5FA2,
            onPlate = 0xFFFFFFFF,
            onAccent = 0xFF18191B,
        )

    val Plum =
        Palette(
            bg = 0xFFF1E9E4,
            surface = 0xFFFFFFFF,
            plate = 0xFF3B1E3F,
            plate2 = 0xFF553258,
            ink = 0xFF2A1830,
            muted = 0xFF6E5A69,
            track = 0xFFE6D7D2,
            accent = 0xFFFF9E7A,
            onPlate = 0xFFFFFFFF,
            onAccent = 0xFF2A1830,
        )

    fun of(theme: Theme): Palette =
        when (theme) {
            Theme.graphite -> Graphite
            Theme.plum -> Plum
        }
}

/** Corner radii in dp/pt. */
object Radii {
    const val CARD = 28
    const val ICON_TILE = 14
    const val FIELD = 16
    const val TAB_BAR = 32
}
