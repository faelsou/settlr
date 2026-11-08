# Desenho do sistema

Perguntas de system design do Settlr, no roteiro do [arc42](https://arc42.org/overview). Contexto, blocos, runtime e deploy já estão escritos; este arquivo só fixa carga, garantia, consistência, falha, decisão e o que muda depois do piloto.

| Seção arc42 | Onde está |
| --- | --- |
| 1. Objetivos | [PRODUTO.md](./PRODUTO.md) e a seção 1 daqui |
| 2. Restrições | Seção 2 daqui |
| 3. Contexto | [Settlr — Arquitetura.md](../Settlr%20%E2%80%94%20Arquitetura.md) |
| 4. Estratégia | Seção 4 daqui |
| 5. Blocos | [TECNICA.md](./TECNICA.md) |
| 6. Runtime | [FLUXOS.md](../FLUXOS.md) |
| 7. Deploy | [ARQUITETURA-DEPLOY.md](../ARQUITETURA-DEPLOY.md) e [INFRA.md](./INFRA.md) |
| 8. Conceitos transversais | Seção 5 daqui |
| 9. Decisões | Seção 6 daqui |
| 10. Qualidade | Seções 1 e 3 daqui e [SRE.md](./SRE.md) |
| 11. Riscos | Seção 7 daqui |
| 12. Glossário | Seção 8 daqui |

---

## 1. Carga

Envelope do produto, ainda sem medição de produção. O cliente da primeira onda tem 100 a 5.000 cobranças por mês, PIX e boleto, um operador no painel. O piloto cabe num nó. A produção desenhada separa os nós `ingress`, `app` e `data`; Postgres, Redis, MinIO e Evolution ficam com uma réplica no nó de dados.

| Grandeza | Envelope | Onde isso mora |
| --- | --- | --- |
| Títulos | 100 a 5.000 por tenant por mês | `invoices` |
| Régua | No máximo a etapa vigente por título e canal; atraso do cron não dispara a rajada | `dunning_events`, Beat `run_dunning` |
| Conversas e LLM | Proporcional a quem responde, manda comprovante ou pede acordo | filas `cobranca-llm` e `conciliacao-llm` |
| Dinheiro que entra | Um `payment` por comprovante, linha de extrato ou webhook | `payments`, bucket `comprovantes` |
| Webhooks | Evolution, emissor e banco entram pelo gateway e voltam 202 | `webhook-api` |
| Réplicas HTTP | No Minikube o gateway escala de 1 a 4 por CPU a 70% | `k8s/hpa.yaml` |

O que ainda não tem número: quantidade de tenants no piloto, mensagens por dia, tamanho do bucket e chamadas de LLM por título. Esses quatro fecham a seção de carga quando o primeiro cliente estiver no ar.

## 2. Restrições

- Um schema Postgres (`cobranca`), multi-tenant por `tenant_id` e RLS. A role da aplicação não é superuser.
- Baixa, status e `audit_log` na mesma transação. Serviço não chama serviço por HTTP para escrever dinheiro.
- LLM só em intenção, comprovante e conversa. Régua, matcher e baixa são código.
- Comprovante sem extrato ou webhook fica provisório. Confirmar pagamento sem banco devolve 409.
- Secrets fora da imagem e do Git. Migração Alembic em job único, antes de atualizar a API.
- Disparo proativo em template e dentro do horário do tenant. Opt-out interrompe a régua na hora.
- Evolution numa réplica: a sessão do WhatsApp é estado local. O Beat (`relo-disp`) também é uma réplica.

## 3. Garantias

Cenário de qualidade: quando o estímulo acontece, na condição dada, o sistema responde com a medida abaixo. As medidas de correção já estão no código. As de tempo estão em aberto.

| Estímulo | Condição | Resposta | Medida |
| --- | --- | --- | --- |
| Webhook do banco repete o mesmo E2E | Pagamento já registrado | `register_bank_payment` devolve vazio, a task de match não é publicada de novo | HTTP 202, `duplicates` > 0, uma linha em `payments` |
| Operador confirma alocação | Origem ainda é só comprovante | A rota recusa | HTTP 409 |
| Dois workers pegam o mesmo pagamento | Baixa em andamento | O segundo não adquire `lock:payment:{id}` | `LockNotAcquired`, uma baixa |
| Devedor manda o mesmo arquivo outra vez | `file_hash` já existe no tenant | A leitura devolve `duplicado` | Um objeto no MinIO |
| Cron da régua atrasa | Várias etapas já vencidas | Sai só a etapa de maior offset ainda não enviada | Um `dunning_events` por título, etapa e canal |
| Evolution falha no envio | Etapa ainda não gravada | A transação daquele título desfaz | A etapa volta no próximo ciclo |
| Horário fora da janela do tenant | `run_dunning_tenant` | A task retorna `fora_do_horario` | Zero disparos |
| Rate limit do número | Slot por minuto esgotado | A task do tenant reagenda em 60 s | `RateLimited` |
| Leitura do comprovante falha na validação | Valor, data ou E2E inválidos | Nasce exceção | `leitura_baixa_confianca` |
| Pedido de acordo acima do teto | Ex.: 8x com máximo 6 | O grafo pausa em `interrupt` | Linha em `approvals` |
| Postgres ou Redis não respondem | `GET /health` | O processo fica fora da rotação | HTTP não-200 |
| Dono da rota fora do ar | Pedido no gateway | O gateway devolve 503 | Log `gateway.upstream_down` |
| Task sem fila de dono | Rota ausente em `queues.py` | Cai em `sem-dono` | Ninguém consome |

Metas de tempo ainda sem número de produção. O ponto de partida do piloto, o orçamento de erro e o que pagina estão em [SRE.md](./SRE.md). O que marcar:

| Sinal | O que marcar |
| --- | --- |
| PIX confirmado → baixa visível no painel | Do webhook 202 até `payments` conciliado |
| Régua | Do horário de abertura do tenant até o `dunning_events` |
| WhatsApp de entrada | Do 202 da Evolution até a resposta gravada em `messages` |
| Exceção | Da abertura até a decisão do operador |

## 4. Estratégia

Três planos. A borda (`edge`) publica o painel, o gateway e a Evolution. A aplicação (`backend`) tem cobrança, conciliação, cadastro, um worker por serviço e o Beat. Os dados não publicam porta.

O gateway autentica e encaminha. Cada serviço é dono das suas rotas e das suas filas (`cobranca`, `cobranca-llm`, `conciliacao`, `conciliacao-llm`, `cadastro`). Trabalho de outro domínio entra na fila do dono.

O painel fala só com o gateway. O browser não abre cobrança, conciliação nem cadastro, e o Next.js não escreve no Postgres.

## 5. Consistência

| Escrita | Onde fecha | O que pode repetir |
| --- | --- | --- |
| Baixa, status do título, match, `audit_log` | Uma transação no Postgres | O webhook. A segunda vez não cria pagamento |
| Acordo e parcelas | A tool emite PIX ou boleto no emissor e grava na mesma sessão; fora da política o grafo para | A decisão humana retoma pelo `approvals` |
| Régua | Uma transação por título; o evento só entra depois do envio | O cron. Etapa já gravada é `etapa_ja_enviada` |
| Comprovante | Objeto no MinIO e linha `aguardando_banco` | O arquivo. O hash devolve o pagamento existente |
| Match provisório | `matches.provisional` até extrato ou webhook | A sugestão. Quem quita é o banco |
| Mensagem de WhatsApp | Linha em `messages`; status pelo `wa_message_id` | O `messages.update`. Status terminal não regride |
| Turno do agente | Checkpointer no Postgres | O debounce no Redis junta rajadas do mesmo devedor |
| Promessa | Texto registra; só a conciliação marca `cumprida` | O `check-promises` das 07:00 quebra a vencida e retoma a régua |

Isolamento entre tenants: o JWT traz `tenant_id` e `get_db` chama `set_tenant` antes da query. A role `agencia` lê `/admin/tenants` fora do RLS de um tenant só. Webhook da Evolution acha o tenant pela instância. Webhook do banco exige `X-Tenant-Id` e HMAC-SHA256 do corpo. Webhook do emissor exige o token gravado no tenant.

## 6. Decisões

### ADR-001. Um Postgres para o dinheiro

Contexto. Cobrança, conciliação e cadastro leem o mesmo título. Uma baixa mexe em pagamento, match, status e auditoria.

Decisão. Os três serviços usam o database `cobranca`. Nenhum chama o outro por HTTP para dar baixa ou mudar status.

Consequência. A escrita é atômica. O deploy continua simples: um Alembic, um backup.

Limite. Um Postgres no nó `data`. Tenant barulhento divide CPU e disco com os outros. Réplica de leitura entra quando a seção 1 mostrar o banco saturado.

### ADR-002. Fila por dono no Redis

Contexto. Régua, comprovante, match e importação passam de HTTP. O volume do piloto cabe em task, com retry.

Decisão. Celery no Redis: db 0 para debounce e lock, db 1 para broker, db 2 para result. Cada worker escuta só as filas do seu serviço. Task sem rota cai em `sem-dono`.

Consequência. Retry com backoff (`reconcile` até 5, comprovante e emissor até 3 ou 5 em erro de transporte). O lock `lock:{key}` segura a baixa concorrente por 30 s.

Limite. Redis único e fila presa à memória dele. Barramento durável entra se a perda de uma task no meio de um restart passar a perder dinheiro ou mensagem aceita.

### ADR-003. Beat e Evolution em uma réplica

Contexto. Dois crons disparariam a régua duas vezes. A sessão da Evolution é arquivo local.

Decisão. `relo-disp` e `evolution` sobem com uma réplica, `stop-first`. A régua ainda grava uma etapa por título e canal, então um segundo passe no mesmo ciclo não reenvia.

Consequência. Um restart atrasa o ciclo. A etapa cujo envio lançou exceção não fica gravada e sai no ciclo seguinte. Rate limit reagenda o tenant em 60 s.

Limite. Sem líder eleito. Uma segunda sessão de WhatsApp é outro número, não outra réplica da mesma.

### ADR-004. LLM fora da baixa

Contexto. Comprovante, intenção e conversa precisam de leitura. Valor, desconto e match errado viram prejuízo.

Decisão. O modelo preenche `ReceiptExtraction` e escolhe entre opções que `build_payment_options` já gerou. `match_payment` devolve `AUTO`, `PARTIAL`, `SUGGESTION`, `AMOUNT_MISMATCH` ou `UNIDENTIFIED` sem modelo. Validação exige valor positivo, data plausível e E2E no formato esperado.

Consequência. Custo de modelo acompanha a conversa. Leitura fraca vira fila humana. Pedido acima do teto pausa o grafo.

Limite. A fila `conciliacao-llm` e a `cobranca-llm` cresce com o número de quem responde, não com o número de títulos.

## 7. O que muda depois do piloto

A célula em que o tenant mora, por porte, está em [INFRA.md](./INFRA.md). Cada linha abaixo espera um número da seção 1 e vale dentro da célula em que ele já está. Enquanto o número não aparece, o desenho desta página continua o de produção.

| Sinal no piloto | Mudança |
| --- | --- |
| CPU ou disco do Postgres no limite com a carga de um nó | Réplica de leitura para painel e métricas. A baixa continua no primário |
| Task aceita some num restart do Redis | Fila durável no lugar do broker. O lock de baixa pode continuar no Redis |
| Um tenant atrasa a régua dos outros | Fila ou worker separado para esse tenant. O RLS continua igual |
| `audit_log` ou o bucket `comprovantes` crescem além do contrato | Retenção por tenant, definida no contrato (LGPD) |
| Webhook de banco ou emissor passa de rajada curta | Gateway acima de 4 réplicas. A idempotência por E2E e por token continua a barreira |
| Dois números de WhatsApp precisam da mesma sessão | Continua uma Evolution por sessão. O tenant já guarda até cinco números de disparo |

Riscos já aceitos no piloto: pareamento real da Evolution, template oficial, webhook assinado de Asaas, Inter e Efí em cliente vivo, Supabase Auth com `app_metadata.tenant_id`, e a revisão jurídica dos textos da régua. O detalhe está na seção 13 de [TECNICA.md](./TECNICA.md).

## 8. Glossário

| Termo | Neste sistema |
| --- | --- |
| Tenant | Cliente da agência. Toda linha de negócio carrega `tenant_id` |
| Título | `invoices`. Centro da régua, da conversa e da baixa |
| Baixa | Match confirmado pelo banco que muda o status do título |
| Provisório | Match de comprovante ainda sem extrato ou webhook |
| Etapa | Um degrau da régua (D-3, D0, D+1, D+5, D+15, D+30) |
| Exceção | Fila humana: match incerto, valor fora da regra, leitura fraca, contestação, D+30 |
| Gateway | `webhook-api`. Única porta HTTP do painel e dos webhooks |
