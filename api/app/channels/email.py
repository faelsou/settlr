import smtplib
from email.message import EmailMessage

from app.core.config import get_settings


def send_email(to: str, subject: str, body: str, html: str | None = None) -> None:
    """E-mail transacional. `html` é a versão rica; `body` continua o texto puro."""
    settings = get_settings()
    if not settings.smtp_host:
        raise RuntimeError("SMTP não configurado (SMTP_HOST)")

    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    if html:
        msg.add_alternative(html, subtype="html")

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
        smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg)
