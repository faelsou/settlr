# SRE no Settlr

Como operar o Settlr com as práticas do livro *Site Reliability Engineering* (Beyer, Jones, Petoff e Murphy, Google). O livro trata confiabilidade como funcionalidade com orçamento, não como “nunca cair”. Este arquivo aplica isso à cobrança, à conciliação e ao painel.

O desenho de falha e de consistência está em [DESENHO.md](./DESENHO.md). Sinais e painéis, em [OBSERVABILIDADE.md](./OBSERVABILIDADE.md). Onde olhar numa falha, em [TROUBLESHOOTING.md](./TROUBLESHOOTING.md). Alerta, remediação e o texto curto do Slack, em [AIOPS.md](./AIOPS.md). Backup e rollback de imagem, em [ARQUITETURA-DEPLOY.md](../ARQUITETURA-DEPLOY.md).

---

## 1. O que entra e o que fica de fora

SRE aqui é o trabalho de manter as jornadas abaixo dentro do combinado, com gente de plantão, mudança segura e aprendizado depois do incidente.

| Jornada | Quem sente | O que “funcionou” significa |
| --- | --- | --- |
| Dinheiro que entra | Operador e caixa | Webhook ou extrato vira no máximo um `payment`; baixa só com banco |
| Régua | Devedor | A etapa vigente sai no horário, uma vez por canal |
| Resposta no WhatsApp | Devedor | A mensagem entra, o turno termina em resposta, exceção ou opt-out |
| Painel | Operador | Login, filas e a decisão humana gravam `audit_log` |
| Isolamento | Tenant | Nenhuma leitura cruza `tenant_id` |

Três regras do livro, já visíveis no código:

1. **Confiabilidade tem custo.** Perseguir 100% de disponibilidade trava o produto. O alvo é um SLO, e o que sobra é orçamento de erro para mudança.
2. **Correção de dinheiro não entra nesse orçamento.** Baixa duplicada, comprovante que quita sozinho e vazamento entre tenants são defeito, não “minuto de instabilidade”. Qualquer ocorrência é incidente.
3. **Simplicidade é o controle.** Um Postgres, fila por dono, Beat e Evolution em uma réplica, LLM fora da baixa. Cada peça a mais precisa pagar o risco que [DESENHO.md](./DESENHO.md) já aceitou.

O operador que baixa uma exceção faz o produto. Isso não é toil de SRE. Toil é o trabalho manual, repetitivo e sem valor duradouro que cresce com o volume: restart à mão, caça em log sem `trace_id`, deploy repetido, conferência de saúde que o alerta já deveria fazer.

---

## 2. SLI, SLO e SLA

O livro separa três coisas. Misturar as três faz o alerta mentir ou o contrato prometer o que o sistema não mede.

| Termo | Neste produto |
| --- | --- |
| **SLI** | O número medido na jornada: proporção de eventos bons, latência, atraso da régua |
| **SLO** | A meta interna desse SLI numa janela (30 dias no piloto) |
| **SLA** | O que o contrato com o tenant promete, com consequência comercial. Só existe depois do SLO medido. Enquanto a seção 3 de [DESENHO.md](./DESENHO.md) estiver sem número de produção, não há SLA |

O SLI bom descreve o que a pessoa vê, não o que o processo exporta. `up{job="cobranca-http"}` diz se o scrape funcionou. O operador vê o título baixar. Os dois entram no monitoramento; só o segundo fecha o SLO.

### Ponto de partida do piloto

Números abaixo são a proposta para o primeiro mês com tráfego real. Servem para alertar e para decidir se dá para lançar feature. Revisar com os dados; não tratar como contrato.

| Jornada | SLI | SLO proposto | Janela |
| --- | --- | --- | --- |
| Aceite do webhook de banco | Proporção de `POST /webhooks/banco` que responde 202, ou 4xx de assinatura inválida, em menos de 1 s | 99,9% | 30 dias |
| Baixa visível | Do 202 do banco até `payment` persistido (novo ou duplicata idempotente) | 99,9% em 60 s | 30 dias |
| Régua do dia | Títulos elegíveis que ganham a etapa vigente dentro do horário do tenant | 99% no mesmo dia | 30 dias |
| WhatsApp de entrada | Do recebimento até linha de saída em `messages`, exceção ou opt-out | 99% em 2 min, no horário do tenant | 30 dias |
| Painel | Pedidos do gateway que não são 5xx, com p95 abaixo de 2 s | 99,5% | 30 dias |
| Fila humana | Exceção aberta até decisão | meta de produto, não de disponibilidade; acompanhar idade | semanal |

Correção, fora do orçamento de erro (meta: zero no mês; uma ocorrência abre incidente):

- dois `payments` com o mesmo `(tenant_id, e2e_id)` ou o mesmo `file_hash`
- baixa definitiva com origem só `comprovante`
- query de um tenant devolvendo linha de outro
- etapa da régua reenviada no mesmo canal
- `relo-disp` com mais de uma réplica

A latência de 2 s no p95 já é o limiar de `CobrancaLatenciaAlta`. O SLO do painel usa o mesmo número de propósito: o alerta e a meta contam a mesma coisa.

### Como marcar o que [DESENHO.md](./DESENHO.md) deixou em aberto

| Sinal | Onde ler |
| --- | --- |
| PIX confirmado → baixa | span do webhook no Tempo mais a linha em `payments` (`trace_id` no log) |
| Régua | `dunning_events` contra o relógio de abertura do tenant; atraso do Beat aparece como etapa no ciclo seguinte, não como rajada |
| WhatsApp de entrada | painel `WhatsApp — ponta a ponta` e a linha em `messages` |
| Exceção | idade da linha em `exceptions` até o `audit_log` da decisão |

Disponibilidade de 99,9% em 30 dias deixa **43 minutos** de orçamento. 99,5% deixa **3 h 36 min**. A conta é `30 × 24 × 60 × (1 − SLO)`. Minuto em que o SLI fica abaixo da meta consome o orçamento, mesmo que o processo esteja `Running`.

### Política do orçamento

Enquanto a queima dos últimos 30 dias estiver dentro do SLO, mudança de produto segue. Quando a queima passar do orçamento, ou quando a projeção do mês estourar antes do dia 30, o time para feature na jornada afetada e gasta o ciclo em confiabilidade: bug, capacidade, alerta, teste. O livro é explícito nisso para o orçamento não virar slide.

Dono de cada SLO: Rafael de Souza. Ele decide quando a queima da jornada para feature, mesmo nos dias em que também escreve código. Sem esse nome, o número não muda quando a realidade mudar.

Os alertas de hoje são limiar (`5xx`, p95, fila, `up`). Eles pegam saturação e queda. Ainda não medem queima de orçamento. A regra prática, até existir recording rule de SLI: página imediata no caminho do dinheiro e em Postgres/Redis; ticket no restante. A seção 5 lista o corte.

---

## 3. Os quatro sinais

Capítulo de monitoramento do livro: latência, tráfego, erros e saturação. Causa (disco, conexão, deploy) explica o sintoma; o alerta de página nasce do sintoma. CPU alta com a jornada dentro do SLO não acorda ninguém.

| Sinal | O que olhar no Settlr | Onde |
| --- | --- | --- |
| Latência | p95 de `cobranca_http_request_duration_seconds`; tempo do 202 até a baixa | Prometheus / Thanos, Tempo |
| Tráfego | taxa HTTP por serviço; tasks publicadas; `dunning_events` no dia; mensagens inbound | painel `Settlr — aplicação` |
| Erros | 5xx, `celery_tasks_total{state="FAILURE"}`, `leitura_baixa_confianca`, exceções novas, `gateway.upstream_down` | regras em `observability/prometheus/rules/cobranca.yml` |
| Saturação | tamanho das filas Celery, throttle de CPU, working set contra o limit, conexões do Postgres, memória do Redis | regras em `k8s/observability/files/k8s.yml` |

Fila crescendo é saturação do worker, não “erro de negócio”. `sem-dono` é defeito de roteamento: task publicada sem consumidor. Os dois entram no sinal de erro operacional.

Métrica de negócio do painel (`GET /metrics` do cadastro: recuperação, DSO, promessa, baixa automática) não é SLI de SRE. Ela diz se o produto cobra bem. O scrape do Prometheus não usa essa rota.

Falha ao exportar OTLP não pode derrubar cobrança nem conciliação. Já é assim em `app/core/tracing.py`. Perder o Grafana é incidente do observatório, não da régua.

---

## 4. Alerta: página, ticket, silêncio

Página é interrupção. O livro pede que cada página seja acionável, urgente e sobre um sintoma real. Alerta que ninguém sabe o que fazer vira ruído e, no mês seguinte, é ignorado.

| Classe | Quando | Exemplos já no Prometheus | Quem age |
| --- | --- | --- | --- |
| Página | A jornada está quebrada agora, ou o dado pode corromper | `PostgresFora`, `RedisFora`, `CobrancaAlvoFora` no gateway ou na conciliação, `DeploymentSemReplica`, `AplicacaoIndisponivel`, `KubePodCrashLoop` nesses mesmos processos | Humano. O AIOps não remedia Postgres nem Redis |
| Ticket | Dói, cabe em horário comercial, a jornada ainda anda | `CobrancaHttp5xx`, `CobrancaLatenciaAlta`, `FilaCeleryCrescendo`, `TaskCeleryFalhou`, `KubeContainerCPUThrottled`, `KubeMemoriaSaturada`, `KubePodOOM` | Plantão do dia, ou o botão do Slack com aprovação |
| Silêncio | Já é consequência de outro alerta | pod não pronto quando o deployment inteiro está em 0; latência alta quando o alvo está fora | Inibição do Alertmanager |

`severity: critical` hoje mistura página de verdade (`PostgresFora`) com CrashLoop, que às vezes é o rolling update se resolvendo. No piloto, critical só pagina se o runbook manda agir em minutos. O resto desce para ticket. O AIOps já agrupa 5xx, latência e restart do mesmo deployment num incidente só.

Ninguém vigia o vigia no Compose e no Swarm: o AIOps está ligado no Minikube. Em produção, `severity=critical` tem um segundo receiver, `critical`, no Alertmanager. Ele posta direto no Slack `#incidente` pelo webhook `SLACK_CRITICAL_WEBHOOK` e não chama o processo `aiops`. O alerta continua também no receiver `aiops`. O dono desse receiver é Rafael de Souza. O desenho está em [AIOPS.md](./AIOPS.md) e em `k8s/observability/files/alertmanager.yml`.

---

## 5. Plantão

Time pequeno não elimina o plantão. Elimina a fantasia de que “alguém vai ver o Grafana”. Uma pessoa está nomeada. O handoff é um parágrafo no `#incidente`: incidentes abertos, mudança nas últimas 24 h, fila que já vinha crescendo.

### Primeira semana do piloto

A semana começa no dia em que a conta `clinica-piloto` ativa. A data de calendário espera essa ativação.

| Dia | Plantão | Canal |
| --- | --- | --- |
| 1 a 7 | Rafael de Souza | Slack `#incidente`. Alerta `critical` também chega pelo receiver `critical` do Alertmanager, sem o processo `aiops` |

No fim do dia 7, o plantonista escreve o handoff no mesmo canal. Quem assume a semana seguinte entra nesse parágrafo.

| Horário | O que pode acordar |
| --- | --- |
| 24 h | Postgres, Redis, gateway ou conciliação fora, suspeita de baixa duplicada ou de dado entre tenants |
| Horário do tenant (padrão 08:00–20:00) | Régua parada, fila `cobranca-llm` ou `conciliacao-llm`, 5xx sustentado, painel lento |
| Nunca de madrugada, salvo SEV-1 | Feature, migração, scale do `relo-disp`, troca de número da Evolution, confirmar exceção “só para destravar” |

O que o plantonista não faz, mesmo com o cluster no colo:

- Escalar `relo-disp`. Duas réplicas disparam a régua em dobro. A idempotência da etapa segura um segundo passe; não segura dois crons como desenho.
- Rollback de imagem depois de migration destrutiva. A imagem volta; o schema não. Decisão de dia, com a migration reversa escrita.
- `AIOPS_AUTO_ACTIONS` com `scale` ou `rollback` sem opt-in explícito. O padrão é lista vazia: o botão pede confirmação.
- Apagar linha de `payments`, `matches` ou `audit_log` para “corrigir” um caso. A correção passa pela API.

Ferramentas do turno: Grafana (pasta Cobrança), Loki com `trace_id`, Tempo, `kubectl -n cobranca get pods`, `GET /health`. A ordem de descida está em [TROUBLESHOOTING.md](./TROUBLESHOOTING.md). `@aiops` no Slack investiga em leitura; a ação continua humana.

Carga do plantão: se as páginas de um mês forem em maioria não acionáveis, o SLO ou a regra está errado. A correção é no alerta, não “prestar mais atenção”.

---

## 6. Incidente

Incidente é qualquer quebra de SLO, qualquer violação da lista de correção, ou qualquer página. O livro separa papéis para duas pessoas não aplicarem consertos opostos ao mesmo tempo. Num time pequeno, uma pessoa acumula papéis, e mesmo assim anuncia qual está exercendo.

| Papel | Faz | Não faz |
| --- | --- | --- |
| Comando | Declara severidade, pede status, decide a ação seguinte, encerra | Debugar sozinho em silêncio |
| Operação | Executa o runbook, lê evidência, aplica restart ou rollback aprovado | Mudar de plano sem o comando saber |
| Comunicação | Uma linha para quem espera o painel ou o PIX: impacto, próximo update | Prometer horário que o comando não deu |

Severidade:

| Nível | Critério | Ritmo |
| --- | --- | --- |
| SEV-1 | Dinheiro errado, tenant cruzado, Postgres ou Redis fora, gateway e conciliação sem réplica | Update a cada 30 min até estancar |
| SEV-2 | Régua do dia parada, fila de LLM presa, 5xx acima do limiar por mais de 15 min, painel fora | Update na abertura e na resolução |
| SEV-3 | Um sinal de saturação, um tenant lento, warning sem jornada quebrada | Ticket; vira SEV-2 se cruzar o horário do tenant sem dono |

Estancar vem antes da causa. Réplica saudável de volta, webhook idempotente segurando a rajada, fila parada de consumir só se estiver gerando baixa errada. Causa raiz fica para o postmortem, com log e trace, não no meio do `kubectl`.

Mudança recente é o primeiro suspeito. O AIOps já trata rollout com menos de 60 min como evidência. O plantonista faz o mesmo: `kubectl rollout history` antes de tunar pool ou limite de memória.

Estado do incidente no `aiops` mora em memória e numa réplica. Restart no meio do fogo perde o card; o alerta continua no Prometheus. Para SEV-1, o comando anota horário e ação fora do Slack (issue ou o postmortem aberto na hora).

---

## 7. Postmortem sem culpa

O texto de oito linhas que o AIOps grava no card é o rascunho. SEV-1, SEV-2 e qualquer evento da lista de correção ganham postmortem escrito por gente, em até cinco dias úteis, com as ações datadas.

Culpa de pessoa não entra. Entra o que o sistema permitiu: alerta mudo, runbook ambíguo, teste que não cobre o E2E repetido, migração sem reversa. Se o texto precisa de um nome para fazer sentido, o nome é do componente.

Modelo:

```text
Título: <sintoma> em <data>
Severidade:
Jornada afetada e duração:
Orçamento consumido (minutos abaixo do SLO, ou “correção”):
Impacto: tenants, títulos, mensagens, dinheiro (valor só se já estiver no audit_log)

Linha do tempo (horário local):
- detecção (alerta, cliente, painel)
- primeira ação
- estancamento
- fim

O que segurou: idempotência, rollback, healthcheck, alguém no canal
O que falhou: alerta, procedimento, capacidade, mudança

Causa: o mecanismo, em uma frase
Ações: verbo no infinitivo, dono, data, e como saber que ficou pronto
```

Ações sem dono e sem data não entram. “Melhorar o monitoramento” não entra. “Gravar o SLI de baixa no Thanos e alertar quando o p95 do webhook passar de 1 s por 10 min” entra.

O postmortem é público para o time. Cliente do tenant recebe o fato e a correção, não a discussão interna.

---

## 8. Toil e o teto de metade do tempo

Toil, no livro: manual, repetitivo, automatizável, tático, sem deixar o serviço melhor, e que cresce junto com a carga. Engenharia de SRE é o que reduz esse volume.

Num time que também entrega produto, a meta continua: **até metade do tempo em operação** (plantão, ticket, incidente, deploy manual). A outra metade vai para trabalho que sobrevive ao ticket: SLI, teste, runbook, capacidade. Mês em que o plantão come tudo é mês em que o orçamento de erro está sendo gasto em silêncio.

| Toil neste repositório | Saída |
| --- | --- |
| Restart de pod que o CrashLoop já explicou | Runbook do AIOps, com aprovação |
| Descobrir qual serviço dono da rota | `routing.py` e a tabela de [TROUBLESHOOTING.md](./TROUBLESHOOTING.md) |
| Olhar log sem `trace_id` | structlog já propaga; o hábito é abrir o span no Tempo |
| Subir stack e conferir saúde na mão | `/health` no Traefik e as regras `up == 0` |
| Redeploy com tag que não ficou saudável | `failure_action: rollback` e `docker/release.sh` |

O que não vira automação cega: baixa, opt-out, acordo, aprovação. Humano no painel é a última instância do produto. O AIOps segue a mesma regra do LLM: explica e propõe; a lista de ações é código.

---

## 9. Mudança

Release engineering do livro, já parcialmente no Swarm: build reproduzível, rollout que prefere a réplica nova (`start-first`) nos serviços sem estado local, `stop-first` em `relo-disp` e na Evolution, healthcheck que tira a réplica doente, rollback se a tag nova não ficar de pé.

Ordem que não se inverte:

1. Job único de migração (`python -m app.cli migrate`), antes de atualizar a API. Duas réplicas não disputam o lock.
2. Sobe a aplicação. `GET /health` só fica 200 com Postgres e Redis.
3. Se a imagem nova não segura, volta a tag. Se o schema não conversa com a tag antiga, a migration reversa roda antes da imagem.

Checklist de um tenant em produção (o passo a passo de dados está em [CADASTRAR-CLIENTE.md](./CADASTRAR-CLIENTE.md)):

- política, régua, horário, número e base legal gravados; ativação sem isso devolve 422
- webhook de banco com HMAC e `X-Tenant-Id` de teste, repetindo o mesmo E2E e vendo uma linha só
- template oficial no disparo; opt-out testado
- painel do operador abre a fila desse tenant e não a de outro
- alerta critical com o receiver `critical`, dono Rafael de Souza, além do `aiops`
- dono do SLO: Rafael de Souza. Plantão da primeira semana: Rafael de Souza, canal `#incidente`

Carga de leitura do painel: [`scripts/loadtest.py`](../scripts/loadtest.py) (`perf` e `stress`) no gateway, sem confirmar exceção e sem webhook. Não substitui teste do caminho de dinheiro.

---

## 10. Sobrecarga e falha em cascata

O livro trata sobrecarga como modo de operação, não como surpresa. O piloto cabe num nó; o desenho já marca o que muda quando a seção de carga de [DESENHO.md](./DESENHO.md) mostrar saturação.

O que já segura a cascata:

| Pressão | Comportamento |
| --- | --- |
| Webhook em rajada | 202 rápido; a task cai na fila do dono; E2E repetido não cria outro `payment` |
| Dono HTTP fora | Gateway responde 503 e registra `gateway.upstream_down` |
| Réplica sem Postgres ou Redis | `/health` sai da rotação |
| Cron atrasado | Sai só a etapa vigente, não a rajada das anteriores |
| Número no limite | `RateLimited` e o tenant volta em 60 s |
| LLM lento ou fora | Matcher e baixa seguem sem modelo; comprovante fraco vira `leitura_baixa_confianca` |
| Fila `cobranca-llm` | Escala o `worker-cobranca`, nunca o Beat |
| Gateway saturado | HPA de 1 a 4 réplicas, CPU 70%, só no `webhook-api` |

O que propaga se ninguém cortar:

- Redis único é broker, lock de baixa e debounce. Redis fora para saúde, fila e trava juntos. Não há barramento durável. Task perdida no restart é o limite do ADR-002; se isso passar a perder dinheiro ou mensagem aceita, a fila muda de tecnologia.
- Postgres único no nó `data`. Réplica de leitura só entra com CPU ou disco no limite, e a baixa continua no primário.
- Retry sem teto no webhook de banco, se algum cliente ignorar o 202 e martelar, enche a fila `conciliacao`. O freio é a idempotência mais o alerta `FilaCeleryCrescendo` (acima de 50 por 10 min). Não se adiciona retry infinito no worker para “garantir”.
- Escalar tudo porque uma fila cresceu. `relo-disp` fica em 1. Deployment com HPA não recebe scale manual para cima, salvo de 0 para 1, quando não há métrica de CPU.

Degradação aceitável no piloto: comprovante fica `aguardando_banco`; acordo acima do teto pausa em `approvals`; régua atrasada espera o próximo ciclo. Degradação inaceitável: perder o webhook que já respondeu 202 sem trilha, ou quitar título duas vezes.

---

## 11. Integridade do dado

Capítulo de estado crítico do livro, e o que mais importa neste produto. Disponibilidade se recupera com réplica. Baixa errada se recupera com pessoa, `audit_log` e, se preciso, restore.

Defesa que já está no código e no schema:

- unicidade `(tenant_id, e2e_id)` e `(tenant_id, file_hash)`
- lock `lock:payment:{id}` por 30 s
- match de comprovante só provisório até extrato ou webhook
- baixa, status e `audit_log` na mesma transação
- RLS com role que não é superuser
- etapa da régua única por título, etapa e canal
- confirmação no painel sem banco devolve 409

Backup previsto, ainda como procedimento e não como drill automático: `pg_dump -Fc` diário de `cobranca` e `evolution`, `mc mirror` do bucket `comprovantes`, cópia do volume da Evolution, secrets no cofre. Retenção de 30 dias. Restore em volume novo, com quem escreve no banco parado, e `alembic_version` conferida antes de subir a API. O comando está em [BANCO.md](./BANCO.md) e a tabela em [ARQUITETURA-DEPLOY.md](../ARQUITETURA-DEPLOY.md).

Prática que o livro exige em cima do dump: **restore testado**. Uma vez por trimestre, num volume que não é o de produção, restaurar o dump, subir a API apontando para ele e ler um título, um pagamento e uma linha de `audit_log`. Dump que nunca foi restaurado não é backup.

Retenção de `audit_log` e do bucket segue o contrato do tenant (LGPD). Apagar antes disso, ou guardar para sempre sem cláusula, são os dois erros. O gatilho para política por tenant está na seção 7 de [DESENHO.md](./DESENHO.md).

---

## 12. Teste de confiabilidade

O livro pede teste do caminho infeliz com o mesmo rigor do caminho feliz. O que o repositório já trava em `pytest`: camadas do matcher, régua (opt-out, etapa única, horário), política, comprovante, fronteira de serviço e fila, telefones. Isso protege a correção. Não mede o SLO.

| Tipo | Para que serve | Estado |
| --- | --- | --- |
| Unitário de regra | Impedir baixa, régua e acordo errados | `cd api && pytest` |
| Carga de leitura | Achar o degrau em que o p95 do painel passa de 2 s | `scripts/loadtest.py` |
| Idempotência do webhook | O segundo E2E não publica match de novo | coberto na regra; repetir no piloto com o banco real do tenant |
| Drill de alerta | `PostgresFora` e `AplicacaoIndisponivel` chegam no canal em minutos | fazer antes do primeiro tenant |
| Drill de restore | O dump volta a abrir o produto | trimestral |
| Falha do LLM | Comprovante inválido vira exceção e o matcher não chama modelo | `tests/test_receipts.py` |

Caos no cluster de produção não faz parte do piloto. O equivalente barato é o que [AIOPS.md](./AIOPS.md) já descreve: imagem `busybox` no `cadastro` para ver CrashLoop, rollback e o pod antigo servindo.

---

## 13. O que fechar antes de chamar de produção

Já fechado para o piloto: Rafael de Souza é o dono do SLO e o plantão dos dias 1 a 7, no `#incidente`. O receiver `critical` está no Alertmanager, com o mesmo dono, e não chama o processo `aiops`.

Itens em aberto, em ordem. Cada um muda o risco; nenhum pede reescrever a arquitetura.

1. Medir os cinco SLIs da seção 2 no Thanos (o Prometheus local guarda 6 h; mês pede o histórico longo).
2. Gravar `SLACK_CRITICAL_WEBHOOK` no Secret `critical-page` antes de ativar o primeiro tenant. Sem esse arquivo, o receiver `critical` não entrega; o `aiops` continua recebendo o mesmo alerta.
3. Um restore completo registrado, com tempo gasto.
4. Drill dos alertas `PostgresFora`, `RedisFora` e `AplicacaoIndisponivel`.
5. Trocar limiar solto por queima de orçamento só depois que o SLI existir. Até lá, a tabela da seção 4 é a política.
6. Anotar, no primeiro mês, volume de tenants, mensagens por dia, tamanho do bucket e chamadas de LLM por título. Esses quatro números são a seção de carga de [DESENHO.md](./DESENHO.md).

Enquanto isso, o desenho que vale é o que já está escrito: um banco para o dinheiro, fila por dono, Beat único, modelo fora da baixa, humano na exceção.
