# Troubleshooting

Onde olhar quando algo falha. O pedido entra pelo painel ou pelo WhatsApp, passa pelo gateway, cai no serviço dono e só então mexe em banco, fila, Evolution ou no modelo. Se a camada de cima está saudável, desça.

Como subir o cluster e os port-forwards: [`MINIKUBE.md`](./MINIKUBE.md). Sinais (OTLP, Grafana, Prometheus, Loki, Tempo): [`OBSERVABILIDADE.md`](./OBSERVABILIDADE.md). Quem executa cada fluxo: [`../FLUXOS.md`](../FLUXOS.md).

Com o AIOps instalado ([`AIOPS.md`](./AIOPS.md)), os alertas já chegam no Slack com estas evidências coletadas. `@aiops <pergunta>` faz a mesma descida pelas camadas.

## Ordem

1. `kubectl get pods -n cobranca` e o `GET /health` do dono do sintoma.
2. Log desse deploy nos últimos minutos, filtrando o evento da seção do fluxo.
3. Se for conversa, a linha em `messages` (direção e autor) antes de concluir que a IA falou.
4. Trace no Tempo se o HTTP voltou 4xx ou 5xx.
5. Fila e worker se o HTTP foi 202 e nada aconteceu depois.
6. ConfigMap e restart se o log cita variável ausente ou `localhost`.

## 1. O processo está no ar

```bash
kubectl get pods -A
kubectl -n cobranca logs deploy/<nome> --since=15m
kubectl -n cobranca describe pod <pod>
```

| Processo | O que ele faz | Se estiver parado |
| --- | --- | --- |
| `frontend-web` | Painel | A tela não abre |
| `webhook-api` | Gateway: auth e proxy | Login e qualquer chamada do painel falham |
| `cobranca` | Conversa, webhook da Evolution, polling e turno do agente | Mensagem entra no WhatsApp e some |
| `conci-pgto` | Pagamento, extrato, comprovante | Conciliação não anda |
| `cadastro` | Título, configuração, métrica de negócio | Régua e cadastro quebram |
| `worker-cobranca` | Filas `cobranca` e `cobranca-llm` | Régua e turno via Celery não rodam |
| `worker-conciliacao` | Filas `conciliacao` e `conciliacao-llm` | Match e leitura de comprovante param |
| `worker-cadastro` | Fila `cadastro` | Evento do emissor não grava título |
| `relo-disp` | Agenda a régua | Nenhum disparo D+N sai |
| `postgres` / `redis` | Estado e trava do turno | `/health` responde 503 |
| `bootstrap` | Migração e seed, uma vez | Login diz que o tenant não existe |

`GET /health` em cada processo HTTP só fica 200 com Postgres e Redis ok. `sentry` e `langfuse` no corpo são informativos e não derrubam a réplica. No host:

```bash
kubectl -n cobranca port-forward svc/webhook-api 8000:8000
kubectl -n cobranca port-forward svc/cobranca 8001:8000
kubectl -n cobranca port-forward svc/conci-pgto 8002:8000
kubectl -n cobranca port-forward svc/cadastro 8003:8000
```

O painel não usa essas portas. Ele fala com o gateway pelo nome `webhook-api`, gravado na imagem no build (`API_UPSTREAM`).

Armadilhas deste cluster:

| O que aparece | O que é |
| --- | --- |
| Pod `bootstrap` com `Ready=false` no painel Kubernetes — métricas | O Job já terminou (`Succeeded`). Um Job concluído fica não pronto. Não é falha. |
| `ImagePullBackOff` ou `ErrImageNeverPull` | A imagem foi construída no Docker do host. O build tem de ser com `eval "$(minikube docker-env)"`. Ver [`MINIKUBE.md`](./MINIKUBE.md). |
| `port-forward` encerra com `lost connection` | O pod reiniciou. O processo não reconecta. Rode o comando outra vez. |
| PVC `postgres-data` em `Pending` | Falta o addon de storage do Minikube. |

## 2. O pedido HTTP

O gateway é o único que o painel e os webhooks enxergam. Ele encaminha pelo prefixo e devolve 503 se o dono não responder. O mapa está em `api/app/services/routing.py`.

| Prefixo | Dono |
| --- | --- |
| `/conversations`, `/approvals`, `/webhooks/evolution` | `cobranca` |
| `/payments`, `/exceptions`, `/webhooks/banco` | `conci-pgto` |
| `/invoices`, `/settings`, `/metrics`, `/admin`, `/webhooks/emissor` | `cadastro` |

No log do gateway, `gateway.upstream_down` é o dono fora do ar. Um 4xx ou 5xx no span do dono é regra de negócio ou bug daquele serviço. O trace no Tempo mostra os dois: `webhook-api POST /{path:path}` e o POST interno.

Fora de produção, `/docs` de cada serviço lista só as rotas dele. No gateway aparecem auth e health.

Painel abre e as chamadas falham: a imagem web foi construída com outro `API_UPSTREAM`. Rebuild com `http://webhook-api:8000`, como em [`MINIKUBE.md`](./MINIKUBE.md). O `CORS_ORIGINS` do ConfigMap lista só a origem do painel. O browser fala com o Next.js, e o Next.js encaminha para o gateway.

## 3. WhatsApp e o agente

A Evolution desta instalação fica em outro servidor. O webhook configurado nela com `http://localhost:8000/...` não alcança o Minikube. Com `EVOLUTION_API_KEY` preenchida, em dev e em produção, o processo `cobranca` puxa as respostas e reconcilia o recibo de saída a cada 8 segundos (`api/app/channels/inbound_sync.py`, `api/app/channels/reconcile.py`).

Ordem:

1. A instância WhatsApp (`Tenant.whatsapp_instance`, no seed `Cobranca`) está conectada na Evolution.
2. O pod tem `EVOLUTION_BASE_URL` na URL pública da Evolution e `EVOLUTION_API_KEY` preenchida. Sem isso, o envio morre em `http://localhost:8080` com `Cannot assign requested address`. `localhost` dentro do pod é o próprio pod.
3. `inbound.synced` grava a mensagem. `inbound.sync_chats_failed` ou `inbound.sync_messages_failed` é a Evolution inacessível ou a chave rejeitada.
4. Conversa em `HUMANO` não aciona o agente. O rodapé "Assuma a conversa para responder" significa que ela ainda está com o agente.
5. Sem `LLM_API_KEY`, o log é `inbound.agent_skipped_no_llm` e o turno não roda. Com a chave, `agent.turn` e um `POST /message/sendText/<instância>` 201. O modelo padrão é `openai:gpt-4o-mini`.
6. Uma bolha verde pode ser a régua, não o modelo. O autor está em `messages.author` (`agente`, `regua:D+5`, `humano:...`).
7. Intenções que não chamam o modelo: `PARAR`, `HOSTIL_SENSIVEL`, `CONTESTACAO`, `JA_PAGUEI`. O log é `inbound.routed` com o outcome.
8. `inbound.agent_failed` é exceção no turno. `inbound.receipt_failed` é comprovante (a mídia não veio em base64). Isso se repete a cada ciclo e não impede a resposta de texto.
9. `inbound.unknown_contact` é a instância do tenant diferente da instância que recebeu a mensagem.

```bash
kubectl -n cobranca logs deploy/cobranca --since=30m | grep -E 'inbound\.|agent\.|gateway\.'
kubectl -n cobranca exec deploy/postgres -- psql -U cobranca -d cobranca -c \
  "SELECT created_at, direction, author, left(body, 80) FROM messages WHERE conversation_id = '<id>' ORDER BY created_at;"
```

Usuário e senha do Postgres local estão em [`MINIKUBE.md`](./MINIKUBE.md).

O polling só liga quando `ENV` não é `prod` e `EVOLUTION_API_KEY` está preenchida. Em produção a entrada é o webhook `POST /webhooks/evolution`, e o token da URL tem de ser o `WEBHOOK_HMAC`. Token diferente responde 401.

## 4. Os outros fluxos

| Sintoma | Onde olhar | Evento |
| --- | --- | --- |
| Régua não dispara ou dispara fora de hora | `relo-disp` e `worker-cobranca`, fila `cobranca` | `dunning.done`, `dunning.invoice_failed`, `dunning.rate_limited` |
| Desconto ou parcelamento parado em aprovação | tela `/aprovacoes`, estado `AGUARDANDO_APROVACAO` | o grafo só segue depois da decisão |
| Comprovante não vira pagamento | `worker-conciliacao`, fila `conciliacao-llm` | `receipt.processed` |
| Extrato ou pagamento do banco não concilia | `conci-pgto` e fila `conciliacao` | `reconcile.done` |
| Emissor não cria título | `cadastro` e fila `cadastro`, token do webhook | `ingest.done` |

As filas estão em `api/app/services/queues.py`. Worker parado ou fila crescendo explica tarefa que sumiu depois do HTTP 202.

| Fila | Worker | Task |
| --- | --- | --- |
| `cobranca-llm` | `worker-cobranca` | entrada do WhatsApp e turno do agente |
| `cobranca` | `worker-cobranca` | régua |
| `conciliacao-llm` | `worker-conciliacao` | comprovante |
| `conciliacao` | `worker-conciliacao` | matching |
| `cadastro` | `worker-cadastro` | evento do emissor |

No dev, o turno disparado pelo polling roda dentro do processo `cobranca`, sem passar pelo Celery. O webhook de produção e a régua usam o worker.

## 5. Dados e configuração

Tudo que os pods leem no Minikube está no ConfigMap `cobranca-env` (`k8s/minikube.yaml`). Mudança de variável só vale depois de `kubectl -n cobranca rollout restart` do deploy que a usa. O processo guarda a configuração em memória.

| Variável | Efeito se estiver vazia ou errada |
| --- | --- |
| `EVOLUTION_BASE_URL` / `EVOLUTION_API_KEY` | Não lê nem envia WhatsApp |
| `LLM_API_KEY` | Agente não responde |
| `WEBHOOK_HMAC` | Webhook da Evolution responde 401 |
| `JWT_SECRET` | Sessão do painel inválida |
| `DATABASE_*` / `REDIS_*` | `/health` 503 |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Sem trace, log estruturado e métrica OTLP. A aplicação segue |

`SENTRY_DSN` e as chaves do Langfuse são opcionais. Vazias, o `/health` mostra `off`.

Login local: `operador@demo.local`, tenant `demo`. Se o tenant não existe, o Job `bootstrap` não completou.

```bash
kubectl -n cobranca logs job/bootstrap
```

O Job concluído não roda de novo. Para repetir a migração, apague o Job e aplique o manifesto outra vez. O passo a passo está em [`MINIKUBE.md`](./MINIKUBE.md).

## 6. Observabilidade

Grafana no Minikube: `kubectl -n observability port-forward svc/grafana 3001:3000`, usuário `admin`, senha `admin`. Os três ambientes estão em [`OBSERVABILIDADE.md`](./OBSERVABILIDADE.md).

| Painel | Serve para | Limite neste cluster |
| --- | --- | --- |
| Cobrança — aplicação | HTTP, 5xx, filas, Postgres, Redis, logs, traces | O datasource é o Thanos |
| Kubernetes — métricas | Nó, pod não pronto, restart, CrashLoop | CPU e memória de container ficam em zero. O cAdvisor entrega o label `container` vazio e o `metric_relabel` em `k8s/observability/prometheus.yml` descarta a série. Os stat de CPU e memória usam `or vector(0)`, então mostram 0 em vez de vazio |
| Kubernetes — logs | Volume e erro por pod no Loki | |
| Kubernetes — traces | Taxa, erro, duração e o trace | O exemplar abre o Tempo |

No Tempo, o span com erro tem `http.status_code` e, no envio ao WhatsApp, a URL `sendText`. No Loki, o `trace_id` do structlog abre esse span. O Prometheus raspa `GET /internal/metrics` direto no processo, sem passar pelo gateway. Falha ao exportar OTLP não derruba cobrança nem conciliação.

Disco do host e condições do nó usam outras métricas (`system_filesystem_*` e `kube_node_status_condition`) e não dependem do cAdvisor.
