#!/usr/bin/env bash
# Deploy do k8s/minikube (kustomize) com uma tag do Docker Hub, smoke test e rollback.
#
#   scripts/deploy-minikube.sh <tag> [namespace-docker-hub]
#
# KUBE_CONTEXT escolhe o cluster (padrão: devops-dev). Se rollout ou smoke test
# falharem, os Deployments voltam para a tag que estava rodando antes. A migração
# do job bootstrap não é desfeita.
set -euo pipefail

tag="${1:?informe a tag da imagem (ex.: sha-1a2b3c4)}"
registry="${2:-faelsouz}"
context="${KUBE_CONTEXT:-devops-dev}"
ns=cobranca
manifest="$(dirname "$0")/../k8s/minikube"

kc() { kubectl --context "$context" "$@"; }

app_deployments() {
  kc -n "$ns" get deploy -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.spec.template.spec.containers[0].name}{" "}{.spec.template.spec.containers[0].image}{"\n"}{end}' \
    | awk '$3 ~ /cobranca-(api|web|site):/'
}

wait_rollouts() {
  local d
  for d in $(kc -n "$ns" get deploy -o name); do
    kc -n "$ns" rollout status "$d" --timeout=180s
  done
}

http_check() {
  local deploy="$1" url="$2"
  case "$deploy" in
    frontend-web|site) kc -n "$ns" exec "deploy/$deploy" -- wget -q -T 5 -O /dev/null "$url" ;;
    *) kc -n "$ns" exec "deploy/$deploy" -- python -c "import urllib.request; urllib.request.urlopen('$url', timeout=5)" ;;
  esac
}

smoke_test() {
  local svc
  http_check webhook-api http://127.0.0.1:8000/health
  for svc in cobranca conci-pgto cadastro; do
    http_check webhook-api "http://${svc}:8000/health"
  done
  http_check frontend-web http://127.0.0.1:3000/
  http_check site http://127.0.0.1:8080/healthz
  http_check site http://127.0.0.1:8080/entrar/
}

rollback() {
  if [ -z "$previous" ] || [ "$previous" = "$tag" ]; then
    echo "::error::Sem tag anterior diferente de $tag para voltar."
    return 1
  fi
  echo "::warning::Voltando os Deployments para $previous"
  local name container image
  while read -r name container image; do
    kc -n "$ns" set image "deploy/$name" "${container}=${image%:*}:${previous}"
  done < <(app_deployments)
  wait_rollouts
}

kc cluster-info >/dev/null

previous=""
if kc -n "$ns" get deploy webhook-api >/dev/null 2>&1; then
  current="$(kc -n "$ns" get deploy webhook-api -o jsonpath='{.spec.template.spec.containers[0].image}')"
  previous="${current##*:}"
fi
echo "Cluster: $context | anterior: ${previous:-nenhuma} | nova: $tag"

rendered="$(mktemp)"
trap 'rm -f "$rendered"' EXIT
kc kustomize "$manifest" \
  | sed -E "s#image: [^ ]*cobranca-(api|web|site):[^ ]+#image: ${registry}/cobranca-\1:${tag}#" > "$rendered"

# Template de Job é imutável: o bootstrap precisa ser recriado a cada tag.
kc -n "$ns" delete job bootstrap --ignore-not-found --wait=true
kc apply -f "$rendered"

if ! kc -n "$ns" wait --for=condition=complete job/bootstrap --timeout=300s; then
  kc -n "$ns" logs job/bootstrap --tail=50 || true
  echo "::error::Job bootstrap não completou."
  rollback || true
  exit 1
fi

if ! wait_rollouts || ! smoke_test; then
  echo "::error::Rollout ou smoke test falhou com $tag."
  kc -n "$ns" get pods -o wide || true
  rollback || true
  exit 1
fi

# O AIOps (k8s/aiops) usa a mesma imagem. Se não está instalado, fica como está.
if kc -n observability get deploy aiops >/dev/null 2>&1; then
  kc -n observability set image deploy/aiops "aiops=${registry}/cobranca-api:${tag}"
  kc -n observability rollout status deploy/aiops --timeout=120s || echo "::warning::aiops não ficou pronto com $tag."
fi

kc -n "$ns" get pods -o wide
echo "Deploy de $tag concluído."
