import httpx

from ayda.smoke import Check, Skip, run_check


async def _ok() -> str:
    return "fine"


async def _skip() -> str:
    raise Skip("KEY not set")


async def _broken() -> str:
    raise AssertionError("no events")


async def _leaky() -> str:
    raise httpx.ConnectError("failed: https://api.telegram.org/bot123456:SECRET/getMe")


async def test_statuses() -> None:
    assert (await run_check(Check("a", _ok))).status == "ok"
    skipped = await run_check(Check("b", _skip))
    assert (skipped.status, skipped.detail) == ("skip", "KEY not set")
    failed = await run_check(Check("c", _broken))
    assert (failed.status, failed.detail) == ("fail", "AssertionError: no events")


async def test_failure_detail_never_quotes_library_messages() -> None:
    result = await run_check(Check("telegram", _leaky))
    assert result.status == "fail"
    assert result.detail == "ConnectError"
