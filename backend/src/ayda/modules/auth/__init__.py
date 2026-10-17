"""Sign-in (Telegram initData, email codes), users, consents, access and refresh tokens."""

from ayda.modules.auth.email import EmailError, check_code, issue_code, normalize_email
from ayda.modules.auth.models import User
from ayda.modules.auth.refresh import (
    RefreshError,
    issue_refresh_token,
    revoke_refresh_token,
    rotate_refresh_token,
)
from ayda.modules.auth.service import (
    CURRENT_CONSENT_VERSION,
    accept_consent,
    consent_required,
    delete_user,
    find_or_create_email_user,
    get_user,
    get_users,
    mark_bot_reachable,
    request_deletion,
    upsert_telegram_user,
    user_city_ids,
)
from ayda.modules.auth.telegram import InitData, InitDataError, TelegramUser, validate_init_data
from ayda.modules.auth.tokens import TokenError, issue_token, read_token

__all__ = [
    "CURRENT_CONSENT_VERSION",
    "EmailError",
    "InitData",
    "InitDataError",
    "RefreshError",
    "TelegramUser",
    "TokenError",
    "User",
    "accept_consent",
    "check_code",
    "consent_required",
    "delete_user",
    "find_or_create_email_user",
    "get_user",
    "get_users",
    "issue_code",
    "issue_refresh_token",
    "issue_token",
    "mark_bot_reachable",
    "normalize_email",
    "read_token",
    "request_deletion",
    "revoke_refresh_token",
    "rotate_refresh_token",
    "upsert_telegram_user",
    "user_city_ids",
    "validate_init_data",
]
