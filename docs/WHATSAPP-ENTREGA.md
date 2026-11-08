# Entrega de mensagens e arquivos no WhatsApp

Como não perder o que entra e o que sai pelo WhatsApp. O painel mostra o estado; quem garante a mensagem é o banco, o recibo de entrega e a cópia do arquivo no storage.

Complementa [`PRODUTO.md`](./PRODUTO.md) (régua e conversa) e [`TECNICA.md`](./TECNICA.md) (canal Evolution). O passo a passo dos fluxos está em [`FLUXOS.md`](../FLUXOS.md).

---

## 1. O que conta como entregue

A Evolution responder HTTP 200 significa que **aceitou** o envio. Entrega é o recibo posterior do WhatsApp (`messages.update`).

| Status | Significado | O que o operador faz |
| --- | --- | --- |
| `pendente` | Gravada aqui e ainda não saiu | Esperar o worker |
| `aceito` | A Evolution aceitou; o `wa_message_id` existe | Esperar o recibo |
| `entregue` | Chegou no aparelho | Nada |
| `lido` | A pessoa abriu | Nada. Muita gente desliga a confirmação de leitura |
| `falhou` | Número inválido, template recusado, sessão caída, erro explícito | Corrigir o contato ou reenviar |
| `sem_recibo` | `aceito` há mais tempo que a janela e sem `entregue` | Entra na fila. Ainda não é falha |

Número sem internet fica em `aceito` por horas e depois vira `entregue`. `lido` é opcional e nunca bloqueia a régua.

O arquivo tem status próprio. O texto pode chegar e o anexo falhar, e o inverso também.

| Status do arquivo | Significado |
| --- | --- |
| `armazenado` | A cópia está no storage (MinIO) e ainda não há recibo |
| `entregue` | O documento chegou no aparelho |
| `falhou` | O envio do anexo terminou em erro |
| `ausente` | A mensagem de mídia foi vista e a cópia não foi gravada aqui |

---

## 2. Estado atual do código

O canal é a Evolution (`api/app/channels/whatsapp.py`). O que já existe e o que ainda falta:

| Peça | Hoje | Efeito |
| --- | --- | --- |
| Régua | A etapa nasce `pendente` e vira `aceito` no HTTP 200 | A etapa só vira `entregue` ou `lido` com o recibo. `falhou` libera reenvio. Timeout deixa `pendente` |
| Unicidade | Índice único parcial em `(invoice_id, step, channel)` onde o status não é `falhou` | Tentativa que falhou não segura a etapa. Aceite, entrega e leitura seguram |
| Mensagem | `messages.delivery_status` e `messages.wa_message_id` | O recibo atualiza a linha pelo id. Status terminal não regride |
| Webhook | `POST /webhooks/evolution` trata `messages.upsert` e `messages.update` | O recibo espelha em `messages` e em `dunning_events` |
| Entrada perdida | `pull_unseen_replies` e `reconcile_outbound` | Com `EVOLUTION_API_KEY`, o processo `cobranca` roda os dois a cada 8 segundos, em dev e em produção. A saída em `aceito` é corrigida pelo que a Evolution ainda tem; depois da janela vira `sem_recibo` |
| Saída | `send_to_debtor` e a régua gravam `pendente` antes do HTTP | Timeout de transporte deixa a linha `pendente`. O aceite grava `aceito` e o `wa_message_id` |
| Painel | `GET /conversations/deliveries` lê `messages` | Mostra enviada, entregue, falha e arquivo recebido ou não. `?falhou=true` filtra a falha. Não chama a Evolution |
| Mídia de entrada | Cópia no MinIO na chegada, antes do OCR | O webhook grava o arquivo ao receber. O processamento lê essa cópia. Sem a cópia, baixa e grava antes de chamar o extrator |
| Sessão | `connection.update` abre exceção `sessao_canal` | Não cria mensagem na conversa do devedor. Alerta repetido da mesma instância não duplica |

---

## 3. Estratégia

Cinco peças, nesta ordem. O dashboard é a última: ele lê o banco.

### 3.1 Caixa de saída

Gravar a mensagem, e o arquivo quando houver, **antes** de chamar a Evolution, com status `pendente`. O worker envia, guarda o `wa_message_id` e passa para `aceito`. Se o processo morrer no meio, o registro continua e o envio retoma.

A etapa da régua só conta como disparada em `aceito`. Falha de transporte grava `falhou` e a etapa pode ser reenviada. O reenvio cria uma mensagem nova, com outro `wa_message_id`. A unicidade da etapa passa a valer para o disparo aceito, não para a tentativa que caiu.

### 3.2 Webhook de status

O webhook passa a tratar `messages.update` além de `messages.upsert`. A atualização é pelo `wa_message_id`, idempotente: evento repetido não duplica linha e não volta um status terminal (`entregue`, `lido`, `falhou`) para um anterior.

O mesmo valor espelha em `messages` e, quando a mensagem for da régua, em `dunning_events.delivery_status`.

### 3.3 Reconciliação

Job periódico, no mesmo desenho de `pull_unseen_replies`, também em produção:

- entrada: mensagens e mídias que o webhook não gravou
- saída: registros em `aceito` ou `sem_recibo`, consultados na Evolution e corrigidos no banco

A Evolution desta instalação fica em outro servidor. Webhook com `localhost` não alcança o Minikube. O pull cobre esse buraco. O painel não consulta a Evolution a cada refresh.

A janela de `sem_recibo` fica na política do tenant (ponto de partida: 6 horas em `aceito` sem `entregue`).

### 3.4 Arquivo no storage

O WhatsApp transporta. O arquivo mora no MinIO.

- **Entrada** (comprovante, imagem, PDF): baixar o base64 no momento em que a mensagem chega e gravar com hash antes do OCR.
- **Saída** (2ª via, boleto, qualquer anexo): o blob nasce no storage; o envio manda uma cópia. `ausente` ou `falhou` reenvia a partir dessa cópia.

O hash segue a mesma ideia de deduplicação de `payments.file_hash`: o mesmo arquivo não baixa o título duas vezes e não se perde se o celular apagar a conversa.

### 3.5 Painel

Fila operacional, na fase de Conversas do MVP ([`PRODUTO.md`](./PRODUTO.md) §3). Três recortes:

- saída: `pendente`, `aceito`, `entregue`, `lido`, `falhou`, `sem_recibo`
- entrada: gravada aqui, ou vista na Evolution e ainda sem linha
- arquivos: cópia nossa sem recibo, ou mídia recebida sem cópia no storage

Ações do operador:

- reenviar a partir do registro local (novo id)
- abrir a conversa e o título ligados à mensagem
- baixar o arquivo do storage

A fila está em `/entregas`. Ela lê `GET /conversations/deliveries`. Reenvio a partir do registro local continua fora desta tela.

A régua não reenvia etapa que já está `entregue` ou `lido`. Reenvio automático só existe para `falhou` com motivo transitório (sessão caída, timeout). Número inválido e template recusado ficam na fila humana.

Alerta de sessão (`connection.update`) é separado da fila de mensagens. Sessão caída perde o canal inteiro; olhar mensagem por mensagem chega tarde.

---

## 4. Ordem de implementação

1. Status de entrega em `messages` e espelho em `dunning_events`.
2. `messages.update` no webhook, idempotente por `wa_message_id`.
3. Job de reconciliação de entrada e de recibo de saída, em dev e em produção.
4. Cópia da mídia no storage na chegada e na saída.
5. Fila no painel com enviada, entregue, falha, arquivo recebido ou não, e o filtro do que falhou. Feito em `/entregas`.

Sem os quatro primeiros, a tela só mostraria `enviado`.

---

## 5. Fora deste desenho

- Tratar `lido` como condição de sucesso da régua.
- Consultar a Evolution a cada abertura do painel.
- Reusar o mesmo `wa_message_id` num reenvio.
- Confiar no chat do celular como arquivo do comprovante.
