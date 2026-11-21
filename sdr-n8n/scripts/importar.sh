#!/usr/bin/env bash
# Importa os workflows do SDR no n8n pela API pública e liga o 01 ao 04.
#
#   N8N_URL=https://n8n.exemplo.com.br N8N_API_KEY=... ./scripts/importar.sh
#
# Opcional: ids das credenciais já criadas no n8n, para não escolher à mão.
#   SDR_CRED_PG SDR_CRED_REDIS SDR_CRED_ANTHROPIC SDR_CRED_EVOLUTION SDR_CRED_GCAL SDR_CRED_FORM
#
# Os workflows entram desativados. Ative 01, 02, 03 e 05 na tela depois de conferir as credenciais.
set -euo pipefail

: "${N8N_URL:?defina N8N_URL}"
: "${N8N_API_KEY:?defina N8N_API_KEY}"
command -v jq >/dev/null || { echo "precisa do jq" >&2; exit 1; }

cd "$(dirname "$0")/.."
python3 gerar_workflows.py

subst() {
  local s
  s=$(cat)
  for v in SDR_CRED_PG SDR_CRED_REDIS SDR_CRED_ANTHROPIC SDR_CRED_EVOLUTION SDR_CRED_GCAL SDR_CRED_FORM; do
    if [[ -n "${!v:-}" ]]; then s=${s//\"$v\"/\"${!v}\"}; fi
  done
  if [[ -n "${TOOLS_ID:-}" ]]; then s=${s//REPLACE_TOOLS_WORKFLOW_ID/$TOOLS_ID}; fi
  printf '%s' "$s"
}

criar() {
  local arquivo=$1 resp id
  resp=$(jq '{name, nodes, connections, settings}' "$arquivo" | subst |
    curl -sS -X POST "$N8N_URL/api/v1/workflows" \
      -H "X-N8N-API-KEY: $N8N_API_KEY" -H 'content-type: application/json' --data-binary @-)
  id=$(jq -r '.id // empty' <<<"$resp")
  if [[ -z "$id" ]]; then echo "falhou: $arquivo" >&2; echo "$resp" >&2; exit 1; fi
  echo "$id"
}

TOOLS_ID=$(criar workflows/04-sdr-ferramentas.json)
echo "04 ferramentas  -> $TOOLS_ID"
export TOOLS_ID
for f in 01-sdr-conversa 02-sdr-followup 03-sdr-lembretes 05-sdr-novo-lead; do
  echo "${f%%-*} $(printf '%-14s' "${f#*-sdr-}") -> $(criar "workflows/$f.json")"
done
