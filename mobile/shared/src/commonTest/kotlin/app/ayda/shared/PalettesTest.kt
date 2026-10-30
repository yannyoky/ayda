package app.ayda.shared

import app.ayda.api.models.Theme
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertSame
import kotlin.test.assertTrue

class PalettesTest {
    @Test
    fun everyThemeFromTheContractHasAPalette() {
        assertSame(Palettes.Graphite, Palettes.of(Theme.graphite))
        assertSame(Palettes.Plum, Palettes.of(Theme.plum))
    }

    @Test
    fun textOnAccentIsTheInkColour() {
        for (palette in listOf(Palettes.Graphite, Palettes.Plum)) {
            assertEquals(palette.ink, palette.onAccent)
        }
    }
}

class AvatarTintsTest {
    @Test
    fun everyThemeHasSixAvatarTints() {
        for (palette in listOf(Palettes.Graphite, Palettes.Plum)) {
            assertEquals(AvatarTints.COUNT, palette.avatars.size)
        }
    }

    @Test
    fun tintMatchesTheMiniApp() {
        // Values from miniapp/src/ui/avatarTint.ts (minus one: the Mini App counts tints from 1)
        assertEquals(4, AvatarTints.indexOf("3f2b1c4e-0000-4000-8000-000000000001"))
        assertEquals(3, AvatarTints.indexOf("Аня"))
        assertEquals(4, AvatarTints.indexOf("a"))
        assertEquals(1, AvatarTints.indexOf(""))
    }

    @Test
    fun usersSpreadOverThePalette() {
        val tints = listOf("a", "b", "c", "d", "e", "f", "g", "h").map(AvatarTints::indexOf).toSet()
        assertTrue(tints.size > 3)
        assertTrue(tints.all { it in 0 until AvatarTints.COUNT })
    }
}
