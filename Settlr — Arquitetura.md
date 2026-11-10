# Settlr — Arquitetura

Oct 16, 2026 · @Rafael de Souza

## Visão do produto

Um agente de WhatsApp que cobra, negocia e confirma pagamentos, e um motor que confere cada entrada contra o que foi vendido. A promessa ao cliente: **receber mais, mais cedo, sem ninguém da equipe precisar cobrar ou bater planilha.**

**Problema.** Cobrar é constrangedor e fica para depois. Conferir PIX, boleto e cartão contra vendas é tedioso e feito no fim de semana. As duas tarefas mexem direto no caixa, e quase nenhuma PME faz bem.

**Cliente ideal (primeira onda)**

- Negócios com recorrência ou parcelamento: clínicas, escolas e cursos, academias, condomínios, assinaturas, distribuidores B2B.
- Volume de 100 a 5.000 cobranças por mês, recebendo majoritariamente por PIX e boleto.
- Já usam WhatsApp com o cliente e têm alguém (geralmente o dono) fazendo a cobrança na mão.

**Oferta**

- *Cobrança:* régua automática antes e depois do vencimento, segunda via, negociação de parcelamento dentro de limites do cliente, confirmação de pagamento.
- *Conciliação:* leitura de comprovantes enviados no WhatsApp, importação de extrato, baixa automática do título e fila de exceções para revisão humana.
- *Painel:* recebido, em aberto, prometido, em negociação e divergências.

## Arquitetura geral

O desenho de runtime (containers, redes, réplicas) e a stack de deploy em Docker Swarm estão em [`ARQUITETURA-DEPLOY.md`](./ARQUITETURA-DEPLOY.md).

Eventos entram pelo gateway: WhatsApp segue para cobrança, emissor para cadastro, banco para conciliação, e o cron da régua para o worker de cobrança. Os serviços leem e gravam no mesmo Postgres e a cobrança responde ao devedor pelo WhatsApp. O painel não acessa o banco; chama o gateway, então o operador vê o mesmo estado que o agente usa.

## Fluxo de cobrança

A cobrança é uma régua determinística disparada por cron, com o agente de IA entrando só quando o devedor responde. Assim o custo de LLM fica proporcional às conversas, não ao volume de títulos.

**Régua padrão (configurável por cliente)**

| Momento | Ação | Canal |
| --- | --- | --- |
| D-3 | Lembrete amigável com link/PIX copia-e-cola | WhatsApp template |
| D0 | Aviso de vencimento hoje | WhatsApp template |
| D+1 | "Não identificamos o pagamento" + segunda via | WhatsApp template |
| D+5 | Oferta de negociação dentro da política | WhatsApp template |
| D+15 | Última tentativa automática, aviso de encaminhamento | WhatsApp + e-mail |
| D+30 | Sai da régua e vai para fila humana | Painel |

**Quando o devedor responde, o agente classifica a intenção e age:**

1. *Já paguei* → pede o comprovante e envia para o motor de conciliação.
2. *Vou pagar dia X* → registra promessa, pausa a régua até X+1 e reagenda.
3. *Quero parcelar ou desconto* → consulta a política do cliente (entrada mínima, nº máximo de parcelas, desconto máximo) e só oferece o que cabe nela; gera novos títulos ao aceitar.
4. *Contestação ou valor errado* → não negocia, abre exceção e avisa um humano.
5. *Pedido de parar / tom hostil / assunto sensível* → opt-out ou escalonamento imediato.

**Regras duras:** o agente nunca inventa valores, nunca oferece fora da política, nunca ameaça, e cada mensagem é registrada com o título relacionado.

## Fluxo de conciliação

Todo dinheiro que entra vira um registro de pagamento, e cada pagamento tenta casar com um título em aberto. O que casa com confiança é baixado sozinho; o resto vai para uma fila curta de exceções.

**Entradas**

- Comprovante (imagem ou PDF) enviado no WhatsApp pelo devedor ou num grupo do cliente → OCR + extração estruturada por LLM (valor, data/hora, pagador, CPF/CNPJ parcial, ID E2E do PIX, banco).
- Extrato bancário: Open Finance ou extrato do emissor, sem arquivo. OFX/CSV fica só como exceção. Webhook do banco quando o PIX é empurrado.
- Webhook do emissor de cobrança (Asaas, Inter, Efí etc.) quando o título nasce com PIX ou boleto registrado.

**Matching em camadas (para no primeiro que casa)**

1. *Chave exata:* `txid` ou ID E2E do PIX igual ao do título → baixa automática.
2. *Valor + documento do pagador + janela de data* → baixa automática.
3. *Valor + nome aproximado + janela de data*, ou soma de vários títulos do mesmo cliente → sugestão com score, confirmada por humano.
4. Sem candidato → exceção "pagamento não identificado".

**Proteções**

- Deduplicação pelo ID E2E e por hash do arquivo: o mesmo comprovante enviado duas vezes não baixa duas vezes.
- Comprovante só baixa definitivo quando também aparece no extrato/webhook; até lá fica "comprovante recebido, aguardando banco". Isso bloqueia comprovante falso.
- Diferença de valor (juros, desconto, pagamento parcial) gera baixa parcial ou exceção conforme regra do cliente.

## Modelo de dados (Postgres)

Um schema único, multi-tenant por `tenant_id` com Row Level Security. O título é o centro: régua, conversas e pagamentos apontam para ele.

| Tabela | Campos principais | Papel |
| --- | --- | --- |
| `tenants` | id, nome, política de negociação (jsonb), régua (jsonb), número WhatsApp, horário permitido | Configuração por empresa cliente |
| `debtors` | id, tenant\_id, nome, documento, telefone, opt\_out, tags | Quem deve |
| `invoices` | id, tenant\_id, debtor\_id, valor, vencimento, status, txid, linha\_digitavel, parent\_id | Títulos; `parent_id` liga parcelas de um acordo |
| `dunning_events` | id, invoice\_id, etapa, enviado\_em, message\_id, status\_entrega | Cada disparo da régua |
| `conversations` | id, tenant\_id, debtor\_id, intent, estado, resumo, updated\_at | Estado do agente por devedor |
| `promises` | id, invoice\_id, data\_prometida, cumprida | Promessas de pagamento |
| `agreements` | id, debtor\_id, títulos\_origem, condições, aceito\_em | Acordos de parcelamento |
| `payments` | id, tenant\_id, origem (comprovante/extrato/webhook), valor, pago\_em, e2e\_id, pagador\_doc, file\_hash, raw (jsonb) | Todo dinheiro que entra |
| `matches` | payment\_id, invoice\_id, valor\_aplicado, método, score, confirmado\_por | Ligação N:N pagamento↔título |
| `exceptions` | id, tenant\_id, tipo, payment\_id, invoice\_id, status, responsável | Fila de revisão humana |
| `audit_log` | quem, o quê, quando, antes/depois | Rastro para disputa e LGPD |

Índices únicos em `payments.e2e_id` e `payments.file_hash` garantem a deduplicação no banco, não só no fluxo.

## Arquitetura Python e stack

Um único repositório Python. Em produção são o gateway e três serviços de domínio, cada um com o seu worker, mais o Beat. A imagem é uma só (`cobranca-api`); o comando muda por processo. Sem n8n: régua, conciliação e agente continuam módulos versionados no Git e testados com pytest.

O Postgres é compartilhado. Baixa, status do título e auditoria acontecem na mesma transação, então um serviço não chama o outro por HTTP para escrever. O gateway recebe o painel e os webhooks e encaminha. Trabalho de outro serviço entra na fila do dono.

| Antes (n8n) | Agora (módulo Python) | Serviço |
| --- | --- | --- |
| WF-01 Ingest | `ingest/`: rotas do cadastro + task `import_invoices` | cadastro + worker-cadastro |
| WF-02 Régua | `dunning/`: task periódica `run_dunning`, rate limit por número | beat + worker-cobranca |
| WF-03 Inbound | `channels/whatsapp.py`: webhook da Evolution, debounce no Redis | gateway → cobranca |
| WF-04 Comprovante | `receipts/`: extração com `with_structured_output` (Pydantic) | worker-conciliacao |
| WF-05 Conciliação | `reconciliation/`: matcher em camadas, Python puro, sem LLM | worker-conciliacao |
| WF-06 Agente | `agent/`: grafo LangGraph, tools tipadas, checkpointer no Postgres | worker-cobranca |

**Estrutura do repositório**

```text
cobranca/                # monorepo
  api/                   # backend Python, uma imagem, vários processos
    app/
      services/          # gateway, cobranca, conciliacao, cadastro
      api/               # rotas HTTP (painel, webhooks, auth)
      core/              # config (pydantic-settings), db, tenancy, logging
      models/            # SQLAlchemy 2.0 + migrations Alembic
      ingest/            # cadastro
      dunning/           # cobrança
      channels/          # whatsapp (Evolution), email — cobrança
      receipts/          # conciliação
      reconciliation/    # conciliação
      agent/             # graph.py, tools.py, policy.py, prompts.py — cobrança
      workers/           # app Celery; a fila de cada task está em services/queues.py
    tests/
  web/                   # painel Next.js (App Router, TypeScript)
    app/                 # rotas: /excecoes, /pagamentos, /titulos ...
    components/
    lib/api.ts           # cliente HTTP do gateway
  docker/                # Dockerfiles + stack.yml (Swarm)
```

**Por que cada peça**

- *FastAPI + Pydantic v2:* webhooks assíncronos e validação dos payloads da Evolution, do emissor e do banco. O gateway só encaminha; a validação fica no serviço dono.
- *Celery + Redis:* retries com backoff, rate limit por task e agendamento pelo Beat. Cada worker escuta só as filas do seu serviço (`cobranca`, `cobranca-llm`, `conciliacao`, `conciliacao-llm`, `cadastro`).
- *LangGraph:* o agente vira um grafo de estados explícito (intenção → consulta de títulos → proposta → confirmação), com pausa para humano via `interrupt` e memória persistida no Postgres.
- *LangChain:* interface de modelos, `with_structured_output` para comprovante e intenção, tools com schema Pydantic.
- *SQLAlchemy 2.0 + Alembic:* migrations versionadas; o RLS continua no Postgres.
- *Observabilidade:* Langfuse para rastrear cada decisão do agente; Sentry e logs estruturados para o resto. Os dois ficam desligados sem variável.
- *Deploy:* Docker Swarm via Portainer. Topologia, redes, secrets e o `docker/stack.yml` em [`ARQUITETURA-DEPLOY.md`](./ARQUITETURA-DEPLOY.md).

**Regra de ouro:** o LLM só entra na leitura do comprovante, na classificação de intenção e na conversa de negociação. Régua, matching e baixa são código determinístico.

## Painel web (Next.js)

O painel do MVP é um app Next.js no mesmo repositório, falando só com o gateway (`api.<domínio>`). O devedor nunca o vê; ele existe para o cliente resolver o que o agente não resolve sozinho.

| Tela | O que faz | Fase |
| --- | --- | --- |
| Login | Supabase Auth, usuário ligado a um tenant | 1 |
| Exceções | Pagamentos não identificados e sugestões de match com score; confirmar ou rejeitar | 1 |
| Pagamentos | Lista com o comprovante (Storage) e o status: só comprovante ou confirmado pelo banco | 1 |
| Títulos | Busca por devedor, status, histórico da régua e das conversas | 2 |
| Conversas | Histórico do WhatsApp; assumir a conversa e devolver ao agente | 3 |
| Aprovações | Acordos pausados pelo agente aguardando decisão humana | 3 |
| Configurações | Política de negociação, régua, horários e templates | 4 |
| Métricas | Recuperação, DSO, promessas cumpridas, % de baixa automática | 4 |

**Stack do painel**

- *Next.js (App Router) + TypeScript*, com Tailwind, shadcn/ui e TanStack Query.
- *Auth:* Supabase Auth no front; o JWT vai para o gateway e o serviço dono da rota valida e resolve o tenant. O RLS no Postgres é a segunda barreira.
- *Contrato:* o painel chama o gateway por `web/lib/api.ts`. O browser não fala com cobrança, conciliação nem cadastro.
- *Tempo real (opcional):* Supabase Realtime na tabela `exceptions` para a fila se atualizar sozinha.
- *Deploy:* container `frontend-web` com build `standalone` no mesmo Swarm, atrás do Traefik. Ver [`ARQUITETURA-DEPLOY.md`](./ARQUITETURA-DEPLOY.md).

**Regra:** o Next.js não escreve no banco direto. Toda ação passa pelo gateway, que encaminha ao serviço dono. Esse serviço aplica as regras de negócio e grava no `audit_log`.

## Riscos, compliance e guardrails

O maior risco não é técnico: é cobrar errado ou de forma abusiva. Por isso as regras ficam no código e na política, não no prompt.

| Risco | Mitigação |
| --- | --- |
| Cobrança vexatória ou constrangedora (CDC, art. 42) | Templates revisados; agente sem permissão para ameaças ou menção a terceiros; horário permitido por tenant |
| Falar com a pessoa errada | Confirmar identidade (ex.: 3 dígitos do CPF) antes de mostrar valores; nunca cobrar em grupo |
| Dados pessoais e financeiros (LGPD) | Base legal registrada por tenant, contrato de operador com o cliente, retenção definida, `audit_log`, acesso por RLS |
| Banimento do número | Templates oficiais para disparo proativo, rate limit por número, opt-out respeitado na hora |
| Comprovante falso | Baixa definitiva só com confirmação do extrato ou webhook |
| Baixa duplicada | Unicidade de `e2e_id` e `file_hash` no banco + locks no Redis |
| Agente inventa condição | Ferramentas só retornam o que a política permite; o LLM escolhe entre opções, não cria valores |
| Alucinação na leitura do comprovante | Validar campos (valor, data, formato do E2E); baixa de baixa confiança vira exceção |

Ponto em aberto: revisar com um advogado os textos da régua e o contrato de prestação antes do primeiro cliente.

## Multi-tenant, métricas e precificação

Onboarding de cliente novo deve ser configuração, não projeto: cadastrar tenant, política, régua, número e integração do emissor.

**Métricas que o painel mostra ao cliente**

- Taxa de recuperação: valor recebido após o vencimento ÷ valor vencido.
- Dias médios de atraso (DSO) do período, comparados com a linha de base gravada no onboarding.
- Promessas cumpridas ÷ promessas feitas.
- Baixa automática: % de pagamentos conciliados sem humano.
- Exceções abertas e tempo médio de resolução.

**Estrutura de preço proposta**

- Setup único: integração com o emissor, importação da base e configuração da régua.
- Mensalidade por faixa de títulos ativos (cobre infra, WhatsApp e LLM).
- Variável sobre o valor recuperado de títulos vencidos, para alinhar o incentivo com o resultado.

Em aberto: valores de cada faixa ainda a definir com base no custo real por título medido no piloto.

## Roadmap do MVP

&#91;embedded content: roadmap · 4 fases de 3 semanas, 4 gates\]

A conciliação vem primeiro porque não fala com o devedor, reaproveita o processamento de comprovantes PIX que já existe e gera prova de valor para vender a régua. Cada fase só começa quando o gate anterior passa num cliente piloto.
