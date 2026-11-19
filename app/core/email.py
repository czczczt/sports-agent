import asyncio
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import (
    FRONTEND_BASE_URL,
    SMTP_FROM,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USE_TLS,
    SMTP_USER,
)

logger = logging.getLogger(__name__)

SENT_EMAILS: list[dict] = []


def _send_smtp_sync(
    to_email: str, subject: str, text_content: str, html_content: str | None = None
) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = to_email

    msg.attach(MIMEText(text_content, "plain", "utf-8"))
    if html_content:
        msg.attach(MIMEText(html_content, "html", "utf-8"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10.0) as server:
        if SMTP_USE_TLS:
            server.starttls()
        if SMTP_USER and SMTP_PASSWORD:
            server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)


async def send_password_reset_email(to_email: str, token: str) -> str:
    reset_url = f"{FRONTEND_BASE_URL.rstrip('/')}/reset-password?token={token}"
    subject = "Восстановление пароля на платформе СберСпорт"
    text_content = (
        f"Здравствуйте!\n\n"
        f"Для вашей учётной записи был запрошен сброс пароля.\n"
        f"Чтобы установить новый пароль, перейдите по ссылке (действительна 1 час):\n"
        f"{reset_url}\n\n"
        f"Если вы не запрашивали сброс пароля, просто проигнорируйте это письмо."
    )

    SENT_EMAILS.append(
        {
            "to": to_email,
            "token": token,
            "reset_url": reset_url,
            "subject": subject,
        }
    )

    if SMTP_HOST:
        try:
            await asyncio.to_thread(_send_smtp_sync, to_email, subject, text_content)
            logger.info("password_reset_email_sent", extra={"to": to_email})
        except Exception as exc:
            logger.error(
                "failed_to_send_reset_email", extra={"to": to_email, "error": str(exc)}
            )
            raise
    else:
        logger.info(
            "simulated_password_reset_email",
            extra={"to": to_email, "reset_url": reset_url},
        )

    return reset_url
