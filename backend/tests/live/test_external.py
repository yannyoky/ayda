"""Live checks of external services (ayda.smoke) as tests: `uv run pytest -m live`.

Not part of the regular run: they need the network and keys, and a third-party outage must
not block a merge. The `Live checks` workflow runs them weekly and by hand.
"""

import httpx
import pytest

from ayda.core.config import Settings
from ayda.smoke import Check, checks, run_check

pytestmark = pytest.mark.live


def _checks() -> list[Check]:
    # Names only: the probes are rebuilt per test so each gets its own HTTP client.
    return checks(Settings(), httpx.AsyncClient())


@pytest.mark.parametrize("name", [c.name for c in _checks()])
async def test_external_service(name: str) -> None:
    async with httpx.AsyncClient() as http:
        check = next(c for c in checks(Settings(), http) if c.name == name)
        result = await run_check(check)
    if result.status == "skip":
        pytest.skip(result.detail)
    assert result.status == "ok", result.detail
