# Documentação técnica

O que foi implementado no repositório, como as peças se ligam e onde está cada regra. Complementa [`ARQUITETURA-DEPLOY.md`](../ARQUITETURA-DEPLOY.md) (runtime/Swarm) e [`FLUXOS.md`](../FLUXOS.md) (passo a passo dos fluxos).

---

## 1. O que existe hoje

Monorepo com API Python, painel Next.js e stack Docker.

```text
api/          FastAPI + Celery + LangGraph + SQLAlchemy 2 + Alembic
  app/api/    rotas HTTP (painel, webhooks, auth, admin)
  app/services/ gateway e os três serviços (cobrança, conciliação, cadastro)
  app/core/   config, db/RLS, redis, storage, audit, llm, metrics, tracing
  app/models/ entidades, enums, transições, migration inicial
  app/ingest/ CSV e webhook do emissor
  app/dunning/ régua e promessas (puro + tasks)
  app/channels/ WhatsApp (Evolution) e e-mail
  app/receipts/ extração LLM + validação determinística
  app/reconciliation/ matcher em camadas (sem LLM)
  app/agent/  grafo LangGraph, tools, política, intenção
  app/workers/ Celery + Beat (filas separadas por serviço)
  tests/      matching, régua, política, comprovante, fronteira dos serviços
web/          Next.js App Router — painel das 4 fases
docker/       compose.dev.yml (local) e stack.yml (Swarm)
k8s/          minikube.yaml e k8s/observability (kustomize)
observability/ coletor OTLP, Prometheus, Thanos, Loki, Tempo, Grafana
```

Processos em produção: `frontend-web`, `webhook-api` (gateway), `cobranca`, `conci-pgto`, `cadastro`, `worker-cobranca`, `worker-conciliacao`, `worker-cadastro`, `relo-disp`, mais `postgres`, `redis`, `minio`, `evolution`, `traefik`.

O banco continua um só. O serviço não chama o outro por HTTP para dar baixa ou mudar status: isso precisa da mesma transação. O gateway é quem recebe o painel e os webhooks e encaminha. Task de outro serviço entra na fila do dono (`app/services/queues.py`).

## 2. Decisões de implementação

| Decisão | Escolha | Por quê |
| --- | --- | --- |
| Sem n8n | Módulos Python versionados | Teste, review e rollback por Git |
| LLM só em 3 pontos | Intenção, comprovante, conversa | Custo proporcional à conversa, não ao volume de títulos |
| Matcher sem LLM | `reconciliation/matcher.py` | Dinheiro não pode alucinar |
| Painel sem SQL | Next.js → FastAPI | Regras e `audit_log` num só lugar |
| Multi-tenant | `tenant_id` + RLS | Segunda barreira depois do JWT |
| Auth | JWT HS256 (`app_metadata.tenant_id`) | Mesmo formato do Supabase; em dev a API emite o token |
| Fila | Celery + Redis (db 0 debounce/lock, 1 broker, 2 result) | Já previsto na infra |
| Arquivos | MinIO (S3), bucket `comprovantes` | Comprovante fora do Postgres |

## 3. Processos e filas

| Processo | Comando | Faz |
| --- | --- | --- |
| `webhook-api` | `uvicorn app.main:app --port 8000` | Gateway: `/health`, `/me`, auth, e encaminha o resto |
| `cobranca` | `uvicorn app.services.cobranca:app` | Conversas, aprovações, webhook da Evolution |
| `conci-pgto` | `uvicorn app.services.conciliacao:app` | Pagamentos, exceções, webhook do banco |
| `cadastro` | `uvicorn app.services.cadastro:app` | Títulos, configuração, métricas, agência, webhook do emissor |
| `worker-cobranca` | `celery … worker -Q cobranca,cobranca-llm` | Régua, inbound, agente |
| `worker-conciliacao` | `celery … worker -Q conciliacao,conciliacao-llm` | Matching e comprovante |
| `worker-cadastro` | `celery … worker -Q cadastro` | Importação e evento do emissor |
| `relo-disp` | `celery -A app.workers.celery_app beat` | Agenda `run_dunning` e `check-promises` (07:00) |
| `frontend-web` | Next.js standalone :3000 | Painel do operador |

A fila de LLM da cobrança é `cobranca-llm` (agente e inbound). A do comprovante é `conciliacao-llm`. Não existe mais a fila `default`/`llm`: task sem rota cai em `sem-dono` e ninguém consome.

`/health` só responde 200 se Postgres e Redis respondem. O corpo inclui `service` (`gateway`, `cobranca`, `conciliacao` ou `cadastro`). O Traefik só publica o gateway e tira a réplica doente da rotação.

## 4. Autenticação e tenancy

1. Painel obtém JWT.
   - **Dev:** `POST /auth/dev-login` `{ email, tenant_slug }` — desligado se `ENV=prod`.
   - **Prod:** Supabase Auth; o JWT precisa de `app_metadata.tenant_id` e `role`.
2. FastAPI valida HS256 + `aud=authenticated`.
3. `get_db` abre sessão e chama `set_tenant` (RLS).
4. Role `agencia` acessa `/admin/tenants` sem RLS de um tenant só.
5. Role da aplicação **não** é superuser nem dona das tabelas, para o RLS valer.

Onboarding (agência): criar tenant → política/régua/horário/WhatsApp/base legal → importar base → `POST /admin/tenants/{id}/activate`. Sem esses campos, a ativação devolve 422.

## 5. Modelo de dados (Postgres `cobranca`)

A criação da instância, das roles e do segundo database está em [`BANCO.md`](./BANCO.md). Schema único, multi-tenant. O **título** é o centro.

| Tabela | Papel |
| --- | --- |
| `tenants` | Política, régua, horário, WhatsApp, emissor, base legal |
| `debtors` | Quem deve; `opt_out` |
| `invoices` | Título; `parent_id` / `agreement_id` nas parcelas |
| `dunning_events` | Cada disparo da régua (único por título+etapa+canal) |
| `conversations` / `messages` | Estado do agente e histórico |
| `promises` | Promessa de pagamento |
| `agreements` / `approvals` | Acordo e pedido pausado (`interrupt`) |
| `payments` | Dinheiro que entra (comprovante / extrato / webhook) |
| `matches` | N:N pagamento↔título; `provisional` = ainda sem banco |
| `exceptions` | Fila humana |
| `audit_log` | Quem, o quê, quando, antes/depois |

Índices únicos: `payments (tenant_id, e2e_id)` e `(tenant_id, file_hash)`. Evolution usa o database `evolution`, separado do Alembic.

Transições de status ficam em `app/models/states.py`. Mudar status fora dali é bug.

## 6. Mapa dos módulos (fluxos → código)

| Fluxo | Módulo | Serviço | LLM? |
| --- | --- | --- | --- |
| 0 Onboarding | `api/routes/admin.py` | cadastro | não |
| 1 Ingestão | `ingest/` + `POST /invoices/import` + `POST /webhooks/emissor` | cadastro | não |
| 2 Régua | `dunning/` — Beat `run_dunning` | worker-cobranca | não |
| 3 Inbound WhatsApp | `channels/whatsapp.py` + debounce Redis | cobranca | intenção |
| 4 Agente | `agent/` LangGraph + tools | worker-cobranca | conversa |
| 5 Promessas | `dunning/promises.py` + `check-promises` | worker-cobranca | não |
| 6 Comprovante | `receipts/` | worker-conciliacao | extração |
| 7 Matching | `reconciliation/matcher.py` | worker-conciliacao | não |
| 8 Exceções | `api/routes/exceptions.py` + painel | conciliacao | não |
| 9 Opt-out | inbound + `debtor.opt_out` | worker-cobranca | detecção |

### 6.1 Régua

`dunning/rules.decide` é função pura: opt-out, promessa, etapa vigente, “já enviada”. Horário e rate limit ficam no worker-cobranca (relógio + Redis).

### 6.2 Matcher

`match_payment(payment, candidates, rules)` devolve `AUTO`, `PARTIAL`, `SUGGESTION`, `AMOUNT_MISMATCH` ou `UNIDENTIFIED`. Comprovante sem banco só grava match **provisório**. Banco/webhook aplica baixa e `audit_log`.

Locks Redis em `payment:{id}` evitam baixa duplicada em concorrência.

### 6.3 Comprovante

LLM preenche `ReceiptExtraction` (Pydantic). `receipts/validation.py` exige valor > 0, data plausível, E2E no formato `E|D + 8 + 12 + 11`. Qualquer problema vira `leitura_baixa_confianca`.

### 6.4 Agente

Grafo: identificar → identidade → títulos → classificar → política → opções → aceite → acordo, ou `request_human`.

Tools tipadas: `get_debtor_invoices`, `get_negotiation_policy`, `build_payment_options` (determinístico), `register_promise`, `create_agreement`, `request_human`. Checkpointer no Postgres.

## 7. API HTTP

Rotas públicas (assinatura/token, sem sessão de usuário). O gateway encaminha; a coluna Serviço é quem executa:

| Método | Rota | Origem | Serviço |
| --- | --- | --- | --- |
| GET | `/health` | Traefik | gateway |
| GET | `/me` | Painel | gateway |
| POST | `/auth/dev-login` | Só `ENV!=prod` | gateway |
| POST | `/webhooks/evolution` | Evolution | cobranca |
| POST | `/webhooks/emissor` | Asaas / Inter / Efí | cadastro |
| POST | `/webhooks/banco` | Extrato / PIX | conciliacao |

Rotas do painel (JWT + tenant), também atrás do gateway:

| Prefixo | Ações | Serviço |
| --- | --- | --- |
| `/exceptions` | Listar, confirmar, rejeitar | conciliacao |
| `/payments` | Listar, comprovante, importar OFX/CSV | conciliacao |
| `/invoices` | Listar, detalhe, importar CSV | cadastro |
| `/conversations` | Listar, mensagens, assumir, devolver, enviar | cobranca |
| `/approvals` | Listar, decidir (retoma o grafo no worker-cobranca) | cobranca |
| `/settings` | GET/PUT política, régua, horário, conciliação | cadastro |
| `/settings/whatsapp` | PUT dos números de disparo da empresa (até cinco) | cadastro |
| `/debtors/{id}/whatsapp` | PATCH dos celulares do devedor (até cinco) | cadastro |
| `/metrics` | Recuperação, DSO, promessas, baixa automática | cadastro |
| `/admin/tenants` | CRUD e ativação (role `agencia`) | cadastro |

Fora de produção, cada processo HTTP expõe `/docs` com as rotas que ele mesmo atende. No gateway aparecem auth e health. Conversas, pagamentos e títulos aparecem no `/docs` de cobrança, conciliação e cadastro.

## 8. Painel (`web/`)

- Next.js 15 App Router, TypeScript, Tailwind, TanStack Query. A marca na tela e no título da aba é **Settlr**.
- `output: "standalone"` para a imagem Swarm.
- Cliente em `web/lib/api.ts` — um fetch autenticado por rota.
- A sidebar recolhe. O início junta as métricas dos últimos 30 dias e as três filas que pedem gente: exceções abertas, conversas com humano e aprovações.
- Títulos, pagamentos e exceções usam tabela paginada. Conversas ficam em duas colunas: a lista e a thread na mesma tela.
- Confirmar ou recusar pede um diálogo. O resultado da ação aparece em toast.
- Telas em `web/app/(painel)/`:
  - `/inicio` — filas e métricas
  - `/excecoes` — confirma alocação, corrige comprovante ou resolve contestação
  - `/pagamentos` — status, origem, comprovante, importação de extrato
  - `/titulos` e `/titulos/[id]` — busca, régua, promessas, matches, mensagens e até cinco celulares do devedor
  - `/conversas` — assumir, devolver e enviar
  - `/aprovacoes` — retoma o grafo com mensagem ao devedor
  - `/configuracoes` — política, régua, horário e até cinco WhatsApps de disparo, com escolha de qual envia
  - `/metricas`

`NEXT_PUBLIC_API_BASE_URL` entra no **build**. Trocar de domínio exige rebuild da imagem `cobranca-web`. Sora e Manrope vêm do pacote npm (`@fontsource`); o `next build` não baixa o CSS do Google Fonts.

## 9. Persistência, secrets e deploy

Secrets do Swarm (nunca na imagem nem no Git): `postgres_password`, `redis_password`, `evolution_api_key`, `jwt_secret`, `llm_api_key`, `minio_root_password`, `webhook_hmac`.

URLs internas montadas no entrypoint a partir dos arquivos em `/run/secrets`, para a senha não aparecer em `docker service inspect`.

Migração: job one-off `python -m app.cli migrate` (Alembic + checkpointer) **antes** de atualizar os serviços da API. Duas réplicas não disputam lock de migration. O passo a passo de volume vazio, roles e conferência está em [`BANCO.md`](./BANCO.md).

Atualização: `start-first` em frontend-web, gateway, cobrança, conci-pgto, cadastro e nos três workers; `stop-first` e 1 réplica em relo-disp, evolution e dados. O Swarm usa `failure_action: rollback`. A pipeline (`.github/workflows/release.yml`) republica a tag anterior se a nova não ficar saudável.

Sentry (SaaS) e Langfuse **não** entram no `docker/stack.yml` nem na stack de observabilidade. Sem `SENTRY_DSN`, o gateway, os três serviços, os workers, o relo-disp e o servidor do painel seguem sem enviar erro. Sem `LANGFUSE_PUBLIC_KEY` e `LANGFUSE_SECRET_KEY`, intenção, comprovante e negociação rodam sem o tracing do Langfuse. `LANGFUSE_HOST` (ou `LANGFUSE_BASE_URL`) só aponta o endpoint; vazio usa o cloud. O DSN do browser (`NEXT_PUBLIC_SENTRY_DSN`) entra no build da imagem `cobranca-web`.

## 10. Observabilidade

O mapa dos três ambientes e dos painéis está em [`OBSERVABILIDADE.md`](./OBSERVABILIDADE.md).

Traces, logs e métricas OTLP saem de `app/core/tracing.py` quando `OTEL_EXPORTER_OTLP_ENDPOINT` está preenchido (gRPC, em geral `:4317`). Vazio desliga. Falha ao exportar não derruba cobrança nem conciliação. `SERVICE_NAME` vira o `service.name` do recurso.

| Sinal | Origem | Caminho |
| --- | --- | --- |
| Traces | FastAPI e Celery instrumentados | coletor → Tempo |
| Logs da aplicação | structlog, com `trace_id` | coletor → Loki |
| Logs de stdout | Promtail | Loki |
| Métricas HTTP | `GET /internal/metrics` em cada processo | Prometheus raspa o processo, sem passar pelo gateway |
| Métricas de recurso | hostmetrics; no Compose e no Swarm, também `docker_stats` | coletor → remote write no Prometheus |
| Métrica de negócio | `GET /metrics` do cadastro | painel do operador; o scrape não usa essa rota |

O Prometheus retém 6 horas. O datasource padrão do Grafana é o Thanos. Um log com `trace_id` abre o span no Tempo.

| Ambiente | Sobe com | Grafana |
| --- | --- | --- |
| Compose local | `docker compose -f observability/compose.yml up -d` | `http://127.0.0.1:3001`, `admin` / `admin` |
| Minikube | `kubectl apply -k k8s/observability` | `kubectl -n observability port-forward svc/grafana 3001:3000` |
| Swarm | `BACKEND_NETWORK=cobranca_backend docker stack deploy -c observability/stack.yml cobranca-obs` | porta 3001 no nó de dados, sem router no Traefik |

A pasta **Cobrança** tem o painel `Settlr — aplicação` (HTTP, filas, Postgres/Redis, logs, traces e recursos) e o painel `WhatsApp — ponta a ponta` (mensagem aceita, roteada e enviada, por contexto, e arquivo recebido ou entregue com ok e falha) nos três ambientes. No Minikube a pasta **Kubernetes** separa os três sinais do cluster:

| Painel | O que mostra |
| --- | --- |
| `Kubernetes — métricas` | USE: CPU, memória, disco, throttle do CFS, working set contra o limit, pods e restarts. Fonte: kube-state-metrics e cAdvisor do kubelet |
| `Kubernetes — logs` | volume e erros por pod |
| `Kubernetes — traces` | RED (taxa, erros, duração) a partir das span metrics que o Tempo grava no Prometheus, mais o mapa de serviços |

No Minikube o coletor não usa `docker_stats`: o socket do Docker não entra no pod. CPU, memória, disco e rede vêm do hostmetrics em `/hostfs`. As regras de alerta do cluster estão em `k8s/observability/files/k8s.yml`.

No host, com a API fora do Docker, use `OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4317`. O profile `app` aponta para `http://otel-collector:4317`. O ConfigMap do Minikube aponta para `http://otel-collector.observability.svc.cluster.local:4317`.

## 11. Testes e seed

```bash
cd api && pytest
```

Cobertura atual (determinística):

- `tests/test_matcher.py` — camadas 1–4, parcial, documento mascarado, soma de títulos
- `tests/test_dunning.py` — opt-out, promessa, etapa única, D+30, horário
- `tests/test_policy.py` — desconto, teto de parcelas, data da promessa
- `tests/test_agreement.py` — parcela do acordo nasce com PIX ou boleto; fora da política não vira condição
- `tests/test_money_http.py` — baixa, rejeição, extrato e acordo pelo HTTP, com isolamento entre tenants
- `tests/test_receipts.py` — confiança, E2E, “não é comprovante”
- `tests/test_observability.py` — Sentry, Langfuse e OTLP ficam desligados sem variável
- `tests/test_services.py` — cada caminho HTTP e cada task tem um serviço dono, e o `stack.yml` sobe as filas certas
- `tests/test_phones.py` — até cinco celulares do devedor, normalização e roteamento
- `tests/test_senders.py` — até cinco WhatsApps de disparo da empresa e troca do número que envia
- `tests/test_inbound.py` — mensagem que entra pelo WhatsApp

`python -m app.cli seed-demo` (bloqueado em `ENV=prod`) cria o tenant `demo` (Clínica Demo) com títulos, pagamentos, exceções, conversa e uma aprovação de 8x (acima do teto 6).

## 12. Como rodar local

Ver [`README.md`](../README.md). Resumo: `docker/compose.dev.yml` sobe Postgres `:55432` e Redis `:56379`. No host, o gateway escuta `:8000` e os serviços `:8001` (cobrança), `:8002` (conciliação) e `:8003` (cadastro). O profile `app` sobe os quatro processos no Docker. Login local: `operador@demo.local` / tenant `demo`.

`observability/compose.yml` sobe o coletor e o Grafana em `:3001`. O Minikube usa `k8s/minikube.yaml` para a aplicação e `kubectl apply -k k8s/observability` para a telemetria. O passo a passo de cluster, build, bootstrap e port-forward está em [`MINIKUBE.md`](./MINIKUBE.md).

## 13. O que ainda não é o piloto completo

- Pareamento real do número na Evolution e templates oficiais do WhatsApp
- Webhooks assinados de Asaas/Inter/Efí em cliente vivo
- Supabase Auth + `app_metadata.tenant_id` em produção (dev usa `/auth/dev-login`)
- Revisão jurídica dos textos da régua e do contrato
- Faixas de preço com custo medido no piloto
