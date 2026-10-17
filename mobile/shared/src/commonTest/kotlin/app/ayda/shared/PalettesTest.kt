package app.ayda.shared

import app.ayda.api.models.Theme
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertSame

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
