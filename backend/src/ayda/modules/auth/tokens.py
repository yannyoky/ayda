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
    # iat keeps microseconds, so "sign out everywhere" can cut exactly at a moment.
    claims = {"sub": str(user_id), "aud": _AUDIENCE, "iat": now.timestamp(), "exp": expires_at}
    token = jwt.encode(claims, secret, algorithm=_ALGORITHM)  # pyright: ignore[reportUnknownMemberType]
    return token, expires_at


def read_token(token: str, secret: str) -> uuid.UUID:
    return read_token_claims(token, secret)[0]


def read_token_claims(token: str, secret: str) -> tuple[uuid.UUID, datetime]:
    """The user id and the issue time of a valid token."""
    try:
        claims = jwt.decode(  # pyright: ignore[reportUnknownMemberType]
            token,
            secret,
            algorithms=[_ALGORITHM],
            audience=_AUDIENCE,
            options={"require": ["sub", "exp", "aud", "iat"]},
        )
        return uuid.UUID(str(claims["sub"])), datetime.fromtimestamp(float(claims["iat"]), UTC)
    except (jwt.PyJWTError, ValueError) as exc:
        raise TokenError("invalid token") from exc
