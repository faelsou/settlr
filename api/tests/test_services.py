"""Fronteira dos microserviços: cada caminho e cada task tem um dono só."""

from pathlib import Path

import pytest

from app.services.queues import TASK_ROUTES, WORKER_QUEUES, queue_for
from app.services.routing import owner_of

TASKS = {
    "app.dunning.tasks.run_dunning": "cobranca",
    "app.dunning.tasks.run_dunning_tenant": "cobranca",
    "app.dunning.tasks.check_promises": "cobranca",
    "app.channels.tasks.process_inbound": "cobranca-llm",
    "app.agent.tasks.run_agent_turn": "cobranca-llm",
    "app.agent.tasks.resume_agent": "cobranca-llm",
    "app.reconciliation.tasks.reconcile": "conciliacao",
    "app.receipts.tasks.process_whatsapp_receipt": "conciliacao-llm",
    "app.ingest.tasks.import_invoices": "cadastro",
    "app.ingest.tasks.handle_issuer_event": "cadastro",
    "app.ingest.tasks.settle_issuer_charges": "cadastro",
}

PATHS = {
    "/conversations": "cobranca",
    "/conversations/deliveries": "cobranca",
    "/conversations/abc/messages": "cobranca",
    "/approvals/1/decide": "cobranca",
    "/webhooks/evolution": "cobranca",
    "/payments": "conciliacao",
    "/payments/export": "conciliacao",
    "/payments/1/receipt": "conciliacao",
    "/exceptions/1/confirm": "conciliacao",
    "/webhooks/banco": "conciliacao",
    "/invoices/import": "cadastro",
    "/debtors/1/whatsapp": "cadastro",
    "/settings": "cadastro",
    "/metrics": "cadastro",
    "/admin/tenants": "cadastro",
    "/webhooks/emissor": "cadastro",
    "/health": None,
    "/auth/dev-login": None,
    "/me": None,
}


@pytest.mark.parametrize(("path", "owner"), PATHS.items())
def test_caminho_tem_um_dono(path: str, owner: str | None) -> None:
    assert owner_of(path) == owner


@pytest.mark.parametrize(("task", "queue"), TASKS.items())
def test_task_vai_para_a_fila_do_dono(task: str, queue: str) -> None:
    assert queue_for(task) == queue
    assert any(queue in owned for owned in WORKER_QUEUES.values())


def test_rotas_do_celery_sao_as_do_catalogo() -> None:
    from app.workers.celery_app import celery_app

    assert celery_app.conf.task_routes == TASK_ROUTES


def test_metricas_prometheus_ficam_no_processo() -> None:
    from fastapi.testclient import TestClient

    from app.services.gateway import app

    assert owner_of("/internal/metrics") is None
    assert owner_of("/metrics") == "cadastro"
    with TestClient(app) as client:
        assert client.get("/nao-existe").status_code == 404
        response = client.get("/internal/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "cobranca_http_requests_total" in response.text


def test_gateway_nao_engole_caminho_desconhecido() -> None:
    from fastapi.testclient import TestClient

    from app.services.gateway import app

    with TestClient(app) as client:
        response = client.get("/nao-existe")
    assert response.status_code == 404
    assert response.json()["detail"] == "não encontrado"


def test_stack_sobe_os_tres_servicos_e_as_filas() -> None:
    stack = (Path(__file__).resolve().parents[2] / "docker" / "stack.yml").read_text()
    for name in ("cobranca", "conciliacao", "cadastro"):
        assert f"app.services.{name}:app" in stack
        queues = ",".join(WORKER_QUEUES[name])
        assert f"worker -Q {queues} " in stack
    assert "app.services.gateway:app" in stack or "app.main:app" in stack


def test_claude_4_5_nao_recebe_temperature() -> None:
    from app.core.llm import _sampling

    assert _sampling("anthropic:claude-sonnet-4-5") == {}
    assert _sampling("openai:gpt-4o-mini") == {"temperature": 0}
