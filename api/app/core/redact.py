"""Segredo que precisa ir na URL não pode ir para log nem trace (SETL-67).

O Inter não manda cabeçalho no callback, então o token do webhook vai em
`?token=`. Tudo que grava a URL passa por aqui: access log do uvicorn, span do
servidor e o salto do gateway para o serviço dono da rota.
"""

import logging
import re

SECRET_PARAMS = ("token", "access_token", "apikey", "api_key")
_SECRET_QUERY = re.compile(
    r"(?P<key>(?:^|[?&])(?:" + "|".join(SECRET_PARAMS) + r")=)[^&#\s]*",
    re.IGNORECASE,
)
REDACTED = "REDACTED"


def redact_url(url: str) -> str:
    """Troca o valor de `token=` e parecidos por REDACTED. O resto da URL fica igual."""
    if not url or "=" not in url:
        return url
    return _SECRET_QUERY.sub(lambda m: m.group("key") + REDACTED, url)


class RedactAccessLog(logging.Filter):
    """uvicorn.access: args = (cliente, método, caminho com query, versão, status)."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3 and isinstance(args[2], str):
            record.args = (*args[:2], redact_url(args[2]), *args[3:])
        return True


def install_access_log_filter() -> None:
    logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, RedactAccessLog) for f in logger.filters):
        logger.addFilter(RedactAccessLog())


URL_ATTRIBUTES = ("http.target", "http.url", "url.full", "url.query")


def redact_span(span) -> None:  # noqa: ANN001
    """Reescreve os atributos de URL de um span já aberto."""
    if span is None or not span.is_recording():
        return
    attributes = getattr(span, "attributes", None) or {}
    for key in URL_ATTRIBUTES:
        value = attributes.get(key)
        if isinstance(value, str) and value != (clean := redact_url(value)):
            span.set_attribute(key, clean)
