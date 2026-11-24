import logging
from urllib.parse import urljoin

from app.core.config import settings


log = logging.getLogger("studybridge.email")


class EmailDeliveryError(RuntimeError):
    pass


def send_email(to_email: str, subject: str, text: str, html: str) -> None:
    if settings.EMAIL_MODE.lower() == "console":
        log.info("Email delivery queued in console mode")
        return

    if not settings.RESEND_API_KEY:
        raise EmailDeliveryError("Email delivery is not configured.")
    if not settings.EMAIL_FROM:
        raise EmailDeliveryError("Email delivery sender is not configured.")
    if settings.EMAIL_MODE.lower() != "resend":
        raise EmailDeliveryError("The selected email mode is not supported.")

    try:
        import requests
    except ImportError as exc:
        raise EmailDeliveryError(
            "Resend delivery requires the backend dependencies. Run "
            "'python -m pip install -r backend\\requirements.txt'."
        ) from exc

    try:
        response = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {settings.RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            json={"from": settings.EMAIL_FROM, "to": [to_email], "subject": subject, "text": text, "html": html},
            timeout=15,
        )
    except requests.Timeout as exc:
        raise EmailDeliveryError("The email provider timed out.") from exc
    except requests.ConnectionError as exc:
        raise EmailDeliveryError("The email provider could not be reached.") from exc
    except requests.RequestException as exc:
        raise EmailDeliveryError("The email provider request failed.") from exc
    if response.status_code not in (200, 201, 202):
        raise EmailDeliveryError("The email provider rejected the delivery request.")


def verification_url(token: str) -> str:
    return urljoin(settings.FRONTEND_BASE_URL.rstrip("/") + "/", f"verify-email?token={token}")


def reset_url(token: str) -> str:
    return urljoin(settings.FRONTEND_BASE_URL.rstrip("/") + "/", f"reset-password?token={token}")


def invitation_url(token: str) -> str:
    return urljoin(settings.FRONTEND_BASE_URL.rstrip("/") + "/", f"lecturer-activate?token={token}")
