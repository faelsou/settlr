"""O guia do painel sai em HTML quando a empresa entra no banco."""

from app.onboarding.welcome import deliver_welcome, welcome_copy


def test_guia_traz_o_passo_a_passo_em_html():
    subject, text, html = welcome_copy("Clínica <Norte>", "https://app.exemplo/")
    assert subject == "Como usar o painel — Clínica <Norte>"
    assert "Clínica &lt;Norte&gt;" in html
    assert "<script>" not in html
    for path in ("/login", "/configuracoes", "/titulos", "/inicio"):
        assert f"https://app.exemplo{path}" in html
        assert f"https://app.exemplo{path}" in text
    for trecho in (
        "Importar CSV",
        "Sem PIX ou boleto",
        "Disparo",
        "base legal",
        "financeiro",
        "atendente",
    ):
        assert trecho in html
        assert trecho in text
    assert "referencia,nome,documento,telefone,email,valor,vencimento" in text
    assert "password" not in text.lower()
    assert "não há senha" in text.lower()
    assert "opacity" not in html
    assert "color:#5f5a78" not in html
    assert 'src="cid:settlr-logo"' in html
    assert "color:#12101f" in html


def test_entrega_o_html_e_nao_derruba_o_cadastro_sem_smtp(monkeypatch):
    captured: dict[str, str] = {}

    def grava(
        to: str,
        subject: str,
        body: str,
        html: str | None = None,
        inline: list[tuple[str, bytes, str]] | None = None,
    ) -> None:
        captured["to"] = to
        captured["subject"] = subject
        captured["body"] = body
        captured["html"] = html or ""
        captured["inline"] = inline

    monkeypatch.setattr("app.onboarding.welcome.send_email", grava)
    assert deliver_welcome("Clínica Norte", "dona@clinica.test", "https://app.exemplo") is True
    assert captured["to"] == "dona@clinica.test"
    assert captured["html"].startswith("<!DOCTYPE html>")
    assert captured["inline"][0][0] == "settlr-logo"
    assert captured["inline"][0][1].startswith(b"\x89PNG")
    assert captured["inline"][0][2] == "png"
    assert deliver_welcome("Clínica Norte", "  ") is False

    def falha(*_args, **_kwargs) -> None:
        raise RuntimeError("SMTP não configurado (SMTP_HOST)")

    monkeypatch.setattr("app.onboarding.welcome.send_email", falha)
    assert deliver_welcome("Clínica Norte", "dona@clinica.test") is False
