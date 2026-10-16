"""Check API responses against the hand-written contract (ADR 0004)."""

from functools import cache
from pathlib import Path
from typing import Any, cast

import httpx
import yaml
from jsonschema import Draft202012Validator, FormatChecker

CONTRACT_PATH = Path(__file__).resolve().parents[2] / "contracts" / "openapi.yaml"
HTTP_METHODS = ("get", "put", "post", "delete", "patch")


@cache
def contract() -> dict[str, Any]:
    with CONTRACT_PATH.open(encoding="utf-8") as f:
        return cast(dict[str, Any], yaml.safe_load(f))


@cache
def operations() -> dict[str, tuple[str, str, dict[str, Any]]]:
    """operationId -> (method, path, operation)."""
    ops: dict[str, tuple[str, str, dict[str, Any]]] = {}
    for path, item in contract()["paths"].items():
        for method in HTTP_METHODS:
            if method in item:
                op = item[method]
                ops[op["operationId"]] = (method, path, op)
    return ops


def _resolve(node: dict[str, Any]) -> dict[str, Any]:
    while "$ref" in node:
        ref = cast(str, node["$ref"])
        target: Any = contract()
        for part in ref.removeprefix("#/").split("/"):
            target = target[part]
        node = cast(dict[str, Any], target)
    return node


def assert_matches(response: httpx.Response, operation_id: str) -> None:
    """The status code is declared for the operation and the body fits its schema."""
    _, _, op = operations()[operation_id]
    status = str(response.status_code)
    responses = cast(dict[str, Any], op["responses"])
    assert status in responses, f"{operation_id}: status {status} not in contract"
    declared = _resolve(cast(dict[str, Any], responses[status]))
    content = cast(dict[str, Any] | None, declared.get("content"))
    if not content:
        assert not response.content, f"{operation_id}: {status} must have no body"
        return
    media_type = response.headers["content-type"].split(";")[0]
    assert media_type in content, f"{operation_id}: unexpected media type {media_type}"
    schema = dict(content[media_type]["schema"])
    schema["components"] = contract()["components"]
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(response.json()), key=lambda e: list(e.path))
    assert not errors, f"{operation_id}: " + "; ".join(
        f"{list(e.path)}: {e.message}" for e in errors
    )
