package app.ayda.shared.media

import app.ayda.api.models.CreateUploadRequest
import app.ayda.shared.ApiProblem
import app.ayda.shared.ApiResult
import app.ayda.shared.AydaClient
import app.ayda.shared.apiCall
import io.ktor.client.request.headers
import io.ktor.client.request.put
import io.ktor.client.request.setBody
import io.ktor.http.isSuccess
import kotlinx.coroutines.CancellationException

/** The contract's limit for one photo. */
const val MAX_PHOTO_BYTES = 10 * 1024 * 1024

/**
 * US-10: gets a presigned slot and PUTs the photo straight to storage. Returns the media id.
 *
 * The apps re-encode every photo to JPEG on the device first, so EXIF (and its location)
 * never leaves the phone; the server strips EXIF again before anyone can see the photo.
 */
suspend fun AydaClient.uploadPhoto(jpeg: ByteArray): ApiResult<String> {
    val request = CreateUploadRequest(CreateUploadRequest.ContentType.imageSlashJpeg, jpeg.size)
    val slot =
        when (val created = apiCall { media.createUpload(request) }) {
            is ApiResult.Ok -> created.value
            is ApiResult.Failed -> return created
            is ApiResult.Offline -> return created
        }
    return try {
        val response =
            http.put(slot.uploadUrl) {
                headers { slot.headers.forEach { (name, value) -> append(name, value) } }
                setBody(jpeg)
            }
        if (response.status.isSuccess()) {
            ApiResult.Ok(slot.mediaId)
        } else {
            ApiResult.Failed(ApiProblem(response.status.value, "upload-failed", ""))
        }
    } catch (e: CancellationException) {
        throw e
    } catch (e: Exception) {
        ApiResult.Offline(e)
    }
}
