package app.ayda.shared.day

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.ayda.api.models.CompleteQuestInput
import app.ayda.api.models.Completion
import app.ayda.api.models.CreateUploadRequest
import app.ayda.api.models.Day
import app.ayda.api.models.DayQuest
import app.ayda.api.models.QuestState
import app.ayda.api.models.Visibility
import app.ayda.shared.ApiResult
import app.ayda.shared.AydaClient
import app.ayda.shared.apiCall
import app.ayda.shared.errorText
import app.ayda.shared.media.MAX_PHOTO_BYTES
import app.ayda.shared.media.MAX_VIDEO_BYTES
import app.ayda.shared.media.uploadMedia
import app.ayda.shared.media.uploadPhoto
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlin.math.floor
import kotlin.math.min
import kotlin.math.roundToInt

/** A photo picked for the proof, already compressed to JPEG on the device. */
class PickedPhoto(
    val id: Int,
    val jpeg: ByteArray,
)

/** A video from the phone or a circle recorded on the spot; goes without photos. */
class PickedClip(
    val kind: CreateUploadRequest.Kind,
    val type: CreateUploadRequest.ContentType,
    val bytes: ByteArray,
)

enum class PhotoError { TooBig, Unreadable, VideoTooBig, VideoUnsupported }

data class Upload(
    /** 1-based number of the photo being uploaded. */
    val current: Int,
    val total: Int,
)

data class CompleteState(
    val quest: DayQuest,
    val visibility: Visibility = Visibility.friends,
    val photos: List<PickedPhoto> = emptyList(),
    val clip: PickedClip? = null,
    val caption: String = "",
    val photoError: PhotoError? = null,
    val uploading: Upload? = null,
    val submitting: Boolean = false,
    val result: Completion? = null,
    val error: String? = null,
) {
    /** A feed post: text, and photos only if the user adds them. */
    val inFeed: Boolean get() = visibility == Visibility.friends
    val canAddPhoto: Boolean get() = clip == null && photos.size < CompleteViewModel.MAX_PHOTOS

    /** A video or a circle goes alone: up to 3 photos, or one video, or one circle. */
    val canAddClip: Boolean get() = clip == null && photos.isEmpty()
    val busy: Boolean get() = submitting || uploading != null
    val ready: Boolean get() = !busy
}

/**
 * US-09/US-10: marks a taken quest done, lets the user choose who sees it and attach
 * 1-3 photos, a video or a circle for friends. [onCompleted] refreshes Today once the server counted it.
 */
class CompleteViewModel(
    private val client: AydaClient,
    quest: DayQuest,
    private val day: Day,
    private val onCompleted: () -> Unit,
) : ViewModel() {
    private val mutableState = MutableStateFlow(CompleteState(quest))
    val state: StateFlow<CompleteState> = mutableState.asStateFlow()
    private var nextPhotoId = 0

    fun onVisibilityChange(value: Visibility) = mutableState.update { it.copy(visibility = value, error = null) }

    fun onCaptionChange(value: String) = mutableState.update { it.copy(caption = value.take(CAPTION_MAX)) }

    fun addPhoto(jpeg: ByteArray) =
        mutableState.update {
            when {
                !it.canAddPhoto -> it
                jpeg.size > MAX_PHOTO_BYTES -> it.copy(photoError = PhotoError.TooBig)
                else -> it.copy(photos = it.photos + PickedPhoto(nextPhotoId++, jpeg), photoError = null)
            }
        }

    /** A video picked from the phone; `mime` is what the system reports for it. */
    fun addVideo(
        bytes: ByteArray,
        mime: String?,
    ) {
        val type = videoType(mime)
        mutableState.update {
            when {
                !it.canAddClip -> it
                type == null -> it.copy(photoError = PhotoError.VideoUnsupported)
                bytes.size > MAX_VIDEO_BYTES -> it.copy(photoError = PhotoError.VideoTooBig)
                else -> it.copy(clip = PickedClip(CreateUploadRequest.Kind.video, type, bytes), photoError = null)
            }
        }
    }

    /** A circle recorded with the front camera, as MP4. */
    fun addCircle(mp4: ByteArray) =
        mutableState.update {
            when {
                !it.canAddClip -> it
                mp4.size > MAX_VIDEO_BYTES -> it.copy(photoError = PhotoError.VideoTooBig)
                else ->
                    it.copy(
                        clip =
                            PickedClip(
                                CreateUploadRequest.Kind.video_note,
                                CreateUploadRequest.ContentType.videoSlashMp4,
                                mp4,
                            ),
                        photoError = null,
                    )
            }
        }

    fun removeClip() = mutableState.update { it.copy(clip = null) }

    /** The device could not decode or compress the picked file. */
    fun photoFailed() = mutableState.update { it.copy(photoError = PhotoError.Unreadable) }

    fun removePhoto(id: Int) = mutableState.update { s -> s.copy(photos = s.photos.filterNot { it.id == id }) }

    /** A preview of the PRD scoring; only the backend awards points. */
    fun expectedPoints(visibility: Visibility): Int {
        val firstToday = day.quests.none { it.state == QuestState.completed }
        val streak = day.streak.currentDays + if (firstToday) 1 else 0
        return (state.value.quest.basePoints * multiplier(visibility) * streakMultiplier(streak)).roundToInt()
    }

    fun submit() {
        val current = state.value
        if (!current.ready) return
        mutableState.update { it.copy(error = null) }
        viewModelScope.launch {
            val mediaIds = mutableListOf<String>()
            val clip = current.clip
            if (current.inFeed && clip != null) {
                mutableState.update { it.copy(uploading = Upload(1, 1)) }
                when (val uploaded = client.uploadMedia(clip.kind, clip.type, clip.bytes)) {
                    is ApiResult.Ok -> mediaIds += uploaded.value
                    else -> return@launch fail(uploaded)
                }
            } else if (current.inFeed) {
                for ((index, photo) in current.photos.withIndex()) {
                    mutableState.update { it.copy(uploading = Upload(index + 1, current.photos.size)) }
                    when (val uploaded = client.uploadPhoto(photo.jpeg)) {
                        is ApiResult.Ok -> mediaIds += uploaded.value
                        else -> return@launch fail(uploaded)
                    }
                }
            }
            mutableState.update { it.copy(uploading = null, submitting = true) }
            val input =
                if (current.inFeed) {
                    CompleteQuestInput(
                        visibility = current.visibility,
                        caption = current.caption.trim().ifEmpty { null },
                        mediaIds = mediaIds.toSet(),
                    )
                } else {
                    CompleteQuestInput(visibility = current.visibility)
                }
            when (val completed = apiCall { client.day.completeQuest(current.quest.id, input) }) {
                is ApiResult.Ok -> {
                    mutableState.update { it.copy(submitting = false, result = completed.value) }
                    onCompleted()
                }
                else -> fail(completed)
            }
        }
    }

    private fun fail(result: ApiResult<*>) =
        mutableState.update { it.copy(uploading = null, submitting = false, error = result.errorText()) }

    companion object {
        const val MAX_PHOTOS = 3
        const val CAPTION_MAX = 500

        fun videoType(mime: String?): CreateUploadRequest.ContentType? =
            when (mime?.substringBefore(';')?.trim()?.lowercase()) {
                "video/mp4" -> CreateUploadRequest.ContentType.videoSlashMp4
                "video/quicktime" -> CreateUploadRequest.ContentType.videoSlashQuicktime
                "video/webm" -> CreateUploadRequest.ContentType.videoSlashWebm
                else -> null
            }

        fun multiplier(visibility: Visibility): Double =
            when (visibility) {
                Visibility.friends -> 1.0
                Visibility.routine -> 0.75
                Visibility.personal -> 0.5
            }

        /** +10% for every full week of the streak, up to +30%. */
        fun streakMultiplier(days: Int): Double = 1 + min(3.0, floor(days / 7.0)) * 0.1
    }
}
