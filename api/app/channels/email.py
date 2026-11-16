import smtplib
from email.message import EmailMessage

from app.core.config import get_settings


def build_message(
    from_addr: str,
    to: str,
    subject: str,
    body: str,
    html: str | None = None,
    inline: list[tuple[str, bytes, str]] | None = None,
) -> EmailMessage:
    """Texto puro, HTML e imagens inline (`cid`, bytes, subtipo)."""
    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    if html:
        msg.add_alternative(html, subtype="html")
        related = msg.get_payload()[-1]
        for cid, data, subtype in inline or []:
            related.add_related(
                data,
                maintype="image",
                subtype=subtype,
                cid=f"<{cid}>",
                filename=f"{cid}.{subtype}",
            )
    return msg


def send_email(
    to: str,
    subject: str,
    body: str,
    html: str | None = None,
    inline: list[tuple[str, bytes, str]] | None = None,
) -> None:
    """E-mail transacional. `html` é a versão rica; `body` continua o texto puro."""
    settings = get_settings()
    if not settings.smtp_host:
        raise RuntimeError("SMTP não configurado (SMTP_HOST)")

    msg = build_message(settings.smtp_from, to, subject, body, html, inline)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
        smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg)
