package app.ayda.shared

import app.ayda.api.infrastructure.HttpResponse
import app.ayda.api.models.Problem
import io.ktor.client.call.body
import kotlinx.coroutines.CancellationException

/** An error the server explained (RFC 9457), with the stable code from the `type` URI. */
data class ApiProblem(
    val status: Int,
    val code: String,
    val message: String,
)

sealed interface ApiResult<out T> {
    data class Ok<T>(
        val value: T,
    ) : ApiResult<T>

    data class Failed(
        val problem: ApiProblem,
    ) : ApiResult<Nothing>

    /** No answer from the server: no network, a timeout, or a body we could not read. */
    data class Offline(
        val cause: Throwable,
    ) : ApiResult<Nothing>
}

/** Runs one generated API call and folds HTTP errors and network failures into [ApiResult]. */
suspend fun <T : Any, R> apiCall(
    request: suspend () -> HttpResponse<T>,
    onSuccess: suspend (HttpResponse<T>) -> R,
): ApiResult<R> =
    try {
        val response = request()
        if (response.success) ApiResult.Ok(onSuccess(response)) else ApiResult.Failed(response.problem())
    } catch (e: CancellationException) {
        throw e
    } catch (e: Exception) {
        ApiResult.Offline(e)
    }

/** The same, for calls whose success body is the generated model itself. */
suspend fun <T : Any> apiCall(request: suspend () -> HttpResponse<T>): ApiResult<T> = apiCall(request) { it.body() }

private suspend fun HttpResponse<*>.problem(): ApiProblem {
    val parsed = runCatching { response.body<Problem>() }.getOrNull()
    return ApiProblem(
        status = status,
        code = parsed?.type?.substringAfterLast('/') ?: "http-$status",
        message = parsed?.detail ?: parsed?.title ?: "",
    )
}

/** A ready-to-show Russian text for a failed call. */
fun ApiResult<*>.errorText(): String =
    when (this) {
        is ApiResult.Failed -> problem.message.ifBlank { ErrorTexts.GENERIC }
        is ApiResult.Offline -> ErrorTexts.OFFLINE
        is ApiResult.Ok -> ErrorTexts.GENERIC
    }

object ErrorTexts {
    const val OFFLINE = "Нет связи с сервером. Проверьте интернет и попробуйте ещё раз."
    const val GENERIC = "Что-то пошло не так. Попробуйте ещё раз."
    const val UPLOAD = "Не получилось загрузить фото. Попробуйте ещё раз или уберите фото и отправьте только текст."
}
