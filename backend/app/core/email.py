"""
Minimal SMTP email sending — no third-party dependency, just the standard
library (smtplib + email.mime), since this is the only place in the app
that needs to send email. If more email features are added later and
this starts feeling thin, that's the signal to bring in a real library
(e.g. a transactional email API) — don't build more on top of this ad hoc.
"""
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings
from app.core.errors import ValidationFailedError


def send_email_with_attachment(
    *,
    to: str,
    subject: str,
    body: str,
    attachment_bytes: bytes,
    attachment_filename: str,
) -> None:
    if not settings.SMTP_HOST:
        raise ValidationFailedError(
            "Email isn't configured yet — set SMTP_HOST (and the other SMTP_* settings) "
            "in the backend's .env file before using this feature."
        )

    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_FROM_EMAIL or settings.SMTP_USERNAME
    msg["To"] = to
    msg.attach(MIMEText(body, "plain"))

    part = MIMEApplication(attachment_bytes, Name=attachment_filename)
    part["Content-Disposition"] = f'attachment; filename="{attachment_filename}"'
    msg.attach(part)

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as server:
            if settings.SMTP_USE_TLS:
                server.starttls()
            if settings.SMTP_USERNAME:
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            server.sendmail(msg["From"], [to], msg.as_string())
    except smtplib.SMTPException as e:
        raise ValidationFailedError(f"Could not send email: {e}")
    except OSError as e:
        # Covers connection refused / DNS failure / timeout — smtplib
        # raises plain OSError subclasses for these, not SMTPException.
        raise ValidationFailedError(f"Could not reach the mail server: {e}")
