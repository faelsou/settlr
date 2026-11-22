-- Banco do SDR. Fica fora do Postgres do produto (sem RLS, sem tenant):
-- é a carteira comercial do próprio Settlr, não dado de cliente.
--   createdb settlr_sdr && psql settlr_sdr -f sql/schema.sql

create table if not exists sdr_leads (
  id                  bigserial primary key,
  phone               text not null unique,          -- dígitos do JID do WhatsApp, ex.: 5511999999999
  name                text,
  company             text,
  role                text,
  email               text,
  segment             text,                          -- clinica, escola, academia, condominio, software, servicos, bpo, banco, outro
  payer_type          text,                          -- pf, pj, ambos
  monthly_charges     integer,                       -- cobranças por mês
  channels            text,                          -- pix, boleto, cartao
  issuer              text,                          -- asaas, inter, efi, iugu, sicoob, planilha, outro
  cnpj_age_months     integer,
  has_pix_automatico  boolean,
  pain                text,                          -- a dor nas palavras do lead
  decision_maker      text,
  fit                 text not null default 'desconhecido'
                        check (fit in ('desconhecido','alto','medio','baixo','fora')),
  stage               text not null default 'novo'
                        check (stage in ('novo','conversando','qualificado','agendado','realizado','perdido','opt_out','humano')),
  source              text,
  summary             text,
  bot_paused_until    timestamptz,                   -- humano assumiu a conversa
  opted_out_at        timestamptz,
  last_inbound_at     timestamptz,
  last_outbound_at    timestamptz,
  followup_count      integer not null default 0,
  next_followup_at    timestamptz,
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now()
);

create index if not exists sdr_leads_followup_idx
  on sdr_leads (next_followup_at)
  where opted_out_at is null and next_followup_at is not null;

create table if not exists sdr_meetings (
  id               bigserial primary key,
  lead_id          bigint not null references sdr_leads(id),
  google_event_id  text unique,
  start_at         timestamptz not null,
  end_at           timestamptz not null,
  meet_link        text,
  status           text not null default 'agendada'
                     check (status in ('agendada','confirmada','cancelada','realizada','no_show')),
  reminder_24h_at  timestamptz,
  reminder_2h_at   timestamptz,
  reminder_15m_at  timestamptz,
  created_at       timestamptz not null default now()
);

create index if not exists sdr_meetings_ativas_idx
  on sdr_meetings (start_at)
  where status in ('agendada','confirmada');

-- Memória da conversa. Mesmo formato que o nó "Postgres Chat Memory" do n8n
-- (LangChain) cria sozinho. Criamos antes porque follow-up, lembrete e
-- primeira mensagem também escrevem aqui, para o agente saber o que já foi dito.
create table if not exists sdr_chat_memory (
  id          serial primary key,
  session_id  varchar(255) not null,
  message     jsonb not null
);

create index if not exists sdr_chat_memory_session_idx on sdr_chat_memory (session_id, id);
