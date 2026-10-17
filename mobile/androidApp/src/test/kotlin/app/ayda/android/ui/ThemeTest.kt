package app.ayda.android.ui

import androidx.compose.ui.graphics.Color
import app.ayda.shared.Palettes
import org.junit.Assert.assertEquals
import org.junit.Test

class ThemeTest {
    @Test
    fun graphiteMapsTokensToMaterialRoles() {
        val scheme = Palettes.Graphite.toColors().toColorScheme()

        assertEquals(Color(0xFFFF5FA2), scheme.primary)
        assertEquals(Color(0xFFE9E9E7), scheme.background)
        assertEquals(Color(0xFF18191B), scheme.onBackground)
        assertEquals(Color(0xFF18191B), scheme.onPrimary)
        assertEquals(Color(0xFF222326), scheme.inverseSurface)
    }

    @Test
    fun plumUsesItsOwnAccentAndPlate() {
        val colors = Palettes.Plum.toColors()

        assertEquals(Color(0xFFFF9E7A), colors.accent)
        assertEquals(Color(0xFF3B1E3F), colors.plate)
        assertEquals(Color(0xFF553258), colors.plate2)
    }
}
