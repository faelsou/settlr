# Subir a aplicação no Minikube

O manifesto da aplicação é [`k8s/minikube.yaml`](../k8s/minikube.yaml). Ele sobe o namespace `cobranca`: Postgres, Redis, o job `bootstrap` (migração e seed), o gateway, os três serviços, os workers, o Beat e o painel.

Não use [`docker/stack.yml`](../docker/stack.yml) aqui. Aquele arquivo é do Swarm.

A observabilidade fica de fora desse manifesto, no namespace `observability`. O passo a passo está na [seção própria](#observabilidade).

O painel encaminha `/auth`, `/invoices` e os demais prefixos da API para o gateway dentro do cluster. Para usar o painel no navegador basta o port-forward do `frontend-web`. Não é preciso publicar a API no host.

## O que precisa estar instalado

- [Minikube](https://minikube.sigs.k8s.io/docs/start/)
- `kubectl` apontando para o cluster do Minikube
- Docker, o mesmo que o Minikube vai usar para construir as imagens

As imagens `cobranca-api:dev` e `cobranca-web:dev` não vêm de um registry. O manifesto usa `imagePullPolicy: IfNotPresent`, então elas precisam existir no Docker **do** Minikube.

## 1. Subir o cluster

```bash
minikube start --memory=4096 --cpus=2
```

O perfil padrão se chama `minikube`. Se você usar outro (`-p <perfil>`), repita o nome nos comandos `minikube` abaixo e confira com `kubectl config current-context` que o `kubectl` está nesse cluster.

O PVC do Postgres pede a StorageClass `standard`. No perfil padrão ela já existe. Se o volume ficar `Pending`:

```bash
minikube addons enable storage-provisioner default-storageclass -p minikube
```

## 2. Apontar o Docker para o Minikube

O `eval` vale só para o shell atual. Build e qualquer `docker` seguinte têm de rodar nesse mesmo terminal. Um shell novo volta a falar com o Docker do host, e o pod sobe com `ImagePullBackOff` ou `ErrImageNeverPull`.

```bash
eval "$(minikube docker-env)"
docker info | grep -i name
```

A saída deve mostrar o daemon do Minikube, não o do host.

## 3. Construir as imagens

Na raiz do repositório, ainda com o `docker-env` ativo:

```bash
docker build -f docker/api.Dockerfile -t cobranca-api:dev .

docker build -f docker/web.Dockerfile \
  --build-arg NEXT_PUBLIC_API_BASE_URL= \
  --build-arg API_UPSTREAM=http://webhook-api:8000 \
  -t cobranca-web:dev .
```

`NEXT_PUBLIC_API_BASE_URL` vazio faz o browser chamar o próprio painel. `API_UPSTREAM` é o endereço do gateway **dentro** do cluster; o Next.js grava esse proxy no build. Trocar qualquer um dos dois exige rebuild da imagem web.

A imagem da API é única. Gateway, cobrança, conciliação, cadastro, workers, Beat e o job `bootstrap` usam `cobranca-api:dev` e mudam só o comando.

## 4. Aplicar o manifesto

```bash
kubectl apply -f k8s/minikube.yaml
kubectl -n cobranca wait --for=condition=complete job/bootstrap --timeout=180s
```

O job `bootstrap` espera o Postgres, roda `python -m app.cli migrate` e depois `python -m app.cli seed-demo`. O seed cria o tenant `demo` (Clínica Demo). Sem ele o login local responde que o tenant não existe. Roles, RLS e a conferência do banco estão em [`BANCO.md`](./BANCO.md).

Confira os pods:

```bash
kubectl -n cobranca get pods
```

Todos os Deployments devem ficar `Running` e `READY 1/1`. O Job fica `Completed`. Workers e o Beat não têm Service e não expõem porta.

| Workload | Imagem | Porta no cluster |
| --- | --- | --- |
| `postgres` | `postgres:16` | 5432 |
| `redis` | `redis:7` | 6379 |
| `webhook-api` | `cobranca-api:dev` | 8000 |
| `cobranca` | `cobranca-api:dev` | 8000 |
| `conci-pgto` | `cobranca-api:dev` | 8000 |
| `cadastro` | `cobranca-api:dev` | 8000 |
| `frontend-web` | `cobranca-web:dev` | 3000 |
| `worker-cobranca`, `worker-conciliacao`, `worker-cadastro`, `relo-disp` | `cobranca-api:dev` | nenhuma |
| `bootstrap` | `cobranca-api:dev` | Job, encerra depois do seed |

## 5. Port-forward do painel

O `port-forward` ocupa o terminal e cai quando o processo encerra. Deixe um terminal só para ele.

```bash
kubectl -n cobranca port-forward svc/frontend-web 3000:3000
```

Abra [http://127.0.0.1:3000](http://127.0.0.1:3000).

Login local (sem Supabase, porque a imagem web foi construída sem as variáveis dele):

- e-mail: `operador@demo.local`
- tenant: `demo`

O `kubectl` escuta em `127.0.0.1`. A porta da esquerda é a do host; a da direita é a do Service. Se a 3000 do host já estiver ocupada pelo `npm run dev`:

```bash
kubectl -n cobranca port-forward svc/frontend-web 3010:3000
```

Nesse caso o painel abre em `http://127.0.0.1:3010`. O `CORS_ORIGINS` do ConfigMap lista só `:3000`. Chamadas que saiam do browser direto para outro host são barradas; o fluxo normal não faz isso, porque o browser fala com o painel e o painel encaminha para o gateway.

Para soltar o terminal:

```bash
kubectl -n cobranca port-forward svc/frontend-web 3000:3000 >/tmp/pf-web.log 2>&1 &
```

Encerre com `kill` no PID, ou `fg` e Ctrl+C se ainda estiver no mesmo shell.

## Port-forward da API

Só quando for chamar o gateway direto do host (curl, cliente HTTP). O painel não precisa disso.

```bash
kubectl -n cobranca port-forward svc/webhook-api 8000:8000
```

`GET http://127.0.0.1:8000/health` deve responder 200. Os outros serviços também escutam 8000 **dentro** do cluster, cada um no próprio Service (`cobranca`, `conci-pgto`, `cadastro`). No host use outra porta local para não colidir com o gateway:

```bash
kubectl -n cobranca port-forward svc/cobranca 8001:8000
kubectl -n cobranca port-forward svc/conci-pgto 8002:8000
kubectl -n cobranca port-forward svc/cadastro 8003:8000
```

Postgres e Redis não têm porta publicada de propósito. Para inspecionar o banco a partir do host:

```bash
kubectl -n cobranca port-forward svc/postgres 5432:5432
```

Usuário `cobranca`, senha `cobranca`, database `cobranca`. Essas senhas estão no manifesto e servem só para este cluster local.

## Observabilidade

Sobe Prometheus, Thanos, Loki, Tempo, Grafana e o coletor no namespace `observability`. O mapa dos sinais e dos outros ambientes está em [`OBSERVABILIDADE.md`](./OBSERVABILIDADE.md). O ConfigMap da aplicação já aponta o OTLP para `otel-collector.observability.svc.cluster.local:4317`. Sem essa stack, a aplicação sobe do mesmo jeito e o exportador falha em silêncio.

```bash
kubectl apply -k k8s/observability
kubectl -n observability port-forward svc/grafana 3001:3000
```

Grafana em [http://127.0.0.1:3001](http://127.0.0.1:3001), usuário `admin`, senha `admin`. A pasta **Cobrança** é o painel da aplicação. A pasta **Kubernetes** mostra métricas, logs e traces do cluster.

O `3001` é a porta do host. O Service do Grafana escuta `3000` dentro do cluster, por isso o mapeamento é `3001:3000`.

## Atualizar o código

O Deployment não puxa tag nova se o nome continuar `cobranca-api:dev`. Reconstrua no daemon do Minikube e force os pods a relerem a imagem.

```bash
eval "$(minikube docker-env)"
docker build -f docker/api.Dockerfile -t cobranca-api:dev .
kubectl -n cobranca rollout restart deployment \
  webhook-api cobranca conci-pgto cadastro \
  worker-cobranca worker-conciliacao worker-cadastro relo-disp
```

Mudança de schema: apague o Job (Jobs concluídos não rodam de novo) e aplique outra vez.

```bash
kubectl -n cobranca delete job bootstrap
kubectl apply -f k8s/minikube.yaml
kubectl -n cobranca wait --for=condition=complete job/bootstrap --timeout=180s
```

O `seed-demo` de novo no mesmo banco é idempotente para o tenant `demo`. O volume do Postgres permanece. Para zerar os dados, apague o PVC depois dos pods que o usam:

```bash
kubectl delete -f k8s/minikube.yaml
kubectl -n cobranca delete pvc postgres-data
```

Painel: o Next.js embute `API_UPSTREAM` no build. Rebuild da imagem web e restart do Deployment.

```bash
eval "$(minikube docker-env)"
docker build -f docker/web.Dockerfile \
  --build-arg NEXT_PUBLIC_API_BASE_URL= \
  --build-arg API_UPSTREAM=http://webhook-api:8000 \
  -t cobranca-web:dev .
kubectl -n cobranca rollout restart deployment frontend-web
```

## HPA

[`k8s/hpa.yaml`](../k8s/hpa.yaml) escala só o `webhook-api` (1 a 4 réplicas, CPU 70%). Ele não entra no `kubectl apply -f k8s/minikube.yaml`. O Minikube precisa do metrics-server antes:

```bash
minikube addons enable metrics-server
kubectl apply -f k8s/hpa.yaml
kubectl -n cobranca get hpa
```

## Quando algo não sobe

| Sintoma | O que fazer |
| --- | --- |
| `ImagePullBackOff` ou `ErrImageNeverPull` em `cobranca-api` ou `cobranca-web` | O build foi no Docker do host. Rode `eval "$(minikube docker-env)"` e construa de novo. |
| Job `bootstrap` em `Error` ou `CrashLoop` no wait | `kubectl -n cobranca logs job/bootstrap`. Quase sempre o Postgres ainda não aceitava conexão, ou a imagem da API não está no daemon do Minikube. |
| PVC `postgres-data` em `Pending` | `minikube addons enable storage-provisioner default-storageclass`. |
| `port-forward` encerra com `lost connection` | O pod reiniciou. Rode o comando outra vez. O processo não reconecta sozinho. |
| `bind: address already in use` | Outro processo está na porta do host. Troque o número da esquerda (`3010:3000`) ou pare o `npm run dev`. |
| Login diz que o tenant não existe | O Job não completou. Espere `job/bootstrap` em `Complete` ou leia o log dele. |
| Painel abre e as chamadas falham | A imagem web foi construída com outro `API_UPSTREAM`. Rebuild com `http://webhook-api:8000`. |

Logs de um processo:

```bash
kubectl -n cobranca logs deploy/webhook-api
kubectl -n cobranca logs deploy/frontend-web
```

## Derrubar

O port-forward sai com Ctrl+C. O cluster:

```bash
kubectl delete -f k8s/minikube.yaml
kubectl delete -k k8s/observability
```

Para apagar o cluster inteiro: `minikube delete`. Isso remove também as imagens `cobranca-api:dev` e `cobranca-web:dev`.
