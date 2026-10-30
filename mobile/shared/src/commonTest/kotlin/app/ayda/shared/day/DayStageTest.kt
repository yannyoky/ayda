package app.ayda.shared.day

import app.ayda.api.models.QuestState
import kotlin.test.Test
import kotlin.test.assertEquals

class DayStageTest {
    @Test
    fun startsWithTheCheckin() = assertEquals(DayStage.Checkin, dayStage(hasCheckin = false, mine = emptyList()))

    @Test
    fun afterTheCheckinComesThePicker() = assertEquals(DayStage.Pick, dayStage(hasCheckin = true, mine = emptyList()))

    @Test
    fun aTakenQuestMeansDoing() =
        assertEquals(DayStage.Doing, dayStage(hasCheckin = true, mine = listOf(QuestState.completed, QuestState.taken)))

    @Test
    fun takenWithoutCheckinIsStillDoing() =
        assertEquals(DayStage.Doing, dayStage(hasCheckin = false, mine = listOf(QuestState.taken)))

    @Test
    fun nothingLeftClosesTheDay() =
        assertEquals(
            DayStage.Done,
            dayStage(hasCheckin = true, mine = listOf(QuestState.completed, QuestState.expired)),
        )
}
