package app.ayda.shared

import io.ktor.client.engine.mock.MockRequestHandleScope
import io.ktor.client.engine.mock.respond
import io.ktor.client.request.HttpRequestData
import io.ktor.client.request.HttpResponseData
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.content.OutgoingContent
import io.ktor.http.headersOf

internal const val TEST_BASE = "https://api.test/api/v1"

internal const val ME_JSON =
    """{"id":"8d6c2f9e-3a1b-4c5d-9e7f-0a1b2c3d4e5f","first_name":"Аня","timezone":"Europe/Kaliningrad",""" +
        """"theme":"plum","reminders":{"morning_at":"08:30","evening_at":null},""" +
        """"consent_required":null,"onboarded":true}"""

internal fun sessionJson(
    access: String,
    refresh: String,
) = """{"access_token":"$access","expires_at":"2026-10-17T12:00:00Z","user":$ME_JSON,"refresh_token":"$refresh"}"""

internal fun problemJson(
    status: Int,
    code: String,
    detail: String,
) = """{"type":"https://ayda.app/errors/$code","title":"Ошибка","status":$status,"detail":"$detail"}"""

internal fun MockRequestHandleScope.json(
    body: String,
    status: HttpStatusCode = HttpStatusCode.OK,
): HttpResponseData = respond(body, status, headersOf(HttpHeaders.ContentType, "application/json"))

internal fun MockRequestHandleScope.problem(
    status: HttpStatusCode,
    code: String,
    detail: String,
): HttpResponseData =
    respond(
        problemJson(status.value, code, detail),
        status,
        headersOf(HttpHeaders.ContentType, "application/problem+json"),
    )

internal fun HttpRequestData.bodyText(): String =
    (body as? OutgoingContent.ByteArrayContent)?.bytes()?.decodeToString() ?: ""
