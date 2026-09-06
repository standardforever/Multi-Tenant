import logging

import httpx

from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"


async def send_email(to: str, subject: str, html: str) -> None:
    """Fire-and-forget email send via Resend. Never raises — this is always
    called from a background task after the HTTP response has already been
    sent, so there's no request left to surface an error to; failures are
    logged instead."""
    if not settings.resend_api_key:
        logger.warning("RESEND_API_KEY not set; skipping email to %s (%s)", to, subject)
        return

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                RESEND_API_URL,
                headers={"Authorization": f"Bearer {settings.resend_api_key}"},
                json={"from": settings.email_from, "to": [to], "subject": subject, "html": html},
            )
            response.raise_for_status()
    except httpx.HTTPError:
        logger.exception("Failed to send email to %s (%s)", to, subject)
