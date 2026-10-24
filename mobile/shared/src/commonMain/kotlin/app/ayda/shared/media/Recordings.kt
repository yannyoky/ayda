package app.ayda.shared.media

import app.ayda.api.models.ChatUploadInput
import app.ayda.shared.ApiProblem
import app.ayda.shared.ApiResult
import app.ayda.shared.AydaClient
import app.ayda.shared.ErrorTexts
import app.ayda.shared.apiCall
import io.ktor.client.request.headers
import io.ktor.client.request.put
import io.ktor.client.request.setBody
import io.ktor.http.isSuccess
import kotlinx.coroutines.CancellationException

/** The contract's limits: 10 MB of voice, 50 MB of a circle. */
const val MAX_VOICE_BYTES = 10 * 1024 * 1024
const val MAX_VIDEO_NOTE_BYTES = 50 * 1024 * 1024

/**
 * ADR 0019: gets a presigned slot in the chat and PUTs the recording (MP4: AAC for voice,
 * H.264 + AAC for a circle) straight to storage. Returns the id to send as `attachment_id`;
 * the server re-encodes the recording and drops its metadata before anyone can play it.
 */
suspend fun AydaClient.uploadRecording(
    conversationId: String,
    kind: ChatUploadInput.Kind,
    recording: ByteArray,
): ApiResult<String> {
    val type =
        when (kind) {
            ChatUploadInput.Kind.voice -> ChatUploadInput.ContentType.audioSlashMp4
            ChatUploadInput.Kind.video_note -> ChatUploadInput.ContentType.videoSlashMp4
        }
    val request = ChatUploadInput(kind, type, recording.size)
    val slot =
        when (val created = apiCall { chat.createChatUpload(conversationId, request) }) {
            is ApiResult.Ok -> created.value
            is ApiResult.Failed -> return created
            is ApiResult.Offline -> return created
        }
    return try {
        val response =
            http.put(slot.uploadUrl) {
                headers { slot.headers.forEach { (name, value) -> append(name, value) } }
                setBody(recording)
            }
        if (response.status.isSuccess()) {
            ApiResult.Ok(slot.mediaId)
        } else {
            ApiResult.Failed(ApiProblem(response.status.value, "upload-failed", ErrorTexts.UPLOAD))
        }
    } catch (e: CancellationException) {
        throw e
    } catch (e: Exception) {
        ApiResult.Offline(e)
    }
}
