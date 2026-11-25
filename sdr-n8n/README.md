# SDR da Kitou no n8n

Agente de pré-vendas no WhatsApp. Ele conversa com quem chegou pelo site ou chamou no número comercial, entende a operação de cobrança, qualifica, marca a conversa com o especialista no Google Agenda, faz follow-up de quem sumiu e lembra da reunião.

O roteiro de qualificação, o cliente ideal e as objeções saem de [JORNADA-VENDA-B2B.md](../docs/JORNADA-VENDA-B2B.md) (etapas 1 e 2) e de [CONSELHO.md](../docs/CONSELHO.md) §2. Quando a jornada mudar, mude [`prompts/sdr-system.md`](./prompts/sdr-system.md) junto.

## Por que fica fora do produto

O produto tirou o n8n do runtime: régua, conciliação e agente de cobrança são módulos Python ([TECNICA.md](../docs/TECNICA.md)). O SDR é ferramenta do comercial da própria Kitou e não toca em dado de cliente:

| | Produto | SDR |
| --- | --- | --- |
| Fala com | Devedor do cliente | Lead da Kitou |
| WhatsApp | Instância da conta, template Meta | Instância própria, `kitou-sdr` |
| Banco | Postgres do produto, RLS por tenant | Database `kitou_sdr`, sem tenant |
| Runtime | Swarm, `cobranca-api` | n8n |

Nunca aponte o SDR para a instância Evolution de cobrança nem para o banco do produto.

## Como funciona

```text
Formulário do site ──► 05 Novo lead ──► abertura no WhatsApp ─┐
                                                               ▼
WhatsApp do lead ──► Evolution ──► 01 Conversa ──► agente (Claude) ──► resposta em 1 a 3 balões
                                        │              │
                                        │              └── ferramentas (04): horários, agendar, cancelar,
                                        │                  confirmar, atualizar lead, humano, opt-out
                                        └── humano digitou no celular? pausa o bot para esse lead

02 Follow-up  (a cada 30 min, seg–sex 9h–18h): D+1, D+3, D+7, D+14 e encerra
03 Lembretes  (a cada 5 min): 24h antes pedindo confirmação, 2h antes com link, 15 min antes
```

| Workflow | Gatilho | O que faz |
| --- | --- | --- |
| `01-sdr-conversa` | Webhook da Evolution | Normaliza a mensagem, junta rajadas (espera 12 s), monta o contexto do lead, chama o agente, quebra a resposta em balões e envia com "digitando..." proporcional ao tamanho |
| `02-sdr-followup` | Agenda, 30 min | Pega quem não respondeu, escreve um follow-up com base no histórico e no passo da cadência, envia e agenda o próximo |
| `03-sdr-lembretes` | Agenda, 5 min | Manda os lembretes da reunião e fecha as reuniões que já passaram |
| `04-sdr-ferramentas` | Chamado pelo agente | As sete ferramentas do agente, num switch por `acao` |
| `05-sdr-novo-lead` | Webhook do formulário | Confere se o número tem WhatsApp, cria o lead e manda a abertura |

### O que deixa a conversa humana

- Junta mensagens picadas: quem manda "oi", "tudo bem?" e "queria saber do sistema" em sequência recebe uma resposta só.
- Responde em até três balões curtos, com "digitando..." antes de cada um (`delay` da Evolution).
- Uma pergunta por vez, reagindo ao que a pessoa disse. Não pergunta de novo o que já sabe: o contexto do lead vai em toda chamada.
- Oferece dois horários, em dias diferentes, em vez de uma lista.
- Lembretes com texto fixo e variações. Lembrete não passa pelo LLM e não inventa nada.
- O agente se apresenta como assistente virtual e diz a verdade se perguntarem. Humanizado não quer dizer se passar por gente.

### Quando o bot sai da conversa

| Situação | O que acontece |
| --- | --- |
| Alguém do time responde pelo celular, no mesmo número | O fluxo vê `fromMe` sem o id que o bot gravou no Redis e pausa o bot por 12 h para esse lead |
| Lead pede uma pessoa, preço insistente, jurídico, técnico, irritado, BPO ou banco querendo avançar | `transferir_humano`: etapa `humano`, bot pausado 24 h, aviso no WhatsApp do especialista com o resumo |
| Lead pede para parar | `registrar_opt_out`: sem follow-up. Se ele mesmo voltar a escrever, o bot responde |

### Etapas do lead

`novo` → `conversando` → `qualificado` → `agendado` → `realizado`, e as saídas `perdido`, `opt_out`, `humano`. O fit (`alto`, `medio`, `baixo`, `fora`) segue os critérios do prompt, tirados da etapa 1 da jornada.

## Instalação

### 1. Banco

```bash
createdb kitou_sdr
psql kitou_sdr -f sql/schema.sql
```

### 2. Evolution

Crie uma instância só do SDR (`kitou-sdr`), pareie o número comercial e aponte o webhook para o n8n:

```bash
curl -X POST "$EVOLUTION_URL/webhook/set/kitou-sdr" \
  -H "apikey: $EVOLUTION_API_KEY" -H 'content-type: application/json' \
  -d '{"webhook":{"enabled":true,"url":"https://SEU-N8N/webhook/settlr-sdr/evolution","events":["MESSAGES_UPSERT"],"byEvents":false,"base64":false}}'
```

### 3. Configuração

```bash
cp config.exemplo.json config.json   # fora do Git: tem telefone e e-mail
# edite nomes, e-mail e WhatsApp do especialista, URL da Evolution, agenda, horários
python3 gerar_workflows.py
```

`gerar_workflows.py` é a fonte de verdade: ele lê `config.json` e os dois prompts e escreve `workflows/*.json`. Edite o script ou o prompt e gere de novo. Não edite o JSON à mão.

### 4. Credenciais no n8n

| Nome | Tipo | Conteúdo |
| --- | --- | --- |
| Kitou SDR Postgres | Postgres | Database `kitou_sdr` |
| Kitou SDR Redis | Redis | Qualquer Redis. Chaves `sdr:*` com TTL |
| Anthropic | Anthropic | Chave da API |
| Evolution SDR (apikey) | Header Auth | Nome `apikey`, valor: a chave da Evolution |
| Google Calendar SDR | Google Calendar OAuth2 | Conta dona da agenda do especialista |
| SDR Formulário (segredo) | Header Auth | Nome `x-sdr-token`, valor: um segredo que o site envia |

### 5. Importar

```bash
N8N_URL=https://SEU-N8N N8N_API_KEY=... ./scripts/importar.sh
```

O script cria o 04 primeiro e grava o id dele nas sete ferramentas do 01. Se você importar pela tela, importe o 04, copie o id da URL e troque `REPLACE_TOOLS_WORKFLOW_ID` nas ferramentas do 01. Abra cada workflow, confira as credenciais e ative 01, 02, 03 e 05. O 04 não precisa ser ativado.

### 6. Formulário do site

```bash
curl -X POST https://SEU-N8N/webhook/kitou-sdr/lead \
  -H 'x-sdr-token: SEU_SEGREDO' -H 'content-type: application/json' \
  -d '{"nome":"Marina Souza","telefone":"11 98888-7777","empresa":"Clínica Bem Viver","email":"marina@bemviver.com.br","segmento":"clinica","origem":"site","mensagem":"Quero parar de bater planilha de PIX"}'
```

## Teste sem celular

Simula uma mensagem do lead chegando pela Evolution:

```bash
curl -X POST https://SEU-N8N/webhook/settlr-sdr/evolution -H 'content-type: application/json' -d '{
  "event": "messages.upsert", "instance": "kitou-sdr",
  "data": { "key": { "remoteJid": "5511988887777@s.whatsapp.net", "fromMe": false, "id": "TESTE1" },
            "pushName": "Marina", "messageType": "conversation",
            "message": { "conversation": "Oi, vi o anúncio de vocês. Como funciona?" } } }'
```

Roteiro mínimo antes de ligar no número real:

1. Rajada de três mensagens em 5 s gera uma resposta só.
2. "Quanto custa?" não recebe número, e na segunda insistência vai para o especialista.
3. "Vocês protestam o cliente?" recebe a explicação do que a Kitou não faz.
4. "Pode ser terça às 10h": cria o evento com Meet, a reunião aparece em `sdr_meetings` e o lead vira `agendado`.
5. "Preciso remarcar": cancela no Google e oferece novos horários.
6. "Para de me mandar mensagem": opt-out, nenhum follow-up depois.
7. Responder pelo celular do número comercial pausa o bot para esse lead.
8. "Você é um robô?": resposta honesta.

## Operação

O especialista assume pelo mesmo número. Para devolver ao bot antes de a pausa acabar:

```sql
update sdr_leads set bot_paused_until = null, stage = 'qualificado' where phone = '5511988887777';
```

Marcar falta ou reunião feita:

```sql
update sdr_meetings set status = 'no_show' where id = 42;   -- ou 'realizada'
```

Funil da semana:

```sql
select stage, fit, count(*) from sdr_leads
 where created_at > now() - interval '7 days' group by 1, 2 order by 1, 2;

select count(*) filter (where status in ('realizada','agendada','confirmada')) as marcadas,
       count(*) filter (where status = 'no_show') as faltas,
       count(*) filter (where status = 'cancelada') as canceladas
  from sdr_meetings where created_at > now() - interval '30 days';
```

## Modelo

O agente usa `claude-opus-5-5` no nó Anthropic Chat Model. O modelo está em `config.json` (`anthropic_model`). O prompt de sistema é fixo, e o que muda por lead vai na mensagem, dentro de `<contexto>`. Assim o começo da requisição se repete entre chamadas.

## Limites conhecidos

- **Janela de 24 h da Cloud API.** Com instância Baileys, a abertura do formulário e o follow-up saem como texto livre. Com `WHATSAPP-BUSINESS` (Cloud API), a abertura e todo follow-up depois de 24 h sem resposta precisam de template aprovado na Meta. Esse caminho não está implementado: troque o `sendText` desses dois fluxos por envio de template antes de migrar.
- **Áudio.** O agente pede para a pessoa escrever. Para transcrever, ligue um nó de transcrição entre "Normalizar evento" e "Bufferizar mensagem".
- **Debounce.** Uma mensagem que chega entre a leitura e a limpeza do buffer, numa janela de milissegundos, se perde. Para o volume de um SDR, o risco é aceitável.
- **Parâmetros do Postgres.** Os nós passam os parâmetros como array (`{{ [ a, b ] }}`). Se a sua versão do n8n reclamar, troque por lista separada por vírgula.
- **Temperatura.** O `claude-opus-5-5` recusa `temperature`, `top_p` e `top_k`. Não preencha esses campos no nó Anthropic. Se o nó mandar um valor padrão e a API devolver 400, atualize o n8n.
- **Fuso.** O SQL usa `America/Sao_Paulo` fixo. Para outro fuso, troque no script também.
