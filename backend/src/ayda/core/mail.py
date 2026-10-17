"""Outgoing email over SMTP (sign-in codes, ADR 0009). Settings come from the environment."""

import asyncio
import smtplib
import ssl
from email.message import EmailMessage

from ayda.core.config import Settings


class MailError(Exception):
    """Sending failed; the message never contains the recipient or the body."""


class Mailer:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def enabled(self) -> bool:
        return self._settings.smtp_host is not None

    async def send(self, to: str, subject: str, body: str) -> None:
        msg = EmailMessage()
        msg["From"] = self._settings.smtp_from
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        try:
            await asyncio.to_thread(self._send, msg)
        except (OSError, smtplib.SMTPException) as exc:
            raise MailError(type(exc).__name__) from None

    def _send(self, msg: EmailMessage) -> None:
        s = self._settings
        assert s.smtp_host is not None
        context = ssl.create_default_context()
        smtp: smtplib.SMTP
        if s.smtp_security == "ssl":
            smtp = smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=10, context=context)
        else:
            smtp = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=10)
        with smtp:
            if s.smtp_security == "starttls":
                smtp.starttls(context=context)
            if s.smtp_username and s.smtp_password:
                smtp.login(s.smtp_username, s.smtp_password.get_secret_value())
            smtp.send_message(msg)
