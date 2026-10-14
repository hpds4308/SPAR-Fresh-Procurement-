"""
Sending email — no third-party dependency, just the standard library.

Two ways out, picked by configuration:
  - Brevo's HTTP API (BREVO_API_KEY + EMAIL_FROM_ADDRESS), the one used in
    production: Railway blocks outbound SMTP on its non-Pro plans.
  - Plain SMTP (SMTP_HOST and the other SMTP_* settings), e.g. local dev.
If neither is set, email_configured() is False and sending raises
EmailNotConfigured.
"""
import base64
import json
import smtplib
import urllib.error
import urllib.request
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

from app.core.config import settings
from app.core.errors import ValidationFailedError

BREVO_URL = "https://api.brevo.com/v3/smtp/email"


class EmailError(Exception):
    """The email service refused the email or couldn't be reached."""


class EmailNotConfigured(EmailError):
    pass


def email_configured() -> bool:
    return bool((settings.BREVO_API_KEY and settings.EMAIL_FROM_ADDRESS) or settings.SMTP_HOST)


def from_address() -> str:
    return settings.EMAIL_FROM_ADDRESS or settings.SMTP_FROM_EMAIL or settings.SMTP_USERNAME


def send_email(
    *,
    to: list[str],
    subject: str,
    text: str,
    html: str | None = None,
    attachments: list[tuple[str, bytes]] | None = None,
) -> None:
    """Sends one email to every address in `to`. Raises EmailError on failure."""
    if settings.BREVO_API_KEY and settings.EMAIL_FROM_ADDRESS:
        _send_brevo(to, subject, text, html, attachments or [])
    elif settings.SMTP_HOST:
        _send_smtp(to, subject, text, html, attachments or [])
    else:
        raise EmailNotConfigured("Email isn't configured yet (no BREVO_API_KEY or SMTP_HOST).")


def _send_brevo(to, subject, text, html, attachments) -> None:
    payload = {
        "sender": {"name": settings.EMAIL_FROM_NAME, "email": settings.EMAIL_FROM_ADDRESS},
        "to": [{"email": addr} for addr in to],
        "subject": subject,
        "textContent": text,
    }
    if html:
        payload["htmlContent"] = html
    if attachments:
        payload["attachment"] = [
            {"name": name, "content": base64.b64encode(data).decode("ascii")} for name, data in attachments
        ]
    req = urllib.request.Request(
        BREVO_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "api-key": settings.BREVO_API_KEY,
            "accept": "application/json",
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310 — fixed https URL
            resp.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        raise EmailError(f"Brevo refused the email ({e.code}): {detail}")
    except (urllib.error.URLError, OSError) as e:
        raise EmailError(f"Could not reach Brevo: {e}")


def _send_smtp(to, subject, text, html, attachments) -> None:
    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = formataddr((settings.EMAIL_FROM_NAME, from_address()))
    msg["To"] = ", ".join(to)
    body = MIMEMultipart("alternative")
    body.attach(MIMEText(text, "plain", "utf-8"))
    if html:
        body.attach(MIMEText(html, "html", "utf-8"))
    msg.attach(body)
    for name, data in attachments:
        part = MIMEApplication(data, Name=name)
        part["Content-Disposition"] = f'attachment; filename="{name}"'
        msg.attach(part)
    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as server:
            if settings.SMTP_USE_TLS:
                server.starttls()
            if settings.SMTP_USERNAME:
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            server.sendmail(from_address(), to, msg.as_string())
    except smtplib.SMTPException as e:
        raise EmailError(f"Could not send email: {e}")
    except OSError as e:
        # Connection refused / DNS failure / timeout — smtplib raises plain
        # OSError subclasses for these, not SMTPException.
        raise EmailError(f"Could not reach the mail server: {e}")


def send_email_with_attachment(
    *,
    to: str,
    subject: str,
    body: str,
    attachment_bytes: bytes,
    attachment_filename: str,
) -> None:
    """For the Master Data "Send" button: errors come back as a message to show Admin."""
    if not email_configured():
        raise ValidationFailedError(
            "Email isn't configured yet — set BREVO_API_KEY and EMAIL_FROM_ADDRESS (or the SMTP_* settings) "
            "on the backend before using this feature."
        )
    try:
        send_email(to=[to], subject=subject, text=body, attachments=[(attachment_filename, attachment_bytes)])
    except EmailError as e:
        raise ValidationFailedError(str(e))
