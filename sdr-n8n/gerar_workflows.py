#!/usr/bin/env python3
"""Gera os workflows n8n do SDR da Kitou em workflows/*.json.

Fonte de verdade: este arquivo, prompts/*.md e config.json (ou config.exemplo.json).
Edite aqui e rode `python3 gerar_workflows.py`; não edite o JSON gerado à mão.
"""
import json
import pathlib
import uuid

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "workflows"
CFG_FILE = ROOT / "config.json" if (ROOT / "config.json").exists() else ROOT / "config.exemplo.json"
CFG = json.loads(CFG_FILE.read_text(encoding="utf-8"))

TOOLS_WF_ID = "REPLACE_TOOLS_WORKFLOW_ID"

# Credenciais: o n8n pede para escolher na primeira abertura se o id não existir.
# scripts/importar.sh troca os ids se as variáveis SDR_CRED_* estiverem definidas.
PG = {"postgres": {"id": "SDR_CRED_PG", "name": "Kitou SDR Postgres"}}
REDIS = {"redis": {"id": "SDR_CRED_REDIS", "name": "Kitou SDR Redis"}}
ANTH = {"anthropicApi": {"id": "SDR_CRED_ANTHROPIC", "name": "Anthropic"}}
EVO = {"httpHeaderAuth": {"id": "SDR_CRED_EVOLUTION", "name": "Evolution SDR (apikey)"}}
GCAL = {"googleCalendarOAuth2Api": {"id": "SDR_CRED_GCAL", "name": "Google Calendar SDR"}}
FORM = {"httpHeaderAuth": {"id": "SDR_CRED_FORM", "name": "SDR Formulário (segredo)"}}


def render(text: str, extra: dict | None = None) -> str:
    values = {**CFG, **(extra or {})}
    for k, v in values.items():
        text = text.replace("{{" + k + "}}", str(v))
    return text


SYSTEM_PROMPT = render((ROOT / "prompts" / "sdr-system.md").read_text(encoding="utf-8"))
FOLLOWUP_PROMPT = render((ROOT / "prompts" / "followup.md").read_text(encoding="utf-8"))


def nid(*parts: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "kitou-sdr/" + "/".join(parts)))


class WF:
    def __init__(self, name: str, slug: str):
        self.name, self.slug = name, slug
        self.nodes: list[dict] = []
        self.conns: dict = {}

    def add(self, name, type_, version, params, pos, creds=None, **extra):
        node = {
            "id": nid(self.slug, name),
            "name": name,
            "type": type_,
            "typeVersion": version,
            "position": pos,
            "parameters": params,
        }
        if creds:
            node["credentials"] = creds
        node.update(extra)
        self.nodes.append(node)
        return name

    def link(self, a, b, out=0, kind="main"):
        lst = self.conns.setdefault(a, {}).setdefault(kind, [])
        while len(lst) <= out:
            lst.append([])
        lst[out].append({"node": b, "type": kind, "index": 0})

    def chain(self, *names):
        for a, b in zip(names, names[1:]):
            self.link(a, b)

    def dump(self):
        names = {n["name"] for n in self.nodes}
        assert len(names) == len(self.nodes), f"nome de nó duplicado em {self.slug}"
        for a, kinds in self.conns.items():
            assert a in names, f"{self.slug}: origem desconhecida {a}"
            for outs in kinds.values():
                for out in outs:
                    for c in out:
                        assert c["node"] in names, f"{self.slug}: destino desconhecido {c['node']}"
        data = {
            "name": self.name,
            "nodes": self.nodes,
            "connections": self.conns,
            "settings": {"executionOrder": "v1", "timezone": CFG["timezone"]},
        }
        OUT.mkdir(exist_ok=True)
        path = OUT / f"{self.slug}.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"ok  {path.relative_to(ROOT)}  ({len(self.nodes)} nós)")


# ---------------------------------------------------------------- blocos comuns

def config_node(wf, pos):
    keys = [
        "sdr_nome", "closer_nome", "closer_email", "closer_whatsapp", "evolution_url",
        "evolution_instance", "calendar_id", "timezone", "duracao_reuniao_min", "horario_inicio",
        "horario_fim", "almoco_inicio", "almoco_fim", "antecedencia_min_horas", "dias_busca",
        "debounce_segundos", "pausa_humano_horas", "max_followups", "followup_hora_inicio",
        "followup_hora_fim",
    ]
    assignments = []
    for k in keys:
        v = CFG[k]
        assignments.append({
            "id": nid(wf.slug, "cfg", k),
            "name": k,
            "value": v,
            "type": "number" if isinstance(v, (int, float)) else "string",
        })
    return wf.add("Config", "n8n-nodes-base.set", 3.4,
                  {"assignments": {"assignments": assignments}, "includeOtherFields": True, "options": {}}, pos)


def code(wf, name, js, pos, **extra):
    return wf.add(name, "n8n-nodes-base.code", 2, {"jsCode": js.strip() + "\n"}, pos, **extra)


def pg(wf, name, query, params_expr, pos, **extra):
    params = {"operation": "executeQuery", "query": query.strip(), "options": {}}
    if params_expr:
        params["options"]["queryReplacement"] = params_expr
    return wf.add(name, "n8n-nodes-base.postgres", 2.5, params, pos, creds=PG, **extra)


def if_node(wf, name, left, op_type, operation, pos, right=None):
    cond = {"id": nid(wf.slug, name, "c"), "leftValue": left, "operator": {"type": op_type, "operation": operation}}
    if right is None:
        cond["operator"]["singleValue"] = True
        cond["rightValue"] = ""
    else:
        cond["rightValue"] = right
    return wf.add(name, "n8n-nodes-base.if", 2.2, {
        "conditions": {
            "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
            "conditions": [cond],
            "combinator": "and",
        },
        "options": {},
    }, pos)


def set_resposta(wf, name, expr, pos):
    return wf.add(name, "n8n-nodes-base.set", 3.4, {
        "assignments": {"assignments": [
            {"id": nid(wf.slug, name, "r"), "name": "resposta", "value": expr, "type": "string"},
        ]},
        "options": {},
    }, pos)


def evolution_send(wf, name, number_expr, text_expr, delay_expr, pos, **extra):
    """sendText da Evolution v2. `delay` mostra "digitando..." antes de enviar.
    batchSize 1 garante a ordem dos balões."""
    body = f"={{{{ JSON.stringify({{ number: {number_expr}, text: {text_expr}, delay: {delay_expr} }}) }}}}"
    return wf.add(name, "n8n-nodes-base.httpRequest", 4.2, {
        "method": "POST",
        "url": "={{ $('Config').first().json.evolution_url }}/message/sendText/{{ $('Config').first().json.evolution_instance }}",
        "authentication": "genericCredentialType",
        "genericAuthType": "httpHeaderAuth",
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": body,
        "options": {"batching": {"batch": {"batchSize": 1, "batchInterval": 500}}, "timeout": 30000},
    }, pos, creds=EVO, **extra)


def mark_sent(wf, name, pos):
    """Guarda o id da mensagem que o bot mandou. Mensagem fromMe sem esse id = humano digitou."""
    return wf.add(name, "n8n-nodes-base.redis", 1, {
        "operation": "set",
        "key": "=sdr:sent:{{ $json.key.id }}",
        "value": "1",
        "keyType": "string",
        "expire": True,
        "ttl": 86400,
    }, pos, creds=REDIS, onError="continueRegularOutput")


def gcal_http(wf, name, method, url, body_expr, pos, **extra):
    params = {
        "method": method,
        "url": url,
        "authentication": "predefinedCredentialType",
        "nodeCredentialType": "googleCalendarOAuth2Api",
        "options": {},
    }
    if body_expr:
        params.update({"sendBody": True, "specifyBody": "json", "jsonBody": body_expr})
    return wf.add(name, "n8n-nodes-base.httpRequest", 4.2, params, pos, creds=GCAL, **extra)


MEMORY_INSERT = """
insert into sdr_chat_memory (session_id, message)
values ($1, jsonb_build_object('type', 'ai', 'content', $2::text,
        'additional_kwargs', '{}'::jsonb, 'response_metadata', '{}'::jsonb, 'tool_calls', '[]'::jsonb,
        'invalid_tool_calls', '[]'::jsonb))
"""


# ======================================================= 01 — conversa (inbound)

def wf_inbound():
    wf = WF("Kitou SDR · 01 Conversa (WhatsApp)", "01-sdr-conversa")
    wf.add("Webhook Evolution", "n8n-nodes-base.webhook", 2, {
        "httpMethod": "POST",
        "path": "kitou-sdr/evolution",
        "responseMode": "onReceived",
        "options": {},
    }, [0, 300], webhookId=nid("webhook", "evolution"))
    config_node(wf, [220, 300])
    code(wf, "Normalizar evento", r"""
// Evolution v2, evento messages.upsert. Grupo, status e canal ficam de fora.
const cfg = $('Config').first().json;
const out = [];
for (const item of $input.all()) {
  const b = item.json.body ?? item.json;
  const ev = String(b.event || '').toLowerCase().replace(/_/g, '.');
  if (ev !== 'messages.upsert') continue;
  if (b.instance && b.instance !== cfg.evolution_instance) continue;
  const d = Array.isArray(b.data) ? b.data[0] : b.data;
  if (!d || !d.key) continue;
  const jid = d.key.remoteJid || '';
  if (!jid.endsWith('@s.whatsapp.net')) continue;
  const m = d.message || {};
  let text = m.conversation || m.extendedTextMessage?.text
    || m.buttonsResponseMessage?.selectedDisplayText || m.listResponseMessage?.title || '';
  if (!text) {
    if (m.audioMessage) text = '[o lead mandou um áudio]';
    else if (m.imageMessage) text = '[o lead mandou uma imagem' + (m.imageMessage.caption ? ': ' + m.imageMessage.caption : '') + ']';
    else if (m.documentMessage) text = '[o lead mandou um documento: ' + (m.documentMessage.fileName || 'sem nome') + ']';
    else if (m.stickerMessage || m.reactionMessage || m.protocolMessage) continue;
    else text = '[mensagem sem texto]';
  }
  out.push({ json: {
    phone: jid.split('@')[0],
    fromMe: !!d.key.fromMe,
    msgId: d.key.id,
    pushName: d.pushName || '',
    text: String(text).trim().slice(0, 4000),
  } });
}
return out;
""", [440, 300])
    if_node(wf, "Enviada pelo nosso número?", "={{ $json.fromMe }}", "boolean", "true", [660, 300])

    # --- fromMe: foi o bot ou um humano no celular?
    wf.add("Foi o bot?", "n8n-nodes-base.redis", 1, {
        "operation": "get",
        "propertyName": "bot",
        "key": "=sdr:sent:{{ $json.msgId }}",
        "keyType": "string",
        "options": {},
    }, [880, 120], creds=REDIS)
    if_node(wf, "Humano digitou?", "={{ $json.bot }}", "string", "empty", [1100, 120])
    pg(wf, "Pausar bot", """
update sdr_leads
   set bot_paused_until = now() + make_interval(hours => $2::int),
       next_followup_at = null,
       updated_at = now()
 where phone = $1
""", "={{ [ $('Normalizar evento').item.json.phone, $('Config').first().json.pausa_humano_horas ] }}", [1320, 120])

    # --- mensagem do lead
    pg(wf, "Upsert lead", """
insert into sdr_leads (phone, name, last_inbound_at, stage, source)
values ($1, nullif($2, ''), now(), 'conversando', 'whatsapp')
on conflict (phone) do update set
  name             = coalesce(sdr_leads.name, excluded.name),
  last_inbound_at  = now(),
  followup_count   = 0,
  next_followup_at = null,
  stage            = case when sdr_leads.stage in ('novo','perdido','opt_out') then 'conversando' else sdr_leads.stage end,
  updated_at       = now()
returning id, phone, coalesce(bot_paused_until > now(), false) as pausado
""", "={{ [ $json.phone, $json.pushName ] }}", [880, 420])
    if_node(wf, "Bot ativo?", "={{ $json.pausado }}", "boolean", "false", [1100, 420])

    # --- debounce: junta rajadas de mensagens antes de responder
    wf.add("Bufferizar mensagem", "n8n-nodes-base.redis", 1, {
        "operation": "push",
        "list": "=sdr:buf:{{ $('Normalizar evento').item.json.phone }}",
        "messageData": "={{ $('Normalizar evento').item.json.text }}",
        "tail": True,
    }, [1320, 420], creds=REDIS)
    wf.add("Marcar última", "n8n-nodes-base.redis", 1, {
        "operation": "set",
        "key": "=sdr:last:{{ $('Normalizar evento').item.json.phone }}",
        "value": "={{ $('Normalizar evento').item.json.msgId }}",
        "keyType": "string",
        "expire": True,
        "ttl": 600,
    }, [1540, 420], creds=REDIS)
    wf.add("Esperar o lead terminar", "n8n-nodes-base.wait", 1.1, {
        "amount": CFG["debounce_segundos"],
        "unit": "seconds",
    }, [1760, 420], webhookId=nid("wait", "debounce"))
    wf.add("Ler última", "n8n-nodes-base.redis", 1, {
        "operation": "get",
        "propertyName": "ultima",
        "key": "=sdr:last:{{ $('Normalizar evento').item.json.phone }}",
        "keyType": "string",
        "options": {},
    }, [1980, 420], creds=REDIS)
    if_node(wf, "Sou a última mensagem?", "={{ $json.ultima }}", "string", "equals", [2200, 420],
            right="={{ $('Normalizar evento').item.json.msgId }}")
    wf.add("Ler buffer", "n8n-nodes-base.redis", 1, {
        "operation": "get",
        "propertyName": "buffer",
        "key": "=sdr:buf:{{ $('Normalizar evento').item.json.phone }}",
        "keyType": "list",
        "options": {},
    }, [2420, 420], creds=REDIS)
    code(wf, "Juntar mensagens", r"""
const ev = $('Normalizar evento').first().json;
const buf = Array.isArray($json.buffer) ? $json.buffer : [];
const texto = (buf.length ? buf : [ev.text]).join('\n');
return [{ json: { phone: ev.phone, pushName: ev.pushName, texto } }];
""", [2640, 420])
    wf.add("Limpar buffer", "n8n-nodes-base.redis", 1, {
        "operation": "delete",
        "key": "=sdr:buf:{{ $json.phone }}",
    }, [2860, 420], creds=REDIS)
    pg(wf, "Contexto do lead", """
select l.*,
       m.id      as reuniao_id,
       m.status  as reuniao_status,
       m.meet_link as reuniao_link,
       to_char(m.start_at at time zone 'America/Sao_Paulo', 'DD/MM/YYYY "às" HH24:MI') as reuniao_quando
  from sdr_leads l
  left join lateral (
        select * from sdr_meetings
         where lead_id = l.id and status in ('agendada','confirmada') and start_at > now() - interval '1 hour'
         order by start_at limit 1) m on true
 where l.phone = $1
""", "={{ [ $('Juntar mensagens').item.json.phone ] }}", [3080, 420])
    code(wf, "Montar contexto", r"""
const l = $json;
const msg = $('Juntar mensagens').first().json;
const agora = DateTime.now().setZone('America/Sao_Paulo').setLocale('pt-BR');
const v = (x) => (x === null || x === undefined || x === '') ? '?' : x;
const linhas = [
  `Agora: ${agora.toFormat("cccc, dd/LL/yyyy HH:mm")} (horário de Brasília)`,
  `Nome no WhatsApp: ${v(msg.pushName)} | nome confirmado: ${v(l.name)}`,
  `Empresa: ${v(l.company)} | cargo: ${v(l.role)} | e-mail: ${v(l.email)}`,
  `Etapa: ${l.stage} | fit: ${l.fit}`,
  `Segmento: ${v(l.segment)} | quem paga: ${v(l.payer_type)} | cobranças/mês: ${v(l.monthly_charges)}`,
  `Meios: ${v(l.channels)} | emissor: ${v(l.issuer)} | Pix Automático: ${v(l.has_pix_automatico)} | idade do CNPJ (meses): ${v(l.cnpj_age_months)}`,
  `Dor: ${v(l.pain)} | decisor: ${v(l.decision_maker)}`,
  `Resumo até aqui: ${v(l.summary)}`,
  l.reuniao_id
    ? `Reunião: ${l.reuniao_status} para ${l.reuniao_quando} (Brasília). Link: ${v(l.reuniao_link)}`
    : 'Reunião: nenhuma marcada',
];
const prompt = `<contexto>\n${linhas.join('\n')}\n</contexto>\n\n<mensagem_do_lead>\n${msg.texto}\n</mensagem_do_lead>`;
return [{ json: { phone: l.phone, lead_id: l.id, prompt } }];
""", [3300, 420])

    wf.add("SDR Kitou", "@n8n/n8n-nodes-langchain.agent", 1.7, {
        "promptType": "define",
        "text": "={{ $json.prompt }}",
        "options": {"systemMessage": SYSTEM_PROMPT, "maxIterations": 8},
    }, [3520, 420], onError="continueRegularOutput")
    wf.add("Claude", "@n8n/n8n-nodes-langchain.lmChatAnthropic", 1.3, {
        "model": {"__rl": True, "mode": "id", "value": CFG["anthropic_model"]},
        "options": {"maxTokensToSample": 2048},
    }, [3300, 700], creds=ANTH)
    wf.add("Memória (Postgres)", "@n8n/n8n-nodes-langchain.memoryPostgresChat", 1.3, {
        "sessionIdType": "customKey",
        "sessionKey": "={{ $('Montar contexto').first().json.phone }}",
        "tableName": "sdr_chat_memory",
        "contextWindowLength": 30,
    }, [3460, 700], creds=PG)
    wf.link("Claude", "SDR Kitou", kind="ai_languageModel")
    wf.link("Memória (Postgres)", "SDR Kitou", kind="ai_memory")

    phone_expr = "={{ $('Montar contexto').first().json.phone }}"
    tools = [
        ("ver_horarios", "horarios",
         "Lista horários livres na agenda do especialista para a reunião. Chame antes de oferecer horários. "
         "Devolve opções com o campo inicio em ISO 8601, que você usa em agendar_reuniao.", {}),
        ("agendar_reuniao", "agendar",
         "Marca a reunião no horário escolhido pelo lead, cria o link do Google Meet e manda o convite. "
         "Só chame depois que o lead aceitou um horário.",
         {"inicio": "Início em ISO 8601 com fuso, ex.: 2026-11-18T10:00:00-03:00. Use o valor de ver_horarios ou o horário que o lead pediu.",
          "email": "E-mail do lead para o convite. Vazio se ele não passou."}),
        ("cancelar_reuniao", "cancelar",
         "Cancela a reunião marcada do lead. Use quando ele quer remarcar (depois chame ver_horarios) ou desistiu.",
         {"motivo": "Motivo em poucas palavras."}),
        ("confirmar_presenca", "confirmar",
         "Registra que o lead confirmou presença na reunião marcada.", {}),
        ("atualizar_lead", "atualizar_lead",
         "Grava o que você aprendeu sobre o lead. Chame sempre que descobrir um dado novo.",
         {"campos": "JSON com só os campos que mudaram. Chaves aceitas: nome, empresa, cargo, email, "
                    "segmento (clinica|escola|academia|condominio|software|servicos|bpo|banco|outro), "
                    "quem_paga (pf|pj|ambos), cobrancas_mes (número), meios (texto), "
                    "emissor (asaas|inter|efi|iugu|sicoob|planilha|outro), idade_cnpj_meses (número), "
                    "tem_pix_automatico (true|false), dor (texto), decisor (texto), "
                    "fit (alto|medio|baixo|fora), etapa (conversando|qualificado|perdido), "
                    "resumo (2 a 3 frases), retomar_em (AAAA-MM-DD). "
                    "Ex.: {\"segmento\":\"clinica\",\"cobrancas_mes\":800}"}),
        ("transferir_humano", "transferir_humano",
         "Passa a conversa para o especialista e pausa você. Use quando o lead pede uma pessoa, "
         "a pergunta é jurídica, técnica profunda ou de preço insistente, ou o lead está irritado.",
         {"motivo": "Por que transferir, em uma frase."}),
        ("registrar_opt_out", "opt_out",
         "Registra que o lead pediu para não receber mais mensagens. Para os follow-ups.", {}),
    ]
    all_inputs = ["acao", "phone", "inicio", "email", "campos", "motivo"]
    for i, (tname, acao, desc, ai_fields) in enumerate(tools):
        value = {"acao": acao, "phone": phone_expr}
        for f in all_inputs[2:]:
            if f in ai_fields:
                value[f] = f"={{{{ $fromAI('{f}', {json.dumps(ai_fields[f], ensure_ascii=False)}, 'string') }}}}"
            else:
                value[f] = ""
        node = wf.add(f"Ferramenta {tname}", "@n8n/n8n-nodes-langchain.toolWorkflow", 2.1, {
            "name": tname,
            "description": desc,
            "workflowId": {"__rl": True, "mode": "id", "value": TOOLS_WF_ID},
            "workflowInputs": {
                "mappingMode": "defineBelow",
                "value": value,
                "matchingColumns": [],
                "schema": [
                    {"id": f, "displayName": f, "required": False, "defaultMatch": False,
                     "display": True, "canBeUsedToMatch": True, "type": "string", "removed": False}
                    for f in all_inputs
                ],
                "attemptToConvertTypes": False,
                "convertFieldsToString": False,
            },
        }, [3620 + 160 * i, 700])
        wf.link(node, "SDR Kitou", kind="ai_tool")

    code(wf, "Quebrar em balões", r"""
// Cada bloco separado por linha em branco vira um balão. "digitando..." proporcional ao tamanho.
const raw = String($json.output || '').trim();
if (!raw) return [];
let partes = raw.split(/\n\s*\n/).map(s => s.trim()).filter(Boolean);
while (partes.length > 3) { const ult = partes.pop(); partes[partes.length - 1] += '\n' + ult; }
const phone = $('Montar contexto').first().json.phone;
return partes.map((t, i) => {
  const text = t.replace(/\*\*(.+?)\*\*/g, '*$1*').replace(/^#+\s*/gm, '');
  const delay = Math.min(1200 + text.length * 35, 8000) + (i ? 700 : 0);
  return { json: { phone, text, delay } };
});
""", [3740, 420])
    evolution_send(wf, "Enviar WhatsApp", "$json.phone", "$json.text", "$json.delay", [3960, 420])
    mark_sent(wf, "Marcar como do bot", [4180, 420])
    pg(wf, "Registrar envio", """
update sdr_leads
   set last_outbound_at = now(),
       next_followup_at = case
         when opted_out_at is null and stage in ('novo','conversando','qualificado') and next_followup_at is null
           then now() + interval '1 day'
         else next_followup_at end,
       updated_at = now()
 where phone = $1
""", "={{ [ $('Montar contexto').first().json.phone ] }}", [4400, 420], executeOnce=True)

    wf.chain("Webhook Evolution", "Config", "Normalizar evento", "Enviada pelo nosso número?")
    wf.link("Enviada pelo nosso número?", "Foi o bot?", 0)
    wf.link("Enviada pelo nosso número?", "Upsert lead", 1)
    wf.chain("Foi o bot?", "Humano digitou?")
    wf.link("Humano digitou?", "Pausar bot", 0)
    wf.chain("Upsert lead", "Bot ativo?")
    wf.link("Bot ativo?", "Bufferizar mensagem", 0)
    wf.chain("Bufferizar mensagem", "Marcar última", "Esperar o lead terminar", "Ler última", "Sou a última mensagem?")
    wf.link("Sou a última mensagem?", "Ler buffer", 0)
    wf.chain("Ler buffer", "Juntar mensagens", "Limpar buffer", "Contexto do lead", "Montar contexto",
             "SDR Kitou", "Quebrar em balões", "Enviar WhatsApp", "Marcar como do bot", "Registrar envio")
    wf.dump()


# ======================================================= 04 — ferramentas do agente

def wf_tools():
    wf = WF("Kitou SDR · 04 Ferramentas do agente", "04-sdr-ferramentas")
    wf.add("Entrada", "n8n-nodes-base.executeWorkflowTrigger", 1.1, {
        "workflowInputs": {"values": [{"name": f} for f in ["acao", "phone", "inicio", "email", "campos", "motivo"]]},
    }, [0, 600])
    config_node(wf, [220, 600])

    acoes = ["horarios", "agendar", "cancelar", "confirmar", "atualizar_lead", "transferir_humano", "opt_out"]
    wf.add("Ação", "n8n-nodes-base.switch", 3.2, {
        "rules": {"values": [{
            "conditions": {
                "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 2},
                "conditions": [{
                    "id": nid("tools", "sw", a),
                    "leftValue": "={{ $('Entrada').first().json.acao }}",
                    "rightValue": a,
                    "operator": {"type": "string", "operation": "equals"},
                }],
                "combinator": "and",
            },
            "renameOutput": True,
            "outputKey": a,
        } for a in acoes]},
        "options": {"fallbackOutput": "extra"},
    }, [440, 600])
    set_resposta(wf, "Ação desconhecida", "Ação desconhecida. Siga a conversa sem esta ferramenta.", [660, 1500])
    wf.chain("Entrada", "Config", "Ação")
    wf.link("Ação", "Ação desconhecida", len(acoes))

    freebusy_url = "https://www.googleapis.com/calendar/v3/freeBusy"
    cal_events = ("=https://www.googleapis.com/calendar/v3/calendars/"
                  "{{ encodeURIComponent($('Config').first().json.calendar_id) }}/events")

    # --- horarios
    y = 0
    code(wf, "Janela de busca", r"""
const cfg = $('Config').first().json;
const agora = DateTime.now().setZone(cfg.timezone);
return [{ json: {
  timeMin: agora.toISO(),
  timeMax: agora.plus({ days: cfg.dias_busca + 1 }).endOf('day').toISO(),
} }];
""", [660, y])
    gcal_http(wf, "FreeBusy (semana)", "POST", freebusy_url,
              "={{ JSON.stringify({ timeMin: $json.timeMin, timeMax: $json.timeMax, timeZone: $('Config').first().json.timezone, items: [{ id: $('Config').first().json.calendar_id }] }) }}",
              [880, y])
    code(wf, "Calcular horários livres", r"""
const cfg = $('Config').first().json;
const tz = cfg.timezone;
const cal = $json.calendars?.[cfg.calendar_id];
if (!cal || cal.errors) {
  return [{ json: { resposta: 'Não consegui ler a agenda agora. Diga ao lead que você confirma o horário em instantes e chame transferir_humano com o motivo "agenda indisponível".' } }];
}
const busy = (cal.busy || []).map(b => [DateTime.fromISO(b.start).toMillis(), DateTime.fromISO(b.end).toMillis()]);
const dur = cfg.duracao_reuniao_min;
const minStart = DateTime.now().setZone(tz).plus({ hours: cfg.antecedencia_min_horas });
const livres = [];
let dia = DateTime.now().setZone(tz).startOf('day');
for (let d = 0; d <= cfg.dias_busca; d++, dia = dia.plus({ days: 1 })) {
  if (dia.weekday > 5) continue;
  for (let m = cfg.horario_inicio * 60; m + dur <= cfg.horario_fim * 60; m += 30) {
    if (m < cfg.almoco_fim * 60 && m + dur > cfg.almoco_inicio * 60) continue;
    const s = dia.plus({ minutes: m });
    if (s < minStart) continue;
    const sm = s.toMillis(), em = s.plus({ minutes: dur }).toMillis();
    if (busy.some(([bs, be]) => sm < be && em > bs)) continue;
    livres.push(s);
  }
}
// No máximo uma de manhã e uma à tarde por dia, até 6 opções.
const vistos = new Set();
const sugestoes = [];
for (const s of livres) {
  const k = s.toISODate() + (s.hour < 12 ? 'm' : 't');
  if (vistos.has(k)) continue;
  vistos.add(k);
  sugestoes.push(s);
  if (sugestoes.length >= 6) break;
}
if (!sugestoes.length) {
  return [{ json: { resposta: 'Sem horário livre nos próximos dias. Diga que o especialista vai propor um horário e chame transferir_humano com o motivo "agenda cheia".' } }];
}
const hoje = DateTime.now().setZone(tz).startOf('day');
const rotulo = (s) => {
  const diff = Math.round(s.startOf('day').diff(hoje, 'days').days);
  const dia = diff === 0 ? 'hoje' : diff === 1 ? 'amanhã' : s.setLocale('pt-BR').toFormat('cccc (dd/LL)');
  const hora = s.minute ? s.toFormat("HH'h'mm") : s.toFormat("HH'h'");
  return `${dia} às ${hora}`;
};
const linhas = sugestoes.map(s => `${rotulo(s)} | inicio=${s.toISO({ suppressMilliseconds: true })}`);
return [{ json: { resposta: `Horários livres para ${dur} min (Brasília). Ofereça duas opções em dias diferentes:\n${linhas.join('\n')}` } }];
""", [1100, y])
    wf.link("Ação", "Janela de busca", 0)
    wf.chain("Janela de busca", "FreeBusy (semana)", "Calcular horários livres")

    # --- agendar
    y = 300
    code(wf, "Validar horário", r"""
const cfg = $('Config').first().json;
const ent = $('Entrada').first().json;
const tz = cfg.timezone;
const s = DateTime.fromISO(String(ent.inicio || ''), { setZone: true }).setZone(tz);
const fail = (motivo) => [{ json: { ok: false, resposta: motivo } }];
if (!s.isValid) return fail('Horário inválido. Chame ver_horarios e use o campo inicio de lá.');
const e = s.plus({ minutes: cfg.duracao_reuniao_min });
const min = s.hour * 60 + s.minute;
if (s < DateTime.now().setZone(tz).plus({ hours: cfg.antecedencia_min_horas }))
  return fail(`Esse horário está muito em cima. Ofereça horários a partir de ${cfg.antecedencia_min_horas}h daqui (chame ver_horarios).`);
if (s.weekday > 5) return fail('O especialista atende de segunda a sexta. Chame ver_horarios e ofereça outro dia.');
if (min < cfg.horario_inicio * 60 || min + cfg.duracao_reuniao_min > cfg.horario_fim * 60)
  return fail(`O especialista atende das ${cfg.horario_inicio}h às ${cfg.horario_fim}h. Chame ver_horarios.`);
return [{ json: { ok: true, start: s.toISO(), end: e.toISO(), email: String(ent.email || '').trim() } }];
""", [660, y])
    if_node(wf, "Horário válido?", "={{ $json.ok }}", "boolean", "true", [880, y])
    pg(wf, "Dados do lead", """
select l.id, l.name, l.company, l.email, l.phone, l.segment, l.monthly_charges, l.issuer, l.pain, l.summary, l.fit,
       (select to_char(start_at at time zone 'America/Sao_Paulo', 'DD/MM "às" HH24:MI')
          from sdr_meetings where lead_id = l.id and status in ('agendada','confirmada') and start_at > now()
          order by start_at limit 1) as ja_marcada
  from sdr_leads l where l.phone = $1
""", "={{ [ $('Entrada').first().json.phone ] }}", [1100, y])
    if_node(wf, "Já tem reunião?", "={{ $json.ja_marcada }}", "string", "notEmpty", [1320, y])
    set_resposta(wf, "Resposta: já marcada",
                 "=O lead já tem reunião em {{ $json.ja_marcada }}. Se ele quer mudar, chame cancelar_reuniao e depois agende de novo.",
                 [1540, y - 100])
    gcal_http(wf, "FreeBusy (slot)", "POST", freebusy_url,
              "={{ JSON.stringify({ timeMin: $('Validar horário').first().json.start, timeMax: $('Validar horário').first().json.end, timeZone: $('Config').first().json.timezone, items: [{ id: $('Config').first().json.calendar_id }] }) }}",
              [1540, y + 60])
    if_node(wf, "Slot livre?",
            "={{ ((($json.calendars || {})[$('Config').first().json.calendar_id] || {}).busy ?? [null]).length === 0 }}",
            "boolean", "true", [1760, y + 60])
    set_resposta(wf, "Resposta: ocupado",
                 "Esse horário acabou de ser ocupado. Chame ver_horarios e ofereça os mais próximos.", [1980, y + 160])
    code(wf, "Montar evento", r"""
const cfg = $('Config').first().json;
const v = $('Validar horário').first().json;
const l = $('Dados do lead').first().json;
const email = v.email || l.email || '';
const quem = l.company || l.name || ('+' + l.phone);
const descr = [
  `Conversa de ${cfg.duracao_reuniao_min} min com ${cfg.closer_nome}, da Kitou.`,
  '',
  'Pré-atendimento (SDR):',
  `Contato: ${l.name || '?'} | WhatsApp +${l.phone}`,
  `Segmento: ${l.segment || '?'} | cobranças/mês: ${l.monthly_charges ?? '?'} | emissor: ${l.issuer || '?'} | fit: ${l.fit}`,
  `Dor: ${l.pain || '?'}`,
  `Resumo: ${l.summary || '?'}`,
].join('\n');
const attendees = [{ email: cfg.closer_email }];
if (/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) attendees.push({ email, displayName: l.name || undefined });
return [{ json: {
  email_valido: attendees.length > 1 ? email : '',
  evento: {
    summary: `Kitou × ${quem}: cobrança e conciliação`,
    description: descr,
    start: { dateTime: v.start, timeZone: cfg.timezone },
    end: { dateTime: v.end, timeZone: cfg.timezone },
    attendees,
    conferenceData: { createRequest: { requestId: `sdr-${l.phone}-${Date.now()}`, conferenceSolutionKey: { type: 'hangoutsMeet' } } },
    reminders: { useDefault: true },
  },
} }];
""", [1980, y])
    gcal_http(wf, "Criar evento", "POST", cal_events + "?conferenceDataVersion=1&sendUpdates=all",
              "={{ JSON.stringify($json.evento) }}", [2200, y])
    pg(wf, "Salvar reunião", """
with m as (
  insert into sdr_meetings (lead_id, google_event_id, start_at, end_at, meet_link)
  values ($1::bigint, $2, $3::timestamptz, $4::timestamptz, $5)
  returning id
)
update sdr_leads
   set stage = 'agendado',
       next_followup_at = null,
       email = coalesce(nullif($6, ''), email),
       updated_at = now()
 where id = $1::bigint
returning (select id from m) as reuniao_id
""", "={{ [ $('Dados do lead').first().json.id, $json.id, $('Validar horário').first().json.start, $('Validar horário').first().json.end, $json.hangoutLink || $json.htmlLink || '', $('Montar evento').first().json.email_valido ] }}",
       [2420, y])
    set_resposta(wf, "Resposta: agendado",
                 "=Reunião marcada para {{ DateTime.fromISO($('Validar horário').first().json.start).setZone($('Config').first().json.timezone).setLocale('pt-BR').toFormat(\"cccc, dd/LL 'às' HH'h'mm\") }} (Brasília) com {{ $('Config').first().json.closer_nome }}. Link: {{ $('Criar evento').first().json.hangoutLink || 'vai no convite' }}. {{ $('Montar evento').first().json.email_valido ? 'Convite enviado para ' + $('Montar evento').first().json.email_valido + '.' : 'O lead não passou e-mail: o link fica só aqui no WhatsApp.' }} Confirme ao lead dia, hora e link, e diga que você manda um lembrete antes.",
                 [2640, y])
    wf.link("Ação", "Validar horário", 1)
    wf.chain("Validar horário", "Horário válido?")
    wf.link("Horário válido?", "Dados do lead", 0)
    wf.chain("Dados do lead", "Já tem reunião?")
    wf.link("Já tem reunião?", "Resposta: já marcada", 0)
    wf.link("Já tem reunião?", "FreeBusy (slot)", 1)
    wf.chain("FreeBusy (slot)", "Slot livre?")
    wf.link("Slot livre?", "Montar evento", 0)
    wf.link("Slot livre?", "Resposta: ocupado", 1)
    wf.chain("Montar evento", "Criar evento", "Salvar reunião", "Resposta: agendado")
    # "Horário válido?" falso termina com a resposta já montada em "Validar horário".
    set_resposta(wf, "Resposta: horário inválido", "={{ $json.resposta }}", [1100, y + 160])
    wf.link("Horário válido?", "Resposta: horário inválido", 1)

    # --- cancelar
    y = 650
    pg(wf, "Reunião ativa", """
select m.id, m.google_event_id
  from sdr_meetings m join sdr_leads l on l.id = m.lead_id
 where l.phone = $1 and m.status in ('agendada','confirmada') and m.start_at > now()
 order by m.start_at limit 1
""", "={{ [ $('Entrada').first().json.phone ] }}", [660, y], alwaysOutputData=True)
    if_node(wf, "Tem reunião?", "={{ !!$json.id }}", "boolean", "true", [880, y])
    gcal_http(wf, "Cancelar no Google", "DELETE",
              cal_events + "/{{ $json.google_event_id }}?sendUpdates=all", None, [1100, y - 60],
              onError="continueRegularOutput")
    pg(wf, "Marcar cancelada", """
with m as (update sdr_meetings set status = 'cancelada' where id = $1::bigint returning lead_id)
update sdr_leads set stage = 'qualificado', updated_at = now(),
       summary = concat_ws(' | ', summary, 'Cancelou reunião: ' || nullif($2, ''))
 where id = (select lead_id from m)
""", "={{ [ $('Reunião ativa').first().json.id, $('Entrada').first().json.motivo ] }}", [1320, y - 60])
    set_resposta(wf, "Resposta: cancelada",
                 "Reunião cancelada e convite retirado. Se o lead quer remarcar, chame ver_horarios.", [1540, y - 60])
    set_resposta(wf, "Resposta: sem reunião", "Não há reunião futura marcada para este lead.", [1100, y + 100])
    wf.link("Ação", "Reunião ativa", 2)
    wf.chain("Reunião ativa", "Tem reunião?")
    wf.link("Tem reunião?", "Cancelar no Google", 0)
    wf.link("Tem reunião?", "Resposta: sem reunião", 1)
    wf.chain("Cancelar no Google", "Marcar cancelada", "Resposta: cancelada")

    # --- confirmar
    y = 900
    pg(wf, "Confirmar presença", """
update sdr_meetings m set status = 'confirmada'
  from sdr_leads l
 where l.id = m.lead_id and l.phone = $1 and m.status = 'agendada' and m.start_at > now()
returning m.id
""", "={{ [ $('Entrada').first().json.phone ] }}", [660, y], alwaysOutputData=True)
    set_resposta(wf, "Resposta: confirmada",
                 "={{ $json.id ? 'Presença confirmada. Agradeça em uma frase curta.' : 'Não havia reunião pendente de confirmação.' }}",
                 [880, y])
    wf.link("Ação", "Confirmar presença", 3)
    wf.chain("Confirmar presença", "Resposta: confirmada")

    # --- atualizar_lead
    y = 1080
    code(wf, "Filtrar campos", r"""
// Só colunas da lista entram no UPDATE. Nome de coluna nunca vem do modelo.
const ent = $('Entrada').first().json;
let c = {};
try { c = typeof ent.campos === 'string' ? JSON.parse(ent.campos || '{}') : (ent.campos || {}); }
catch (e) { return [{ json: { sql: 'select 1', params: [], resposta: 'O campo campos precisa ser um JSON válido. Tente de novo.' } }]; }
const texto = (x) => String(x).trim().slice(0, 500);
const inteiro = (x) => { const n = parseInt(String(x).replace(/\D/g, ''), 10); return Number.isFinite(n) ? n : null; };
const enumOf = (...ok) => (x) => ok.includes(String(x).toLowerCase()) ? String(x).toLowerCase() : null;
const mapa = {
  nome: ['name', texto], empresa: ['company', texto], cargo: ['role', texto], email: ['email', texto],
  segmento: ['segment', enumOf('clinica','escola','academia','condominio','software','servicos','bpo','banco','outro')],
  quem_paga: ['payer_type', enumOf('pf','pj','ambos')],
  cobrancas_mes: ['monthly_charges', inteiro], meios: ['channels', texto],
  emissor: ['issuer', enumOf('asaas','inter','efi','iugu','sicoob','planilha','outro')],
  idade_cnpj_meses: ['cnpj_age_months', inteiro],
  tem_pix_automatico: ['has_pix_automatico', (x) => x === true || String(x).toLowerCase() === 'true'],
  dor: ['pain', texto], decisor: ['decision_maker', texto],
  fit: ['fit', enumOf('alto','medio','baixo','fora')],
  etapa: ['stage', enumOf('conversando','qualificado','perdido')],
  resumo: ['summary', (x) => String(x).trim().slice(0, 1200)],
};
const sets = [], params = [ent.phone], gravados = [];
for (const [k, val] of Object.entries(c)) {
  if (val === null || val === undefined || val === '') continue;
  if (k === 'retomar_em') {
    const d = DateTime.fromISO(String(val), { zone: 'America/Sao_Paulo' });
    if (!d.isValid) continue;
    params.push(d.set({ hour: 10, minute: 0 }).toISO());
    sets.push(`next_followup_at = $${params.length}::timestamptz, followup_count = 0`);
    gravados.push('retomar_em');
    continue;
  }
  const m = mapa[k];
  if (!m) continue;
  const v = m[1](val);
  if (v === null) continue;
  params.push(v);
  sets.push(`${m[0]} = $${params.length}`);
  gravados.push(k);
}
if (!sets.length) return [{ json: { sql: 'select 1', params: [], resposta: 'Nenhum campo reconhecido. Use as chaves da descrição da ferramenta.' } }];
return [{ json: {
  sql: `update sdr_leads set ${sets.join(', ')}, updated_at = now() where phone = $1`,
  params,
  resposta: `Registrado: ${gravados.join(', ')}. Siga a conversa.`,
} }];
""", [660, y])
    wf.add("Gravar campos", "n8n-nodes-base.postgres", 2.5, {
        "operation": "executeQuery",
        "query": "={{ $json.sql }}",
        "options": {"queryReplacement": "={{ $json.params }}"},
    }, [880, y], creds=PG, alwaysOutputData=True)
    set_resposta(wf, "Resposta: lead atualizado", "={{ $('Filtrar campos').first().json.resposta }}", [1100, y])
    wf.link("Ação", "Filtrar campos", 4)
    wf.chain("Filtrar campos", "Gravar campos", "Resposta: lead atualizado")

    # --- transferir_humano
    y = 1260
    pg(wf, "Pausar e marcar humano", """
update sdr_leads
   set stage = 'humano',
       bot_paused_until = now() + interval '24 hours',
       next_followup_at = null,
       updated_at = now()
 where phone = $1
returning name, company, phone, segment, monthly_charges, issuer, pain, summary, fit
""", "={{ [ $('Entrada').first().json.phone ] }}", [660, y])
    code(wf, "Aviso ao especialista", r"""
const cfg = $('Config').first().json;
const l = $json;
const motivo = $('Entrada').first().json.motivo || 'não informado';
const text = [
  `🔔 Lead para você assumir no WhatsApp do SDR`,
  `${l.name || 'Sem nome'}${l.company ? ' · ' + l.company : ''} · +${l.phone}`,
  `Motivo: ${motivo}`,
  `Segmento: ${l.segment || '?'} | cobranças/mês: ${l.monthly_charges ?? '?'} | emissor: ${l.issuer || '?'} | fit: ${l.fit}`,
  `Dor: ${l.pain || '?'}`,
  `Resumo: ${l.summary || '?'}`,
  `O bot fica pausado 24h para este lead. Responda pelo mesmo número.`,
].join('\n');
return [{ json: { phone: cfg.closer_whatsapp, text } }];
""", [880, y])
    evolution_send(wf, "Avisar especialista", "$json.phone", "$json.text", "0", [1100, y],
                   onError="continueRegularOutput")
    set_resposta(wf, "Resposta: transferido",
                 f"=Transferido. Diga ao lead, em uma frase, que {CFG['closer_nome']} segue a conversa por aqui no horário comercial. Depois disso não faça mais perguntas.",
                 [1320, y])
    wf.link("Ação", "Pausar e marcar humano", 5)
    wf.chain("Pausar e marcar humano", "Aviso ao especialista", "Avisar especialista", "Resposta: transferido")

    # --- opt_out
    y = 1420
    pg(wf, "Registrar opt-out", """
update sdr_leads
   set opted_out_at = now(), stage = 'opt_out', next_followup_at = null, updated_at = now()
 where phone = $1
""", "={{ [ $('Entrada').first().json.phone ] }}", [660, y], alwaysOutputData=True)
    set_resposta(wf, "Resposta: opt-out",
                 "Registrado. Responda uma frase curta e educada confirmando que não vai mais mandar mensagem. Não tente reverter.",
                 [880, y])
    wf.link("Ação", "Registrar opt-out", 6)
    wf.chain("Registrar opt-out", "Resposta: opt-out")
    wf.dump()


# ======================================================= 02 — follow-up

def wf_followup():
    wf = WF("Kitou SDR · 02 Follow-up", "02-sdr-followup")
    wf.add("A cada 30 min", "n8n-nodes-base.scheduleTrigger", 1.2, {
        "rule": {"interval": [{"field": "minutes", "minutesInterval": 30}]},
    }, [0, 300])
    config_node(wf, [220, 300])
    code(wf, "Horário comercial?", r"""
const cfg = $('Config').first().json;
const agora = DateTime.now().setZone(cfg.timezone);
if (agora.weekday > 5) return [];
if (agora.hour < cfg.followup_hora_inicio || agora.hour >= cfg.followup_hora_fim) return [];
return [{ json: { ok: true } }];
""", [440, 300])
    pg(wf, "Leads devidos", """
update sdr_leads l
   set next_followup_at = now() + interval '3 hours'   -- reserva: evita envio duplo se o fluxo cair no meio
 where l.id in (
   select id from sdr_leads
    where next_followup_at <= now()
      and opted_out_at is null
      and stage in ('novo','conversando','qualificado')
      and (bot_paused_until is null or bot_paused_until < now())
      and followup_count < $1::int
    order by next_followup_at
    limit 15
    for update skip locked)
returning l.*
""", "={{ [ $('Config').first().json.max_followups ] }}", [660, 300])
    pg(wf, "Histórico", """
select coalesce(string_agg(linha, E'\\n' order by id), '(sem histórico)') as historico
  from (select id,
               case when message->>'type' = 'human' then 'Lead: ' else 'Nós: ' end
               || left(coalesce(message->>'content', message->'data'->>'content', ''), 400) as linha
          from sdr_chat_memory
         where session_id = $1
         order by id desc
         limit 16) t
""", "={{ [ $json.phone ] }}", [880, 300])
    prompt = FOLLOWUP_PROMPT.replace(
        "{{passo}}", "{{ $('Leads devidos').item.json.followup_count + 1 }}"
    ).replace(
        "{{dados}}",
        "Nome: {{ $('Leads devidos').item.json.name || '?' }} | Empresa: {{ $('Leads devidos').item.json.company || '?' }}\n"
        "Segmento: {{ $('Leads devidos').item.json.segment || '?' }} | cobranças/mês: {{ $('Leads devidos').item.json.monthly_charges || '?' }} | emissor: {{ $('Leads devidos').item.json.issuer || '?' }}\n"
        "Dor: {{ $('Leads devidos').item.json.pain || '?' }}\n"
        "Resumo: {{ $('Leads devidos').item.json.summary || '?' }}",
    ).replace("{{historico}}", "{{ $json.historico }}")
    wf.add("Escrever follow-up", "@n8n/n8n-nodes-langchain.chainLlm", 1.5, {
        "promptType": "define",
        "text": "=" + prompt,
    }, [1100, 300])
    wf.add("Claude", "@n8n/n8n-nodes-langchain.lmChatAnthropic", 1.3, {
        "model": {"__rl": True, "mode": "id", "value": CFG["anthropic_model"]},
        "options": {"maxTokensToSample": 1024},
    }, [1100, 520], creds=ANTH)
    wf.link("Claude", "Escrever follow-up", kind="ai_languageModel")
    code(wf, "Preparar envio", r"""
const leads = $('Leads devidos').all();
return $input.all().map((item, i) => {
  const l = leads[i].json;
  const text = String(item.json.text || '').trim().replace(/^"|"$/g, '');
  const pular = !text || /^PULAR\b/i.test(text);
  return { json: { lead_id: l.id, phone: l.phone, text, pular, delay: Math.min(1500 + text.length * 35, 7000) } };
});
""", [1320, 300])
    if_node(wf, "Pular?", "={{ $json.pular }}", "boolean", "true", [1540, 300])
    pg(wf, "Encerrar cadência", """
update sdr_leads set next_followup_at = null, updated_at = now() where id = $1::bigint
""", "={{ [ $json.lead_id ] }}", [1760, 180])
    evolution_send(wf, "Enviar follow-up", "$json.phone", "$json.text", "$json.delay", [1760, 420],
                   onError="continueRegularOutput")
    mark_sent(wf, "Marcar como do bot", [1980, 420])
    pg(wf, "Avançar cadência", """
with u as (
  update sdr_leads
     set followup_count   = followup_count + 1,
         last_outbound_at = now(),
         next_followup_at = case followup_count + 1
                              when 1 then now() + interval '2 days'   -- D+3
                              when 2 then now() + interval '4 days'   -- D+7
                              when 3 then now() + interval '7 days'   -- D+14
                              else null end,
         stage            = case when followup_count + 1 >= $3::int then 'perdido' else stage end,
         updated_at       = now()
   where id = $1::bigint
  returning phone
)
insert into sdr_chat_memory (session_id, message)
select phone, jsonb_build_object('type', 'ai', 'content', $2::text,
       'additional_kwargs', '{}'::jsonb, 'response_metadata', '{}'::jsonb, 'tool_calls', '[]'::jsonb,
       'invalid_tool_calls', '[]'::jsonb)
  from u
""", "={{ [ $('Preparar envio').item.json.lead_id, $('Preparar envio').item.json.text, $('Config').first().json.max_followups ] }}",
       [2200, 420])
    wf.chain("A cada 30 min", "Config", "Horário comercial?", "Leads devidos", "Histórico",
             "Escrever follow-up", "Preparar envio", "Pular?")
    wf.link("Pular?", "Encerrar cadência", 0)
    wf.link("Pular?", "Enviar follow-up", 1)
    wf.chain("Enviar follow-up", "Marcar como do bot", "Avançar cadência")
    wf.dump()


# ======================================================= 03 — lembretes de reunião

def wf_reminders():
    wf = WF("Kitou SDR · 03 Lembretes de reunião", "03-sdr-lembretes")
    wf.add("A cada 5 min", "n8n-nodes-base.scheduleTrigger", 1.2, {
        "rule": {"interval": [{"field": "minutes", "minutesInterval": 5}]},
    }, [0, 300])
    config_node(wf, [220, 300])
    pg(wf, "Lembretes devidos", """
with due as (
  select m.id,
         case
           when m.reminder_15m_at is null
                and m.start_at <= now() + interval '15 minutes'
             then '15m'
           when m.reminder_2h_at is null
                and m.start_at <= now() + interval '2 hours' and m.start_at > now() + interval '20 minutes'
                and now() >= m.created_at + interval '1 hour'
             then '2h'
           when m.reminder_24h_at is null
                and m.start_at <= now() + interval '24 hours' and m.start_at > now() + interval '3 hours'
                and now() >= m.created_at + interval '2 hours'
             then '24h'
         end as tipo
    from sdr_meetings m
    join sdr_leads l on l.id = m.lead_id
   where m.status in ('agendada','confirmada')
     and m.start_at > now()
     and l.opted_out_at is null
   for update of m skip locked
), marcados as (
  update sdr_meetings m
     set reminder_15m_at = case when d.tipo = '15m' then now() else m.reminder_15m_at end,
         reminder_2h_at  = case when d.tipo in ('15m','2h') then coalesce(m.reminder_2h_at, now()) else m.reminder_2h_at end,
         reminder_24h_at = coalesce(m.reminder_24h_at, now())
    from due d
   where d.id = m.id and d.tipo is not null
  returning m.id, m.lead_id, m.start_at, m.meet_link, m.status, d.tipo
)
select k.*, l.phone, l.name
  from marcados k join sdr_leads l on l.id = k.lead_id
""", None, [440, 300])
    code(wf, "Escrever lembrete", r"""
// Texto fixo com variações: lembrete não precisa de LLM e não pode inventar nada.
const cfg = $('Config').first().json;
const tz = cfg.timezone;
const pick = (arr, seed) => arr[Math.abs(seed) % arr.length];
const hoje = DateTime.now().setZone(tz).startOf('day');
return $input.all().map(({ json: r }) => {
  const s = DateTime.fromISO(new Date(r.start_at).toISOString()).setZone(tz).setLocale('pt-BR');
  const diff = Math.round(s.startOf('day').diff(hoje, 'days').days);
  const dia = diff === 0 ? 'hoje' : diff === 1 ? 'amanhã' : s.toFormat('cccc (dd/LL)');
  const hora = s.minute ? s.toFormat("HH'h'mm") : s.toFormat("HH'h'");
  const nome = (r.name || '').split(' ')[0];
  const oi = nome ? `${nome}, ` : '';
  const link = r.meet_link || 'o link está no convite';
  let text;
  if (r.tipo === '24h') {
    text = r.status === 'confirmada'
      ? pick([
          `Oi ${oi}passando só pra lembrar: ${dia} às ${hora} você conversa com ${cfg.closer_nome}. Até lá!`,
          `${oi}lembrete rápido da nossa conversa ${dia} às ${hora} com ${cfg.closer_nome}. Qualquer coisa me chama por aqui.`,
        ], r.id)
      : pick([
          `Oi ${oi}tudo bem? Passando pra lembrar da conversa com ${cfg.closer_nome} ${dia} às ${hora}.\n\nSegue de pé? Se precisar mudar, me fala que eu ajusto.`,
          `${oi}a sua conversa com ${cfg.closer_nome} está marcada pra ${dia} às ${hora}.\n\nConsegue confirmar pra mim? Se o horário apertou, a gente remarca sem problema.`,
        ], r.id);
  } else if (r.tipo === '2h') {
    text = pick([
      `${oi}daqui a pouco, às ${hora}, é a conversa com ${cfg.closer_nome}. Deixo o link aqui pra facilitar: ${link}`,
      `Oi ${oi}hoje às ${hora} tem a conversa com ${cfg.closer_nome}. O link é este: ${link}`,
    ], r.id);
  } else {
    text = pick([
      `Começa em 15 minutos! ${cfg.closer_nome} entra por aqui: ${link}`,
      `${oi}em 15 min ${cfg.closer_nome} abre a sala: ${link}`,
    ], r.id);
  }
  return { json: { phone: r.phone, text, delay: 1500, tipo: r.tipo } };
});
""", [660, 300])
    evolution_send(wf, "Enviar lembrete", "$json.phone", "$json.text", "$json.delay", [880, 300],
                   onError="continueRegularOutput")
    mark_sent(wf, "Marcar como do bot", [1100, 300])
    pg(wf, "Guardar na memória", MEMORY_INSERT,
       "={{ [ $('Escrever lembrete').item.json.phone, $('Escrever lembrete').item.json.text ] }}", [1320, 300])
    pg(wf, "Fechar reuniões passadas", """
with r as (
  update sdr_meetings set status = 'realizada'
   where status in ('agendada','confirmada') and end_at < now() - interval '1 hour'
  returning lead_id
)
update sdr_leads set stage = 'realizado', updated_at = now()
 where id in (select lead_id from r) and stage = 'agendado'
""", None, [440, 520])
    wf.chain("A cada 5 min", "Config", "Lembretes devidos", "Escrever lembrete", "Enviar lembrete",
             "Marcar como do bot", "Guardar na memória")
    wf.link("Config", "Fechar reuniões passadas")
    wf.dump()


# ======================================================= 05 — novo lead (formulário/anúncio)

def wf_new_lead():
    wf = WF("Kitou SDR · 05 Novo lead (formulário)", "05-sdr-novo-lead")
    wf.add("Webhook formulário", "n8n-nodes-base.webhook", 2, {
        "httpMethod": "POST",
        "path": "kitou-sdr/lead",
        "authentication": "headerAuth",
        "responseMode": "onReceived",
        "options": {},
    }, [0, 300], creds=FORM, webhookId=nid("webhook", "lead"))
    config_node(wf, [220, 300])
    code(wf, "Normalizar lead", r"""
const b = $json.body ?? $json;
let tel = String(b.telefone || b.phone || b.whatsapp || '').replace(/\D/g, '');
if (tel.length === 10 || tel.length === 11) tel = '55' + tel;
if (tel.length < 12) return [];
return [{ json: {
  phone: tel,
  nome: String(b.nome || b.name || '').trim(),
  empresa: String(b.empresa || b.company || '').trim(),
  email: String(b.email || '').trim(),
  segmento: String(b.segmento || '').trim().toLowerCase(),
  origem: String(b.origem || b.utm_source || 'formulario').trim(),
  mensagem: String(b.mensagem || b.message || '').trim().slice(0, 500),
} }];
""", [440, 300])
    wf.add("Checar WhatsApp", "n8n-nodes-base.httpRequest", 4.2, {
        "method": "POST",
        "url": "={{ $('Config').first().json.evolution_url }}/chat/whatsappNumbers/{{ $('Config').first().json.evolution_instance }}",
        "authentication": "genericCredentialType",
        "genericAuthType": "httpHeaderAuth",
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": "={{ JSON.stringify({ numbers: [ $json.phone ] }) }}",
        "options": {},
    }, [660, 300], creds=EVO)
    code(wf, "Resolver número", r"""
// Usa o JID que o WhatsApp devolve: evita lead duplicado por causa do nono dígito.
const r = Array.isArray($json) ? $json[0] : ($json[0] ?? $json);
const lead = $('Normalizar lead').first().json;
if (!r || r.exists === false || !r.jid) return [];
return [{ json: { ...lead, phone: r.jid.split('@')[0] } }];
""", [880, 300])
    pg(wf, "Criar lead", """
insert into sdr_leads (phone, name, company, email, segment, source, stage, summary)
values ($1, nullif($2,''), nullif($3,''), nullif($4,''),
        case when $5 in ('clinica','escola','academia','condominio','software','servicos','bpo','banco','outro') then $5 end,
        $6, 'novo', nullif('Mensagem do formulário: ' || $7, 'Mensagem do formulário: '))
on conflict (phone) do update set
  name = coalesce(sdr_leads.name, excluded.name),
  company = coalesce(sdr_leads.company, excluded.company),
  email = coalesce(sdr_leads.email, excluded.email),
  updated_at = now()
returning id, phone, name, (xmax = 0) as novo, last_outbound_at, opted_out_at
""", "={{ [ $json.phone, $json.nome, $json.empresa, $json.email, $json.segmento, $json.origem, $json.mensagem ] }}",
       [1100, 300])
    if_node(wf, "Primeiro contato?",
            "={{ $json.novo || (!$json.last_outbound_at && !$json.opted_out_at) }}", "boolean", "true", [1320, 300])
    code(wf, "Mensagem de abertura", r"""
const cfg = $('Config').first().json;
const l = $('Resolver número').first().json;
const nome = (l.nome || '').split(' ')[0];
const oi = nome ? `Oi, ${nome}! ` : 'Oi! ';
const empresa = l.empresa ? ` da ${l.empresa}` : '';
const abertura = `${oi}Aqui é a ${cfg.sdr_nome}, assistente virtual do time da Kitou. Vi que você deixou seu contato${empresa} no nosso site.`;
const pergunta = l.mensagem
  ? `Li a sua mensagem por aqui. Pra eu entender melhor: hoje, como vocês conferem os PIX e boletos que entram contra o que foi cobrado?`
  : `Pra eu te direcionar do jeito certo: hoje, como vocês conferem os PIX e boletos que entram contra o que foi cobrado?`;
return [
  { json: { phone: l.phone, text: abertura, delay: 2500 } },
  { json: { phone: l.phone, text: pergunta, delay: 4000 } },
];
""", [1540, 300])
    evolution_send(wf, "Enviar abertura", "$json.phone", "$json.text", "$json.delay", [1760, 300])
    mark_sent(wf, "Marcar como do bot", [1980, 300])
    pg(wf, "Guardar na memória", MEMORY_INSERT,
       "={{ [ $('Mensagem de abertura').item.json.phone, $('Mensagem de abertura').item.json.text ] }}", [2200, 300])
    pg(wf, "Registrar abertura", """
update sdr_leads set last_outbound_at = now(), stage = 'conversando',
       next_followup_at = now() + interval '1 day', updated_at = now()
 where phone = $1
""", "={{ [ $('Resolver número').first().json.phone ] }}", [2420, 300], executeOnce=True)
    wf.chain("Webhook formulário", "Config", "Normalizar lead", "Checar WhatsApp", "Resolver número",
             "Criar lead", "Primeiro contato?")
    wf.link("Primeiro contato?", "Mensagem de abertura", 0)
    wf.chain("Mensagem de abertura", "Enviar abertura", "Marcar como do bot", "Guardar na memória",
             "Registrar abertura")
    wf.dump()


if __name__ == "__main__":
    print(f"config: {CFG_FILE.name}")
    wf_inbound()
    wf_followup()
    wf_reminders()
    wf_tools()
    wf_new_lead()
