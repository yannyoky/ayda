"""Sign-in (Telegram initData, email codes), users, consents, access and refresh tokens."""

from ayda.modules.auth.devices import forget_token, list_devices, register_device, remove_device
from ayda.modules.auth.email import EmailError, check_code, issue_code, normalize_email
from ayda.modules.auth.identities import (
    IdentityError,
    link_email,
    link_telegram,
    list_identities,
    unlink_identity,
)
from ayda.modules.auth.models import Device, User, UserIdentity
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
from ayda.modules.auth.sessions import end_all_sessions, token_revoked
from ayda.modules.auth.telegram import InitData, InitDataError, TelegramUser, validate_init_data
from ayda.modules.auth.telegram_login import (
    CODE_PREFIX,
    LoginRequestError,
    approve_request,
    create_request,
    exchange_request,
    find_pending,
)
from ayda.modules.auth.tokens import TokenError, issue_token, read_token, read_token_claims

__all__ = [
    "CODE_PREFIX",
    "CURRENT_CONSENT_VERSION",
    "Device",
    "EmailError",
    "IdentityError",
    "InitData",
    "InitDataError",
    "LoginRequestError",
    "RefreshError",
    "TelegramUser",
    "TokenError",
    "User",
    "UserIdentity",
    "accept_consent",
    "approve_request",
    "check_code",
    "consent_required",
    "create_request",
    "delete_user",
    "end_all_sessions",
    "exchange_request",
    "find_or_create_email_user",
    "find_pending",
    "forget_token",
    "get_user",
    "get_users",
    "issue_code",
    "issue_refresh_token",
    "issue_token",
    "link_email",
    "link_telegram",
    "list_devices",
    "list_identities",
    "mark_bot_reachable",
    "normalize_email",
    "read_token",
    "read_token_claims",
    "register_device",
    "remove_device",
    "request_deletion",
    "revoke_refresh_token",
    "rotate_refresh_token",
    "token_revoked",
    "unlink_identity",
    "upsert_telegram_user",
    "user_city_ids",
    "validate_init_data",
]
