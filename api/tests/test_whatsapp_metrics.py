"""Contadores do WhatsApp: contexto estável e ok/falha de mensagem e arquivo."""

from prometheus_client import REGISTRY

from app.channels.metrics import outbound_context, record_file, record_message, route_context


def _value(name: str, labels: dict[str, str]) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0


def test_contexto_prefere_intencao_e_nao_vaza_autor():
    assert route_context("agente", "duvida") == "duvida"
    assert route_context("pede_comprovante", "ja_paguei") == "ja_paguei"
    assert route_context("grupo", "duvida") == "grupo"
    assert route_context("pede_comprovante", None) == "comprovante"
    assert route_context("sem_texto_ou_humano", None) == "humano"
    assert outbound_context("agente", "parar") == "parar"
    assert outbound_context("regua:D0", None) == "regua"
    assert outbound_context("financeiro@empresa.com", "duvida") == "operador"


def test_mensagem_e_arquivo_entram_no_prometheus():
    message = {
        "direction": "entrada",
        "stage": "roteada",
        "context": "duvida",
        "kind": "texto",
        "result": "ok",
    }
    before = _value("cobranca_whatsapp_messages_total", message)
    record_message("entrada", "roteada", "duvida", "texto", "ok")
    record_message("entrada", "roteada", "email-do-devedor", "texto", "ok")
    assert _value("cobranca_whatsapp_messages_total", message) == before + 1
    outro = {**message, "context": "outro"}
    assert _value("cobranca_whatsapp_messages_total", outro) >= 1

    received_ok = {"direction": "recebido", "result": "ok", "reason": "aguardando_banco"}
    received_fail = {"direction": "recebido", "result": "falha", "reason": "baixa_confianca"}
    delivered_fail = {"direction": "entregue", "result": "falha", "reason": "envio"}
    ok_before = _value("cobranca_whatsapp_files_total", received_ok)
    fail_before = _value("cobranca_whatsapp_files_total", received_fail)
    delivered_before = _value("cobranca_whatsapp_files_total", delivered_fail)
    record_file("recebido", "aguardando_banco")
    record_file("recebido", "baixa_confianca")
    record_file("recebido", "download")
    record_file("entregue", "envio")
    assert _value("cobranca_whatsapp_files_total", received_ok) == ok_before + 1
    assert _value("cobranca_whatsapp_files_total", received_fail) == fail_before + 1
    assert _value("cobranca_whatsapp_files_total", {"direction": "recebido", "result": "falha", "reason": "download"}) >= 1
    assert _value("cobranca_whatsapp_files_total", delivered_fail) == delivered_before + 1
