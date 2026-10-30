package app.ayda.android.ui

import app.ayda.android.ui.social.initial
import org.junit.Assert.assertEquals
import org.junit.Test

class AvatarTest {
    @Test
    fun takesTheWholeFirstCharacterEmojiIncluded() {
        assertEquals("🦊", initial("🦊 Маргарита"))
        assertEquals("Ё", initial("ёлка"))
        assertEquals("J", initial("  Jo"))
        assertEquals("?", initial(""))
    }
}
