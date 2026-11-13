# Settlr

Agente de WhatsApp que cobra, negocia e confirma pagamentos, e um motor que confere cada entrada contra o que foi vendido.

Documentação do que foi implementado:

- Produto e regras de negócio: [`docs/PRODUTO.md`](./docs/PRODUTO.md)
- Técnica (módulos, API, painel): [`docs/TECNICA.md`](./docs/TECNICA.md)
- Banco Postgres (criação, roles, RLS): [`docs/BANCO.md`](./docs/BANCO.md)
- Observabilidade (OTLP, Grafana, três ambientes): [`docs/OBSERVABILIDADE.md`](./docs/OBSERVABILIDADE.md)
- Troubleshooting: [`docs/TROUBLESHOOTING.md`](./docs/TROUBLESHOOTING.md)
- AIOps no Slack (alerta → diagnóstico → remediação aprovada): [`docs/AIOPS.md`](./docs/AIOPS.md)
- Índice: [`docs/README.md`](./docs/README.md)

A fonte de verdade dos fluxos está em [`FLUXOS.md`](./FLUXOS.md). O desenho original está em [`Settlr — Arquitetura.md`](./Settlr%20%E2%80%94%20Arquitetura.md). O runtime (Swarm, redes, secrets) está em [`ARQUITETURA-DEPLOY.md`](./ARQUITETURA-DEPLOY.md).

**Regra de ouro:** o LLM só lê comprovante, classifica intenção e conversa na negociação. Régua, matching e baixa são código determinístico.

## Fases do painel

| Fase | Telas | O que entrega |
| --- | --- | --- |
| 1 | Login, Exceções, Pagamentos | Conciliação e revisão humana |
| 2 | Títulos | Histórico da régua e das baixas |
| 3 | Conversas, Aprovações | Assumir o WhatsApp e decidir o que o agente pausou |
| 4 | Configurações, Métricas | Política, régua, horário, recuperação e DSO |

O Next.js nunca escreve no banco. Toda ação passa pelo gateway e pelo serviço dono da rota, que grava `audit_log`.

## Stack

```text
api/            FastAPI + Celery + LangGraph + SQLAlchemy
web/            Next.js (App Router) + TanStack Query
docker/         Swarm (stack.yml) e compose de desenvolvimento
k8s/            Minikube local e a stack de observabilidade do cluster
observability/  coletor OTLP, Prometheus, Thanos, Loki, Tempo e Grafana
```

Microserviços, uma imagem: `webhook-api` (gateway), `cobranca`, `conci-pgto`, `cadastro`, cada um com o seu worker, mais `relo-disp` (régua) e `frontend-web` (painel). O Postgres é compartilhado: baixa, status do título e auditoria ficam na mesma transação. Infra: Postgres 16, Redis 7, MinIO, Evolution API, Traefik.

Traces, logs e métricas saem por OpenTelemetry quando `OTEL_EXPORTER_OTLP_ENDPOINT` está preenchido. O coletor entrega traces ao Tempo, logs ao Loki e métricas de recurso ao Prometheus; o Prometheus também raspa `/internal/metrics`. O Grafana lê o histórico pelo Thanos. Sentry e Langfuse continuam opcionais e ficam desligados sem as chaves.

## Desenvolvimento local

```bash
# 1. Infra
docker compose -f docker/compose.dev.yml up -d

# 2. API — quatro processos. O painel fala só com o gateway em :8000.
cd api
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
python -m app.cli migrate
python -m app.cli seed-demo
uvicorn app.main:app --reload --port 8000
uvicorn app.services.cobranca:app --reload --port 8001
uvicorn app.services.conciliacao:app --reload --port 8002
uvicorn app.services.cadastro:app --reload --port 8003

# 3. Painel (outro terminal)
cd web
cp .env.example .env
npm install
npm run dev
```

Abra `http://localhost:3000`. Login local (sem Supabase):

- e-mail: `operador@demo.local`
- tenant: `demo`

O seed cria a Clínica Demo com títulos, pagamentos, exceções, uma conversa e uma aprovação fora da política.

Para subir os quatro serviços no Docker, em vez dos uvicorn no host:

```bash
docker compose -f docker/compose.dev.yml --profile app up -d --build
```

O profile `app` já aponta o OTLP para `http://otel-collector:4317`. No host, preencha no `api/.env`:

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4317
```

Worker e Beat, se quiser exercitar a régua e o agente. Cada worker escuta só a fila do seu serviço (`-n` evita dois workers com o mesmo nome na máquina):

```bash
cd api && source .venv/bin/activate
celery -A app.workers.celery_app worker -Q cobranca,cobranca-llm -n cobranca@%h --loglevel=info
celery -A app.workers.celery_app worker -Q conciliacao,conciliacao-llm -n conciliacao@%h --loglevel=info
celery -A app.workers.celery_app worker -Q cadastro -n cadastro@%h --loglevel=info
celery -A app.workers.celery_app beat --loglevel=info
```

## Observabilidade local

Sobe depois da rede do compose de desenvolvimento. Grafana em `http://127.0.0.1:3001` (`admin` / `admin`). A pasta **Cobrança** abre o painel da aplicação (HTTP, filas, logs, traces e recursos).

```bash
docker compose -f observability/compose.yml up -d
```

O Prometheus raspa `GET /internal/metrics` nas portas 8000–8003. O `GET /metrics` do cadastro continua sendo a métrica de negócio do painel.

## Minikube

O passo a passo (cluster, build no daemon do Minikube, job de bootstrap, port-forward do painel e do Grafana, rebuild e falhas comuns) está em [`docs/MINIKUBE.md`](./docs/MINIKUBE.md).

```bash
minikube start --memory=4096 --cpus=2
eval "$(minikube docker-env)"
docker build -f docker/api.Dockerfile -t cobranca-api:dev .
docker build -f docker/web.Dockerfile \
  --build-arg NEXT_PUBLIC_API_BASE_URL= \
  --build-arg API_UPSTREAM=http://webhook-api:8000 \
  -t cobranca-web:dev .
kubectl apply -f k8s/minikube.yaml
kubectl -n cobranca wait --for=condition=complete job/bootstrap --timeout=180s
kubectl -n cobranca port-forward svc/frontend-web 3000:3000
```

Painel em `http://127.0.0.1:3000` (`operador@demo.local`, tenant `demo`). A observabilidade é opcional: `kubectl apply -k k8s/observability` e `kubectl -n observability port-forward svc/grafana 3001:3000`.

## Testes

```bash
cd api && source .venv/bin/activate
pytest
```

Cobrem o que não pode depender de LLM: camadas de matching, decisão da régua, opções da política, validação do comprovante e a fronteira entre os serviços.

## Produção

A stack Swarm de referência é `docker/stack.yml`, alinhada à seção 9 de `ARQUITETURA-DEPLOY.md`. A telemetria sobe à parte, com `observability/stack.yml` (coletor OTLP, Prometheus, Thanos, Loki, Tempo e Grafana na porta 3001 do nó de dados, sem rota no Traefik). O padrão de `OTEL_EXPORTER_OTLP_ENDPOINT` é `http://otel-collector:4317`; vazio desliga o OTLP. Sentry e Langfuse não são serviço de nenhuma das duas stacks: só ligam se as variáveis estiverem preenchidas.

CI em pull request (`.github/workflows/ci.yml`): pytest, ruff nos módulos de observabilidade e tipos do painel. Na `main`, `.github/workflows/release.yml` publica `cobranca-api` e `cobranca-web` no GHCR com o SHA do commit e roda `docker/release.sh` no manager. Se a tag nova não ficar saudável, o script republica a anterior. Para voltar uma tag já publicada: Actions → Release → `rollback_to` = SHA. Sem `DEPLOY_HOST`, a pipeline só publica as imagens.

- Painel: `app.settlr.com.br`
- API: `api.settlr.com.br` (`/health`, `/webhooks/evolution`, `/webhooks/emissor`, `/webhooks/banco`)
- WhatsApp: `wa.settlr.com.br`
- Auth do painel: Supabase Auth. O JWT precisa de `app_metadata.tenant_id`.
- Migração: job one-off `alembic upgrade head` **antes** de atualizar os serviços da API. Nenhum deles migra no entrypoint.

## Guardrails

- Nunca envia fora do horário do tenant.
- `opt_out` interrompe a régua na hora.
- Identidade (ex.: dígitos do CPF) antes de mostrar valores.
- Baixa definitiva só com confirmação do banco.
- Deduplicação por `e2e_id` e `file_hash`.
- Tools do agente só devolvem opções que a política já validou.
