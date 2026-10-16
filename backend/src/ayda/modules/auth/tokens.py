"""Short-lived signed access tokens issued after the initData check (no session table)."""

import uuid
from datetime import UTC, datetime, timedelta

import jwt

TOKEN_TTL = timedelta(hours=12)
_ALGORITHM = "HS256"
_AUDIENCE = "ayda-api"


class TokenError(Exception):
    pass


def issue_token(
    user_id: uuid.UUID, secret: str, now: datetime | None = None
) -> tuple[str, datetime]:
    now = now or datetime.now(UTC)
    expires_at = now + TOKEN_TTL
    claims = {"sub": str(user_id), "aud": _AUDIENCE, "iat": now, "exp": expires_at}
    token = jwt.encode(claims, secret, algorithm=_ALGORITHM)  # pyright: ignore[reportUnknownMemberType]
    return token, expires_at


def read_token(token: str, secret: str) -> uuid.UUID:
    try:
        claims = jwt.decode(  # pyright: ignore[reportUnknownMemberType]
            token,
            secret,
            algorithms=[_ALGORITHM],
            audience=_AUDIENCE,
            options={"require": ["sub", "exp", "aud"]},
        )
        return uuid.UUID(str(claims["sub"]))
    except (jwt.PyJWTError, ValueError) as exc:
        raise TokenError("invalid token") from exc
