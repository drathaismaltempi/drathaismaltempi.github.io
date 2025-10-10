"""Utility helpers for dispatching physician summary emails."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Optional

from src.config import settings


class EmailService:
    """Simple SMTP wrapper tailored for physician summary delivery."""

    def __init__(
        self,
        *,
        host: Optional[str] = None,
        port: Optional[int] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        sender: Optional[str] = None,
    ) -> None:
        self._host = host or settings.smtp_host
        self._port = port or settings.smtp_port
        self._username = username or settings.smtp_username
        self._password = password or settings.smtp_password
        self._sender = sender or settings.smtp_sender or settings.smtp_username

    def is_configured(self) -> bool:
        """Return True when SMTP credentials are available."""

        return bool(
            self._host
            and self._port
            and self._username
            and self._password
            and self._sender
        )

    def send_markdown_email(self, *, to: str, subject: str, body: str) -> None:
        """Send a plaintext/Markdown email via SMTP."""

        if not self.is_configured():
            raise RuntimeError("SMTP credentials are not fully configured.")

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self._sender
        message["To"] = to
        message.set_content(body)

        with smtplib.SMTP(self._host, self._port, timeout=30) as smtp:
            smtp.starttls()
            smtp.login(self._username, self._password)
            smtp.send_message(message)


__all__ = ["EmailService"]

