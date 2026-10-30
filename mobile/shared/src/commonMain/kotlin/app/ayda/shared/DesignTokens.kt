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
    /** Letter avatar tints: tile and letter colour, six of them (docs/design/themes.md). */
    val avatars: List<AvatarTint>,
)

data class AvatarTint(
    val tile: Long,
    val letter: Long,
)

/** Picks one of the six tints for a user, the same way as the Mini App, so a friend has one colour everywhere. */
object AvatarTints {
    const val COUNT = 6

    /** 0-based tint index from the user id (FNV-1a over UTF-16 code units, as in miniapp/src/ui/avatarTint.ts). */
    fun indexOf(key: String): Int {
        var hash = 0x811c9dc5.toInt()
        for (c in key) hash = (hash xor c.code) * 0x01000193
        return (hash.toUInt() % COUNT.toUInt()).toInt()
    }
}

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
            avatars =
                listOf(
                    AvatarTint(0xFF222326, 0xFFFF5FA2),
                    AvatarTint(0xFFFF5FA2, 0xFF18191B),
                    AvatarTint(0xFFFFD25E, 0xFF18191B),
                    AvatarTint(0xFF8EC5FF, 0xFF18191B),
                    AvatarTint(0xFFA8E0A0, 0xFF18191B),
                    AvatarTint(0xFFC9B6FF, 0xFF18191B),
                ),
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
            avatars =
                listOf(
                    AvatarTint(0xFF3B1E3F, 0xFFFF9E7A),
                    AvatarTint(0xFFFF9E7A, 0xFF2A1830),
                    AvatarTint(0xFFF6C977, 0xFF2A1830),
                    AvatarTint(0xFFA9C8E8, 0xFF2A1830),
                    AvatarTint(0xFFB9DDB8, 0xFF2A1830),
                    AvatarTint(0xFFE3B4D6, 0xFF2A1830),
                ),
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
    const val MEDIA = 20
    const val BUBBLE = 20
    const val SEGMENT = 12
    const val CHIP = 10
}

/** Motion timings in ms (docs/design/themes.md, "Motion"). */
object Motion {
    const val PRESS = 160
    const val SEGMENT = 250
    const val STREAK_ROLL = 420
    const val CHECK_POP = 360
    const val SPARKS = 560
    const val COUNT_UP = 700
    const val PRESSED_SCALE = 0.97f
}
