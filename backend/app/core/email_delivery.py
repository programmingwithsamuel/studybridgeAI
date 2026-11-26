
import logging
import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import urljoin

from app.core.config import settings


log = logging.getLogger("studybridge.email")


class EmailDeliveryError(RuntimeError):
    pass


def send_email(to_email: str, subject: str, text: str, html: str) -> None:
    mode = settings.EMAIL_MODE.lower()

    # Local development mode
    if mode == "console":
        log.info("Email delivery queued in console mode")
        return

    # Gmail SMTP mode
    if mode == "gmail":
        if not settings.SMTP_USERNAME or not settings.SMTP_PASSWORD:
            raise EmailDeliveryError(
                "Gmail SMTP credentials are not configured."
            )

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = settings.SMTP_FROM or settings.SMTP_USERNAME
        message["To"] = to_email
        message.set_content(text)
        message.add_alternative(html, subtype="html")

        try:
            context = ssl.create_default_context()

            with smtplib.SMTP(
                settings.SMTP_HOST,
                settings.SMTP_PORT,
                timeout=20,
            ) as server:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                server.login(
                    settings.SMTP_USERNAME,
                    settings.SMTP_PASSWORD.replace(" ", ""),
                )
                server.send_message(message)

            log.info("Email successfully sent")

        except (smtplib.SMTPException, OSError) as exc:
            log.exception("Gmail SMTP delivery failed")
            raise EmailDeliveryError(
                "Gmail could not send the email. Check SMTP configuration."
            ) from exc

        return

    # Existing Resend mode
    if mode == "resend":
        if not settings.RESEND_API_KEY:
            raise EmailDeliveryError(
                "Email delivery is not configured."
            )

        if not settings.EMAIL_FROM:
            raise EmailDeliveryError(
                "Email delivery sender is not configured."
            )

        try:
            import requests
        except ImportError as exc:
            raise EmailDeliveryError(
                "Resend requires requests. Install backend requirements."
            ) from exc

        try:
            response = requests.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {settings.RESEND_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": settings.EMAIL_FROM,
                    "to": [to_email],
                    "subject": subject,
                    "text": text,
                    "html": html,
                },
                timeout=15,
            )
        except requests.Timeout as exc:
            raise EmailDeliveryError(
                "The email provider timed out."
            ) from exc
        except requests.ConnectionError as exc:
            raise EmailDeliveryError(
                "The email provider could not be reached."
            ) from exc
        except requests.RequestException as exc:
            raise EmailDeliveryError(
                "The email provider request failed."
            ) from exc

        if response.status_code not in (200, 201, 202):
            raise EmailDeliveryError(
                "The email provider rejected the delivery request."
            )

        return

    raise EmailDeliveryError(
        "The selected email mode is not supported."
    )


def verification_url(token: str) -> str:
    return urljoin(
        settings.FRONTEND_BASE_URL.rstrip("/") + "/",
        f"verify-email?token={token}",
    )


def reset_url(token: str) -> str:
    return urljoin(
        settings.FRONTEND_BASE_URL.rstrip("/") + "/",
        f"reset-password?token={token}",
    )


def invitation_url(token: str) -> str:
    return urljoin(
        settings.FRONTEND_BASE_URL.rstrip("/") + "/",
        f"lecturer-activate?token={token}",
    )
