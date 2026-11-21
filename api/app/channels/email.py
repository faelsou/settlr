import smtplib
from email.message import EmailMessage
from email.utils import make_msgid

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


def smtp_configured() -> bool:
    return bool(get_settings().smtp_host)


def send_email(
    to: str,
    subject: str,
    body: str,
    html: str | None = None,
    inline: list[tuple[str, bytes, str]] | None = None,
    message_id: str | None = None,
) -> str:
    """E-mail transacional. `html` é a versão rica; `body` continua o texto puro.

    Devolve o Message-ID. O servidor SMTP aceitar não é entrega: é o `aceito` do canal.
    """
    settings = get_settings()
    if not settings.smtp_host:
        raise RuntimeError("SMTP não configurado (SMTP_HOST)")

    msg = build_message(settings.smtp_from, to, subject, body, html, inline)
    msg["Message-ID"] = message_id or make_msgid(domain=_domain(settings.smtp_from))

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
        smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg)
    return msg["Message-ID"]


def _domain(address: str) -> str | None:
    return address.rsplit("@", 1)[1] if "@" in address else None


def is_permanent(exc: BaseException) -> bool:
    """Recusa 5xx do destinatário não melhora com retry. Rede, 4xx e login sim."""
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return True
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return False
    if isinstance(exc, smtplib.SMTPResponseException):
        return exc.smtp_code >= 500
    return False
