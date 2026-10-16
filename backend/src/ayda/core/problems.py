"""RFC 9457 problem details for every error the API returns."""

from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

PROBLEM_BASE = "https://ayda.app/errors/"
PROBLEM_MEDIA_TYPE = "application/problem+json"

_DEFAULT_TITLES = {
    400: "Некорректный запрос",
    401: "Нужно войти",
    403: "Нет доступа",
    404: "Не найдено",
    405: "Метод не поддерживается",
    409: "Конфликт",
    410: "Больше не действует",
    422: "Проверьте данные",
    429: "Слишком много запросов",
    500: "Что-то пошло не так",
    503: "Сервис недоступен",
}


class Problem(Exception):
    """Raise from any layer to answer with a problem+json body."""

    def __init__(
        self,
        status: int,
        code: str,
        title: str | None = None,
        detail: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(code)
        self.status = status
        self.code = code
        self.title = title or _DEFAULT_TITLES.get(status, "Ошибка")
        self.detail = detail
        self.headers = headers


def problem_response(
    status: int,
    code: str,
    title: str | None = None,
    detail: str | None = None,
    errors: list[dict[str, str]] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": PROBLEM_BASE + code,
        "title": title or _DEFAULT_TITLES.get(status, "Ошибка"),
        "status": status,
    }
    if detail is not None:
        body["detail"] = detail
    if errors is not None:
        body["errors"] = errors
    return JSONResponse(body, status_code=status, media_type=PROBLEM_MEDIA_TYPE, headers=headers)


_HTTP_CODES = {
    401: "unauthorized",
    403: "forbidden",
    404: "not-found",
    405: "method-not-allowed",
    429: "too-many-requests",
}


def install_problem_handlers(app: FastAPI) -> None:
    async def on_problem(_: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, Problem)
        return problem_response(exc.status, exc.code, exc.title, exc.detail, headers=exc.headers)

    async def on_http(_: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, StarletteHTTPException)
        code = _HTTP_CODES.get(exc.status_code, "http-error")
        return problem_response(exc.status_code, code, headers=exc.headers)

    async def on_validation(_: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, RequestValidationError)
        errors = [
            {
                # Field path without the location prefix (body/query/path)
                "field": ".".join(str(p) for p in err.get("loc", ())[1:]) or "body",
                "message": str(err.get("msg", "invalid")),
            }
            for err in exc.errors()
        ]
        # Never echo the submitted values back: they may hold personal data.
        return problem_response(422, "validation-failed", errors=errors)

    app.add_exception_handler(Problem, on_problem)
    app.add_exception_handler(StarletteHTTPException, on_http)
    app.add_exception_handler(RequestValidationError, on_validation)
