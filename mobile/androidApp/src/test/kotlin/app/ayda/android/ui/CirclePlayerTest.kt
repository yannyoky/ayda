package app.ayda.android.ui

import app.ayda.android.ui.chat.CircleMode
import app.ayda.android.ui.chat.afterTap
import app.ayda.android.ui.chat.circleProgress
import app.ayda.android.ui.chat.circleSecondsLeft
import org.junit.Assert.assertEquals
import org.junit.Test

class CirclePlayerTest {
    @Test
    fun tapPlaysPausesAndResumesLikeTelegram() {
        assertEquals(CircleMode.Playing, CircleMode.Preview.afterTap())
        assertEquals(CircleMode.Paused, CircleMode.Playing.afterTap())
        assertEquals(CircleMode.Playing, CircleMode.Paused.afterTap())
    }

    @Test
    fun progressRingCoversThePlayedShare() {
        assertEquals(0f, circleProgress(0, 10_000), 0.001f)
        assertEquals(0.25f, circleProgress(2_500, 10_000), 0.001f)
        assertEquals(1f, circleProgress(12_000, 10_000), 0.001f)
        assertEquals(0f, circleProgress(1_000, 0), 0.001f)
    }

    @Test
    fun previewShowsTheWholeLengthAndPlaybackWhatIsLeft() {
        assertEquals(14, circleSecondsLeft(CircleMode.Preview, 5_000, 13_400))
        assertEquals(9, circleSecondsLeft(CircleMode.Playing, 5_000, 13_400))
        assertEquals(0, circleSecondsLeft(CircleMode.Paused, 20_000, 13_400))
    }
}
