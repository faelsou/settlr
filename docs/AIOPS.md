# AIOps no Slack

O Prometheus dispara, o Alertmanager agrupa e inibe, e o processo `aiops` correlaciona os alertas num incidente. Ele coleta as evidências, pede ao LLM a causa provável e posta no Slack com um botão de remediação. Também responde perguntas livres: `@aiops por que o cobranca está com 5xx?`.

A regra de ouro do projeto vale aqui também: **o LLM só explica**. A coleta, a correlação e qualquer ação no cluster são código determinístico, com uma lista fechada de ações, aprovação humana e verificação depois.

Código: `api/app/aiops/`. Processo: `uvicorn app.services.aiops:app`. Manifestos: [`k8s/aiops`](../k8s/aiops/aiops.yaml) e [`k8s/observability/alertmanager.yaml`](../k8s/observability/alertmanager.yaml).

## O ciclo

```text
Prometheus (regras em files/cobranca.yml e k8s.yml)
  → Alertmanager: agrupa por alertname/service/pod e inibe o sintoma quando a causa já alerta
  → POST /aiops/alertmanager (Bearer AIOPS_WEBHOOK_TOKEN)
  → correlação: alertas do mesmo deployment = um incidente (5xx + latência + restart)
  → evidências em paralelo: métricas do runbook, pods, eventos, histórico de rollout, logs de erro
  → especialistas da área (Kubernetes, engenharia, banco) e o SRE sintetiza o diagnóstico
  → ação filtrada pela lista permitida do runbook
  → Slack: problema, troubleshooting, ação sugerida, Aceitar e resolver, Grafana e Kubernetes
  → aceite → agente resolutor executa, verifica o rollout, silencia o alerta e fecha o incidente
  → Slack: status Resolvido, a ação tomada e o postmortem no card e na thread
```

| Prática | Onde está |
| --- | --- |
| Redução de ruído: agrupamento, inibição, deduplicação | `files/alertmanager.yml` e `IncidentStore.ingest` (repetição não gera mensagem) |
| Correlação por serviço afetado | `runbooks.correlation_key` |
| Correlação com mudança (deploy recente é o primeiro suspeito) | `collect_evidence` lê as ReplicaSets; rollout com menos de 60 min vira evidência e prioriza rollback |
| Runbook como código | `runbooks.RUNBOOKS`, espelho de [`TROUBLESHOOTING.md`](./TROUBLESHOOTING.md) |
| Humano no circuito | todo botão pede confirmação; `SLACK_APPROVERS` restringe quem aprova |
| Freio de remediação | cooldown por deployment (`AIOPS_COOLDOWN_SECONDS`) e teto por hora (`AIOPS_MAX_ACTIONS_PER_HOUR`) |
| Menor privilégio | Role em `cobranca` com `patch` só nos Deployments sem estado (`resourceNames`) |
| Verificação depois da ação | `Remediator.verify` espera o rollout e conta na thread |
| Degradação | sem LLM, heurística; sem Loki ou Prometheus, a falha vira evidência; sem Slack, log |
| Postmortem blameless | `diagnose.postmortem` no card e na thread quando o incidente fecha |
| Métricas do próprio AIOps | `aiops_alerts_total`, `aiops_incidents_total`, `aiops_actions_total`, `aiops_diagnoses_total`, `aiops_time_to_resolve_seconds` (MTTR) |

## O que ele pode fazer

| Alerta | Ações permitidas |
| --- | --- |
| `CobrancaHttp5xx`, `TaskCeleryFalhou`, `KubePodNaoReady` | rollback, restart |
| `KubePodCrashLoop` | rollback |
| `CobrancaLatenciaAlta`, `FilaCeleryCrescendo` | scale, restart |
| `KubeContainerCPUThrottled` | scale |
| `CobrancaAlvoFora`, `KubeMemoriaSaturada` | restart |
| `DeploymentSemReplica`, `AplicacaoIndisponivel` | scale para 1 se o spec está em 0; rollback se o rollout é novo; senão restart |
| `KubePodOOM` | nenhuma: o ajuste é o limit de memória no manifesto |
| `PostgresFora`, `RedisFora`, qualquer outro | nenhuma: só humano |

Limites que nenhum prompt muda:

- A ação tem de ser no deployment do incidente e estar no runbook de um dos alertas dele. A exceção é voltar de 0 para 1 réplica: o serviço está no chão e restart não cria pod.
- O incidente só fecha com pelo menos 1 réplica disponível. 0/0 não conta como rollout concluído e o alerta não é silenciado.
- `relo-disp` nunca escala, porque duas réplicas do beat disparam a régua em dobro.
- Deployment com HPA (`webhook-api`) não recebe scale para cima. A exceção é 0 para 1: sem pod o HPA de CPU não tem métrica e não sobe sozinho.
- Indisponibilidade (0 réplicas pedidas ou 0 disponíveis) abre o Slack cerca de 10 segundos depois, lendo a API do Kubernetes. O botão executa a ação do troubleshooting, não a sugestão solta do modelo.
- O scale vai até `AIOPS_MAX_REPLICAS`.
- Rollback só existe se houver uma revisão anterior. Ele volta o template da ReplicaSet anterior, como o `kubectl rollout undo`.
- A migração do banco não é desfeita. Rollback de imagem depois de migração destrutiva é decisão humana.
- Com `AIOPS_DRY_RUN=true`, tudo é proposto e nada é aplicado.

Ação sem clique só com opt-in explícito: `AIOPS_AUTO_ACTIONS='["restart"]'`. O padrão é vazio.

## 1. App no Slack

Em [api.slack.com/apps](https://api.slack.com/apps), use **Create New App → From a manifest** e cole:

```yaml
display_information:
  name: AIOps Cobrança
features:
  bot_user:
    display_name: aiops
    always_online: true
  slash_commands:
    - command: /aiops
      description: Status, incidentes ou uma pergunta
      usage_hint: "status | incidentes | por que a fila cobranca-llm cresceu?"
oauth_config:
  scopes:
    bot: [app_mentions:read, chat:write, commands]
settings:
  event_subscriptions:
    bot_events: [app_mention]
  interactivity:
    is_enabled: true
  socket_mode_enabled: true
```

Depois:

1. **Basic Information → App-Level Tokens**: gere um token com `connections:write`. Esse é o `SLACK_APP_TOKEN` (`xapp-`).
2. **Install App**: instale no workspace. Copie o **Bot User OAuth Token**: é o `SLACK_BOT_TOKEN` (`xoxb-`).
3. No canal (`#aiops` por padrão), rode `/invite @aiops`.

O Socket Mode abre uma conexão de saída. O Minikube não precisa de URL pública. Em produção, atrás do Traefik, dá para usar HTTP: desligue o Socket Mode no app, preencha `SLACK_SIGNING_SECRET` e aponte Events, Interactivity e o slash command para `/slack/events`, `/slack/interactions` e `/slack/commands`. A assinatura v0 é verificada, com janela de 5 minutos contra replay.

## 2. Minikube

A imagem precisa conter `app/aiops`. A tag que está em `k8s/aiops/aiops.yaml` é anterior a ele. Use a tag do próximo push na `main` ou construa local:

```bash
eval "$(minikube docker-env)"
docker build -f docker/api.Dockerfile -t faelsouz/cobranca-api:aiops .
```

Secrets fora do git:

```bash
kubectl -n observability create secret generic aiops-secrets \
  --from-literal=SLACK_BOT_TOKEN=xoxb-... \
  --from-literal=SLACK_APP_TOKEN=xapp-... \
  --from-literal=AIOPS_WEBHOOK_TOKEN="$(openssl rand -hex 24)" \
  --from-literal=LLM_API_KEY=sk-...

kubectl -n observability create secret generic critical-page \
  --from-literal=SLACK_CRITICAL_WEBHOOK=https://hooks.slack.com/services/...
```

O segundo Secret é o webhook de entrada do Slack no `#incidente`. Ele não passa pelo processo `aiops`. O dono é Rafael de Souza. Sem ele, o Alertmanager sobe e o receiver `critical` não entrega; o receiver `aiops` continua.

Aplicar, nesta ordem:

```bash
kubectl apply -k k8s/observability     # Alertmanager e o Prometheus apontando para ele
kubectl -n observability rollout restart deploy/prometheus
kubectl apply -k k8s/aiops
kubectl -n observability set image deploy/aiops aiops=faelsouz/cobranca-api:aiops   # se construiu local
kubectl -n observability rollout status deploy/aiops
```

O `scripts/deploy-minikube.sh` atualiza a imagem do `aiops` junto com a aplicação quando o deployment existe.

Conferir:

```bash
kubectl -n observability port-forward svc/aiops 8099:8000 &
curl -s localhost:8099/health
# {"service":"aiops","slack":"socket","llm":"on","kubernetes":"on","dry_run":false,"incidentes_abertos":0}
```

`slack: off` significa que falta o `SLACK_BOT_TOKEN`. `kubernetes: off` significa que o pod está sem ServiceAccount.

## 3. Testar

Um alerta de mentira, direto no Alertmanager:

```bash
kubectl -n observability port-forward svc/alertmanager 9093:9093 &
curl -s -XPOST localhost:9093/api/v2/alerts -H 'content-type: application/json' -d '[{
  "labels": {"alertname": "CobrancaHttp5xx", "service": "cobranca", "severity": "warning"},
  "annotations": {"summary": "5xx em cobranca (teste)"}
}]'
```

Em cerca de 30 segundos (`group_wait`), aparece a mensagem no canal. Para fechar o incidente, mande o mesmo alerta com `"endsAt"` no passado.

Uma falha de verdade: `kubectl -n cobranca set image deploy/cadastro cadastro=busybox:1.36`. O container não tem `uvicorn` e entra em CrashLoop. Em cerca de 5 minutos (`for` da regra), `KubePodCrashLoop` chega no canal com o rollout novo como evidência e o botão **Rollback de cadastro**. O pod antigo continua servindo durante o teste, porque o rolling update não derruba a réplica pronta.

No Slack:

| Comando | Resposta |
| --- | --- |
| `/aiops` ou `/aiops status` | alvos fora, 5xx, filas e pods não prontos |
| `/aiops incidentes` | incidentes abertos (só para você) |
| `/aiops <pergunta>` ou `@aiops <pergunta>` | investigação com ferramentas só de leitura: PromQL, Loki, pods, eventos, rollouts |

## Configuração

| Variável | Padrão | Efeito |
| --- | --- | --- |
| `SLACK_BOT_TOKEN` | vazio | Sem ele, as mensagens vão só para o log |
| `SLACK_APP_TOKEN` | vazio | Liga o Socket Mode |
| `SLACK_SIGNING_SECRET` | vazio | Liga as rotas HTTP do Slack |
| `SLACK_CHANNEL` | `#aiops` | Canal dos incidentes |
| `SLACK_APPROVERS` | `[]` | IDs (`U0...`) que podem aprovar ações. Vazio = qualquer um do canal |
| `AIOPS_WEBHOOK_TOKEN` | vazio | Bearer do Alertmanager. Vazio só é aceito com `ENV=dev` |
| `LLM_API_KEY` / `LLM_MODEL` | vazio / `openai:gpt-4o-mini` | Sem chave, usa a heurística do runbook |
| `AIOPS_AUTO_ACTIONS` | `[]` | Ações que rodam sem clique |
| `AIOPS_DRY_RUN` | `false` | Propõe sem aplicar |
| `AIOPS_COOLDOWN_SECONDS` | `600` | Intervalo mínimo entre ações no mesmo deployment |
| `AIOPS_MAX_ACTIONS_PER_HOUR` | `6` | Teto global |
| `AIOPS_MAX_REPLICAS` | `3` | Teto do scale |
| `AIOPS_PROMETHEUS_URL` / `AIOPS_LOKI_URL` | `thanos-query:9090` / `loki:3100` | Fontes de evidência |

## Limites conhecidos

- O estado dos incidentes fica em memória, com uma réplica. Num restart, o próximo `repeat_interval` (4 h) reabre como incidente novo o que ainda estiver disparando.
- O receiver `critical` do Alertmanager posta `severity=critical` direto no `#incidente`, pelo webhook `SLACK_CRITICAL_WEBHOOK`, sem chamar este processo. O dono é Rafael de Souza. O mesmo alerta segue para o `aiops`. Sem o secret, essa segunda entrega não sai; a primeira continua.
- O LLM recebe métricas, eventos e até 25 linhas de log. Os logs da aplicação não devem conter dado pessoal do devedor. Revise antes de apontar para um modelo externo.
- No Compose e no Swarm não há Alertmanager. O AIOps está ligado só no Minikube.
