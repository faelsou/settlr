"""SETL-67: o token do webhook do Inter não aparece em log nem trace."""

import logging

import pytest

from app.core.redact import RedactAccessLog, redact_url

SEGREDO = "tok-inter-segredo"


@pytest.mark.parametrize(
    ("url", "esperado"),
    [
        (f"/webhooks/emissor?token={SEGREDO}", "/webhooks/emissor?token=REDACTED"),
        (f"/webhooks/emissor?x=1&token={SEGREDO}&y=2", "/webhooks/emissor?x=1&token=REDACTED&y=2"),
        (f"https://api.kitou.com.br/webhooks/emissor?TOKEN={SEGREDO}",
         "https://api.kitou.com.br/webhooks/emissor?TOKEN=REDACTED"),
        ("/invoices?status=aberto", "/invoices?status=aberto"),
        ("/webhooks/emissor?mytoken=1", "/webhooks/emissor?mytoken=1"),
        ("", ""),
    ],
)
def test_redact_url(url: str, esperado: str) -> None:
    assert redact_url(url) == esperado


def test_access_log_do_uvicorn_nao_mostra_o_token() -> None:
    record = logging.LogRecord(
        "uvicorn.access", logging.INFO, __file__, 1,
        '%s - "%s %s HTTP/%s" %d',
        ("10.0.0.1:5000", "POST", f"/webhooks/emissor?token={SEGREDO}", "1.1", 202),
        None,
    )
    assert RedactAccessLog().filter(record) is True
    linha = record.getMessage()
    assert SEGREDO not in linha
    assert "/webhooks/emissor?token=REDACTED" in linha


def test_configure_logging_instala_o_filtro() -> None:
    from app.core.logging import configure_logging

    configure_logging()
    assert any(isinstance(f, RedactAccessLog) for f in logging.getLogger("uvicorn.access").filters)


def test_span_do_servidor_e_reescrito() -> None:
    from app.core.redact import redact_span

    class _Span:
        def __init__(self) -> None:
            self.attributes = {"http.target": f"/webhooks/emissor?token={SEGREDO}",
                               "url.query": f"token={SEGREDO}", "http.method": "POST"}

        def is_recording(self) -> bool:
            return True

        def set_attribute(self, key: str, value: str) -> None:
            self.attributes[key] = value

    span = _Span()
    redact_span(span)
    assert SEGREDO not in str(span.attributes)
    assert span.attributes["http.method"] == "POST"


def test_gateway_leva_o_token_no_cabecalho_e_nao_na_url() -> None:
    import httpx
    from fastapi.testclient import TestClient

    from app.services.gateway import app

    vistos: list[tuple[str, dict]] = []

    class _Http:
        async def request(self, method, url, headers=None, content=None):  # noqa: ANN001
            vistos.append((url, dict(headers or {})))
            return httpx.Response(202, json={"status": "enfileirado"})

        async def aclose(self) -> None:
            return None

    with TestClient(app) as client:
        app.state.http = _Http()
        resposta = client.post(f"/webhooks/emissor?token={SEGREDO}&x=1", json=[])
    assert resposta.status_code == 202
    ((url, headers),) = vistos
    assert SEGREDO not in url
    assert url.endswith("/webhooks/emissor?x=1")
    assert headers["x-webhook-token"] == SEGREDO
