# Criação do banco Postgres

Como criar a instância do Settlr do zero: dois databases no mesmo Postgres 16, três roles, o schema da aplicação via Alembic e as tabelas do checkpointer. O modelo de negócio está na seção 5 de [`TECNICA.md`](./TECNICA.md). O runtime (rede, volume, secret) está na seção 6 de [`ARQUITETURA-DEPLOY.md`](../ARQUITETURA-DEPLOY.md).

A imagem é `postgres:16`. Encoding `UTF8`. Timestamps de negócio são `timestamptz`. O fuso do cliente fica em `tenants.timezone` (padrão `America/Sao_Paulo`) e é aplicado na aplicação.

---

## 1. O que a instância contém

Um serviço `postgres`. Dois databases, para a Evolution não misturar a migration dela com o Alembic.

| Database | Dono | Quem conecta | Conteúdo |
| --- | --- | --- | --- |
| `cobranca` | role `cobranca` | API, workers, job de migração, postgres-exporter | Tabelas de negócio, RLS, checkpointer do LangGraph |
| `evolution` | role `evolution` | Evolution API | Sessão e fila da Evolution. O Alembic não toca neste database |

| Role | Atributos | Uso |
| --- | --- | --- |
| `cobranca` | superuser, criado pela imagem (`POSTGRES_USER`) | Só o job `python -m app.cli migrate`. Dona das tabelas. Superuser ignora RLS |
| `cobranca_app` | `LOGIN NOSUPERUSER NOBYPASSRLS`, sem ser dona das tabelas | Gateway, cobrança, conciliação, cadastro e os três workers |
| `evolution` | `LOGIN`, dona do database `evolution` | Evolution API. Senha igual à da role `cobranca` (`postgres_password`) |

A senha da role `cobranca` e da role `evolution` vem do secret `postgres_password`. A senha de `cobranca_app` vem de `postgres_app_password`. Em desenvolvimento os dois arquivos estão em `docker/dev-secrets/` e os valores são `cobranca` e `cobranca_app`.

A aplicação monta a URL em `app/core/config.py`. Runtime usa `cobranca_app`. Alembic e `PostgresSaver.setup()` usam `cobranca`.

```text
postgresql+psycopg://cobranca_app:<postgres_app_password>@<host>:<porta>/cobranca
postgresql+psycopg://cobranca:<postgres_password>@<host>:<porta>/cobranca
```

No host local a porta publicada é `55432`. Dentro do Compose, do Swarm e do Minikube o host é `postgres` e a porta é `5432`.

---

## 2. Ordem

A ordem importa. O script de roles roda uma vez, com o volume vazio. O schema da aplicação entra depois, com a role dona.

1. A imagem cria a role superuser `cobranca` e o database `cobranca`.
2. `docker/postgres/init-roles.sh` cria `cobranca_app`, a role `evolution` e o database `evolution`.
3. `python -m app.cli migrate` aplica o Alembic até `head` e cria as tabelas do checkpointer.
4. Em desenvolvimento, `python -m app.cli seed-demo` carrega o tenant `demo`. Em produção este comando recusa `ENV=prod`.

O entrypoint dos serviços da API não migra. Duas réplicas não podem disputar o lock do Alembic. No Swarm o job é `docker/migrate.sh`, antes de atualizar a stack. No Minikube o job se chama `bootstrap`.

---

## 3. Desenvolvimento local

```bash
docker compose -f docker/compose.dev.yml up -d postgres
```

O serviço publica `127.0.0.1:55432`, monta `init-roles.sh` em `/docker-entrypoint-initdb.d/` e usa o volume `pg_dev`. O healthcheck é `pg_isready -U cobranca -d cobranca`.

Com `api/.env` copiado de `api/.env.example` (`DATABASE_HOST=localhost`, `DATABASE_PORT=55432`):

```bash
cd api
python -m app.cli migrate
python -m app.cli seed-demo
```

`migrate` faz `alembic upgrade head` e, em seguida, `PostgresSaver.setup()`. As duas etapas usam a role `cobranca`.

Para recriar do zero, apague o volume e suba de novo. O script de init não roda em volume que já tem dados.

```bash
docker compose -f docker/compose.dev.yml down
docker volume rm cobranca-dev_pg_dev
docker compose -f docker/compose.dev.yml up -d postgres
```

---

## 4. Roles e o segundo database

O script abaixo é o de `docker/postgres/init-roles.sh`. No Swarm ele entra como config `postgres_init_roles`, modo `0555`, no mesmo caminho do entrypoint. No Minikube o texto equivalente está no ConfigMap `postgres-init`. As senhas chegam por arquivo, nunca por variável de ambiente da stack.

```sql
CREATE ROLE cobranca_app LOGIN PASSWORD :'app_pw' NOSUPERUSER NOBYPASSRLS;
GRANT CONNECT ON DATABASE :"db" TO cobranca_app;
GRANT USAGE ON SCHEMA public TO cobranca_app;

CREATE ROLE evolution LOGIN PASSWORD :'evo_pw';
CREATE DATABASE evolution OWNER evolution;
```

`:'app_pw'` e `:'evo_pw'` são parâmetros do `psql -v`. O script lê `POSTGRES_APP_PASSWORD_FILE` e `POSTGRES_PASSWORD_FILE`.

Se o volume já existia antes deste script, crie os objetos à mão conectado como `cobranca` e troque os placeholders pela senha real. `CREATE ROLE` falha se a role já existe. Confira com `\du` antes.

A Evolution recebe a URI `postgresql://evolution:<postgres_password>@postgres:5432/evolution`, montada em `docker/evolution/entrypoint.sh`. Ela cria o próprio schema nesse database.

---

## 5. Schema da aplicação

Fonte do DDL: `api/app/models/migrations/versions/`. A cadeia atual:

| Revisão | Arquivo | O que faz |
| --- | --- | --- |
| `0001` | `0001_schema_inicial.py` | 13 tabelas, índices, grants e RLS |
| `0002` | `0002_debtor_phones.py` | `debtors.phones text[]` e índice GIN |
| `0003` | `0003_tenant_whatsapp_senders.py` | `tenants.whatsapp_senders jsonb`, copiando o número legado |

Head esperado: `0003`. O Alembic grava a revisão em `public.alembic_version`.

Chave primária é `uuid`, gerado na aplicação (`uuid4`). A coluna não tem `DEFAULT` no banco: um `INSERT` administrativo precisa informar `id`. Dinheiro é `numeric(14,2)`. JSON de configuração e payload é `jsonb`.

`tenants` não tem RLS. É a tabela que o agendador e os webhooks leem para descobrir o tenant antes de `set_config('app.tenant_id', ...)`.

| Tabela | RLS | Papel |
| --- | --- | --- |
| `tenants` | não | Cliente, política, régua, horário, WhatsApp, emissor, `bank_feed`, base legal |
| `debtors` | sim | Devedor. Único `(tenant_id, document)`. Até cinco celulares em `phones` |
| `invoices` | sim | Título. Único `(tenant_id, external_id)`. `parent_id` e `agreement_id` nas parcelas |
| `dunning_events` | sim | Disparo da régua. Único `(invoice_id, step, channel)` |
| `conversations` | sim | Estado do agente. Único `(tenant_id, debtor_id)` |
| `messages` | sim | Histórico. `direction` é `in` ou `out` |
| `promises` | sim | Promessa de pagamento |
| `agreements` | sim | Acordo. Parcelas são linhas de `invoices` |
| `approvals` | sim | Pedido pausado no checkpointer, aguardando o operador |
| `payments` | sim | Entrada de dinheiro. Único `(tenant_id, e2e_id)`, `(tenant_id, file_hash)` e `(tenant_id, source_id)` |
| `matches` | sim | N:N pagamento e título. `provisional = true` ainda não tem confirmação do banco |
| `exceptions` | sim | Fila humana |
| `audit_log` | sim | Append-only para a role da aplicação |

No Postgres, `UNIQUE` admite vários `NULL`. Pagamento sem `e2e_id`, sem `file_hash` ou sem `source_id` não colide com outro na mesma condição. Os índices deduplicam PIX, comprovante e o lançamento do extrato automático quando o identificador veio preenchido.

Status gravados como texto, validados na aplicação (`app/models/states.py` e `app/models/enums.py`):

| Coluna | Valores |
| --- | --- |
| `invoices.status` | `aberto`, `em_cobranca`, `promessa`, `em_negociacao`, `renegociado`, `parcialmente_pago`, `pago`, `fila_humana`, `contestado`, `cancelado` |
| `payments.status` | `recebido_comprovante`, `aguardando_banco`, `recebido_banco`, `confirmado`, `conciliado`, `em_excecao`, `descartado` |
| `payments.origin` | `comprovante`, `extrato`, `webhook` |
| `exceptions.status` | `aberta`, `resolvida`, `rejeitada` |
| `conversations.state` | `agente`, `aguardando_identidade`, `aguardando_comprovante`, `aguardando_aprovacao`, `humano`, `encerrada` |
| `approvals.status` | `pendente`, `aprovada`, `rejeitada` |

### Grants e RLS

A revisão `0001` faz isto depois de criar as tabelas. Roda como `cobranca`.

```sql
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO cobranca_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO cobranca_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO cobranca_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO cobranca_app;
REVOKE UPDATE, DELETE ON audit_log FROM cobranca_app;
```

O `ALTER DEFAULT PRIVILEGES` vale para tabelas criadas depois pela role `cobranca`, inclusive as do checkpointer. `audit_log` perde `UPDATE` e `DELETE` de propósito: a aplicação insere o rastro e não reescreve.

Para cada tabela da lista com RLS:

```sql
ALTER TABLE <tabela> ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON <tabela>
  USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
```

`FORCE ROW LEVEL SECURITY` fica desligado. A role dona e o superuser continuam enxergando todas as linhas. Por isso a API entra como `cobranca_app`. Cada request e cada task de worker chamam `set_config('app.tenant_id', '<uuid>', true)` no início da transação (`app/core/db.py`). O terceiro argumento `true` limita o setting à transação.

Sem `app.tenant_id`, a policy compara com `NULL` e a role da aplicação não vê linha nenhuma. `audit_log.tenant_id` é anulável; linha com `tenant_id` nulo também fica invisível para `cobranca_app`.

---

## 6. Checkpointer

`setup_checkpointer()` em `app/agent/runner.py` abre o `PostgresSaver` do LangGraph com a role `cobranca` e chama `setup()`. As tabelas nascem no schema `public` do database `cobranca` (checkpoints, blobs e writes da conversa). O `thread_id` é o id da conversa.

Essas tabelas não têm policy de tenant. O isolamento delas é o `thread_id` que a aplicação escolhe. A role `cobranca_app` recebe DML pelos default privileges e é quem lê e grava durante o turno do agente.

---

## 7. Swarm

Antes do `docker stack deploy`:

```bash
docker secret create postgres_password ./postgres_password
docker secret create postgres_app_password ./postgres_app_password
```

O serviço `postgres` em `docker/stack.yml` usa a imagem `postgres:16`, a rede `backend`, uma réplica, constraint `node.labels.role == data`, limite de 1 GB e volume `postgres_data`. Não publica porta. Healthcheck: `pg_isready -U cobranca -d cobranca`.

Quando o serviço estiver saudável e o volume tiver passado pelo init:

```bash
REGISTRY=ghcr.io/<org> IMAGE_TAG=<git-sha> ./docker/migrate.sh
```

O script sobe um serviço one-off na rede `cobranca_backend`, com o secret `postgres_password`, `DATABASE_HOST=postgres` e `DATABASE_NAME=cobranca`, e roda `python -m app.cli migrate`. Remove o serviço ao terminar. Saída diferente de `Complete` interrompe o deploy.

Cada processo SQLAlchemy abre pool de 5 conexões e mais 5 de overflow (`app/core/db.py`). Gateway, três serviços, três workers e o beat são oito processos: até 80 conexões, fora o postgres-exporter. O `max_connections` padrão da imagem é 100. Subir réplica de worker pede `max_connections` maior ou um pooler na frente. O exporter usa `postgres:5432/cobranca` com `sslmode=disable` e a senha do secret `postgres_password`.

Backup previsto na arquitetura: `pg_dump` diário dos dois databases, cópia fora do nó.

```bash
pg_dump -Fc -h postgres -U cobranca -d cobranca -f cobranca.dump
pg_dump -Fc -h postgres -U cobranca -d evolution -f evolution.dump
```

Restore com `pg_restore` num volume novo, depois confira `alembic_version` antes de subir a API.

---

## 8. Minikube

`k8s/minikube.yaml` sobe o mesmo desenho no namespace `cobranca`: Secret `postgres-secrets`, ConfigMap `postgres-init`, PVC `postgres-data`, Service `postgres` e o Job `bootstrap`.

```bash
kubectl apply -f k8s/minikube.yaml
kubectl -n cobranca wait --for=condition=complete job/bootstrap --timeout=180s
```

O job espera a porta 5432, roda `migrate` e depois `seed-demo`. Para olhar o banco a partir do host:

```bash
kubectl -n cobranca port-forward svc/postgres 5432:5432
```

Recriar o volume: apague o PVC `postgres-data` e o Job `bootstrap`, e aplique o manifesto de novo. O passo a passo de falha do job está em [`MINIKUBE.md`](./MINIKUBE.md).

---

## 9. Conferência

Conecte como `cobranca` no database `cobranca`.

```sql
SELECT current_database(), version();

SELECT rolname, rolsuper, rolbypassrls
FROM pg_roles
WHERE rolname IN ('cobranca', 'cobranca_app', 'evolution');

SELECT datname, pg_catalog.pg_get_userbyid(datdba) AS owner
FROM pg_database
WHERE datname IN ('cobranca', 'evolution');

SELECT version_num FROM alembic_version;

SELECT c.relname, c.relrowsecurity AS rls
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relkind = 'r'
ORDER BY 1;

SELECT polrelid::regclass AS tabela, polname
FROM pg_policy
ORDER BY 1;
```

O resultado esperado:

- `version_num = 0003`
- `cobranca_app` com `rolsuper = false` e `rolbypassrls = false`
- database `evolution` com dono `evolution`
- RLS ligado em todas as tabelas de negócio menos `tenants`
- uma policy `tenant_isolation` em cada tabela com RLS
- `cobranca_app` sem `UPDATE`/`DELETE` em `audit_log`

Prova de isolamento, ainda como superuser, dentro de uma transação que troca de role:

```sql
BEGIN;
SET LOCAL ROLE cobranca_app;
SELECT count(*) FROM invoices;  -- 0: sem app.tenant_id a policy não libera linha
SELECT set_config('app.tenant_id', (SELECT id::text FROM tenants WHERE slug = 'demo'), true);
SELECT count(*) FROM invoices;  -- só o tenant demo, depois do seed
ROLLBACK;
```

`/health` do gateway responde 200 quando este Postgres e o Redis aceitam conexão.

---

## 10. Ao evoluir o schema

Nova coluna ou tabela entra em revisão Alembic nova, com `down_revision` apontando para a head atual. Tabela com `tenant_id` recebe `ENABLE ROW LEVEL SECURITY` e a policy `tenant_isolation` na mesma revisão. Grant para `cobranca_app` sai do `ALTER DEFAULT PRIVILEGES` se quem cria a tabela é a role `cobranca`. Tabela criada por outra role precisa de `GRANT` explícito.

O job de migração roda antes de atualizar os serviços. A revisão `0001` lista as tabelas com RLS numa tupla fixa: tabela nova não herda essa lista sozinha.
