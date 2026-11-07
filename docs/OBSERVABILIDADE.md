# Observabilidade

Traces, logs e métricas da aplicação. O detalhe de cada sinal está na seção 10 de [`TECNICA.md`](./TECNICA.md). O runtime de produção está em [`ARQUITETURA-DEPLOY.md`](../ARQUITETURA-DEPLOY.md). No cluster local, o passo a passo está em [`MINIKUBE.md`](./MINIKUBE.md).

A aplicação exporta OTLP (gRPC, porta `4317`) quando `OTEL_EXPORTER_OTLP_ENDPOINT` está preenchido. Vazio desliga. Falha ao exportar não derruba cobrança nem conciliação.

| Sinal | Caminho |
| --- | --- |
| Traces | coletor → Tempo |
| Logs da aplicação e de stdout | coletor ou Promtail → Loki |
| Métricas HTTP (`GET /internal/metrics`) | Prometheus raspa o processo |
| Métricas de recurso | coletor → remote write no Prometheus |
| Histórico no Grafana | Thanos, retenção curta no Prometheus (6 horas) |

Sentry e Langfuse ficam de fora das stacks. Só ligam se as chaves estiverem preenchidas.

## Onde sobe

| Ambiente | Arquivo | Grafana |
| --- | --- | --- |
| Compose local | [`observability/compose.yml`](../observability/compose.yml) | `http://127.0.0.1:3001`, `admin` / `admin` |
| Minikube | [`k8s/observability`](../k8s/observability/kustomization.yaml), namespace `observability` | `kubectl -n observability port-forward svc/grafana 3001:3000` |
| Swarm | [`observability/stack.yml`](../observability/stack.yml), stack `cobranca-obs` | porta 3001 no nó de dados, sem rota no Traefik |

```bash
docker compose -f observability/compose.yml up -d
```

```bash
kubectl apply -k k8s/observability
kubectl -n observability port-forward svc/grafana 3001:3000
```

No Minikube o ConfigMap da API já aponta para `otel-collector.observability.svc.cluster.local:4317`. No Compose, o profile `app` usa `http://otel-collector:4317`. No host, fora do Docker, use `http://127.0.0.1:4317`.

## Painéis

A pasta **Cobrança** abre `Cobrança — aplicação` (HTTP, filas, Postgres/Redis, logs, traces e recursos) e `WhatsApp — ponta a ponta` (mensagem aceita, roteada e enviada, recibo no aparelho em entregue, lido ou falhou, e arquivo recebido ou entregue com ok e falha) nos três ambientes.

No Minikube a pasta **Kubernetes** separa os sinais do cluster: métricas (USE), logs e traces (RED). O coletor desse ambiente não lê o socket do Docker. CPU, memória, disco e rede vêm do hostmetrics em `/hostfs`.
