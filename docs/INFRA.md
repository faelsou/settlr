# Infra por porte

Como o Settlr atende cliente B2B pequeno, médio e grande. O runtime de uma célula está em [`ARQUITETURA-DEPLOY.md`](../ARQUITETURA-DEPLOY.md). O gatilho medido para mudar uma peça está em [`DESENHO.md`](./DESENHO.md). O SLO está em [`SRE.md`](./SRE.md).

A primeira onda do produto tem 100 a 5.000 cobranças por mês. As faixas desta página são planejamento de capacidade. Tenants, mensagens por dia, tamanho do bucket e chamadas de LLM por título ainda não foram medidos.

---

## 1. Decisão

Uma plataforma, em células. Pequeno e médio moram na célula compartilhada. Grande ganha uma célula dedicada: a mesma imagem, o mesmo Postgres de dinheiro, outro disco e outros secrets.

O porte muda o isolamento, o canal de WhatsApp e a recuperação. Baixa, régua e RLS continuam os mesmos.

O piso de uma célula (três máquinas, objeto, backup, domínio) é o motivo de o pequeno compartilhar. Célula dedicada é faixa de contrato, combinada no onboarding, antes do primeiro título.

## 2. O que vale nos três portes

| Invariante | Neste sistema |
| --- | --- |
| Um Postgres por célula | Baixa, status, match e `audit_log` na mesma transação |
| RLS por `tenant_id` | Isolamento lógico. A célula dedicada soma isolamento físico |
| Beat em 1 réplica | Dois crons disparam a régua duas vezes |
| Uma Evolution por sessão | O estado do WhatsApp é arquivo local |
| LLM fora da baixa | Matcher e régua seguem se o modelo atrasar |
| Gateway na borda | O painel e os webhooks entram por ele. O browser não abre o banco |
| Correção fora do SLO | E2E duplicado, baixa só com comprovante, tenant cruzado ou etapa reenviada é incidente |

Região única, em São Paulo. Um primário escreve. A segunda região, quando existir, é standby do dado.

## 3. Faixas

| | Pequeno | Médio | Grande |
| --- | --- | --- | --- |
| Títulos / mês | Até 2.000 | 2.000 a 20.000 | Acima de 20.000, ou cláusula de isolamento |
| Célula | Compartilhada | A mesma | Dedicada |
| Se atrasar os outros | Rate limit do número | Fila e worker só dele. O RLS continua igual | Já está sozinho |
| WhatsApp | Evolution, 1 número | Evolution, até 5 números, 1 processo por sessão | API oficial (Cloud API ou BSP) |
| Postgres | Primário da célula | Primário. Réplica de leitura se o painel saturar. A baixa continua no primário | Primário + réplica de leitura. A baixa continua no primário |
| Fila | Redis AOF da célula | Fila do tenant barulhento no worker daquele serviço | Redis próprio. Broker durável se um restart perder task aceita |
| Comprovantes | Bucket da célula, retenção do contrato | O mesmo bucket, prefixo por tenant | Bucket próprio |
| Operação | SLO da plataforma | SLO da plataforma, régua isolada | RPO, janela de manutenção e drill de restore no contrato |

No grande, a Evolution sai do caminho crítico. Sessão em arquivo e pareamento por QR ficam no pequeno e no médio. A API oficial tira esse estado do nó de dados.

Homologação continua uma stack, `cobranca-hml`, com número de teste. Uma homologação por cliente é outra célula, e só entra quando o contrato paga esse piso.

## 4. Célula compartilhada

Três papéis, os mesmos do deploy de produção, com a observabilidade fora do disco do banco. O nó de 4 vCPU / 8 GB é o piloto. A partida abaixo é a primeira célula que recebe cliente pagante.

| Papel | O que corre | Partida |
| --- | --- | --- |
| Ingress | Traefik, TLS, portas 80 e 443 | 2 vCPU, 4 GB |
| App | Painel, gateway, cobrança, conciliação, cadastro, um worker por serviço, Beat × 1 | 8 vCPU, 16 GB |
| Dados | Postgres 16, Redis 7 com AOF, uma Evolution por sessão | 8 vCPU, 32 GB, NVMe |
| Objetos | Bucket `comprovantes`, fora do volume do Postgres | Storage S3 compatível |
| Observabilidade | Prometheus, Thanos, Loki, Tempo, Grafana | 4 vCPU, 8 GB, disco próprio |

Escala o worker pela fila do serviço e o gateway pela CPU. O Beat permanece em uma réplica. Postgres, Redis e MinIO permanecem sem porta publicada. O firewall do nó libera 22, 80 e 443.

Alerta `critical` tem um receiver independente do processo `aiops`.

A partida acima é um nó de cada papel. A célula que cobra cliente pagante é a da seção 5: duas zonas, banco com failover e a aplicação em dois nós.

## 5. Orçamento da célula com redundância

Cinco listas para a **mesma célula de produção**, em novembro de 2026. Preço sob demanda, 730 horas, sem reserva, sem imposto e sem desconto de contrato. O real usa a PTAX de venda de 06/11/2026, R$ 5,5013. Fora da conta: LLM, WhatsApp, domínio, Supabase, Sentry, Langfuse, gente e a célula de homologação. Um cliente grande que ganha célula dedicada repete este número.

O que sobe em par, em zonas diferentes:

| Peça | Forma | O que não duplica |
| --- | --- | --- |
| Borda | Balanceador em duas zonas | — |
| App | 2 nós de 8 vCPU e 16 GB | O Beat continua 1 réplica, num dos nós |
| Postgres | Primário de 8 vCPU e 32 GB, 200 GB, com standby e failover | A baixa continua no primário |
| Redis | Primário e réplica, AOF | — |
| Objetos | 100 GB durável, mais 200 GB de backup fora do disco do primário | — |
| Evolution | 1 processo de 2 vCPU e 4 GB, volume com snapshot | A segunda sessão não sobe. Perder o volume pede QR de novo |
| Observabilidade | 1 nó de 4 vCPU e 8 GB, disco próprio | Cair o Grafana não para a régua |
| Saída | 200 GB no mês | — |

SKU é o tamanho mais próximo da lista. Onde a família só existe com 32 GB para 8 vCPU, a memória extra entra no preço.

| Peça | AWS São Paulo | Azure Brasil Sul | GCP São Paulo | Oracle São Paulo | Hetzner Falkenstein + Nuremberg |
| --- | --- | --- | --- | --- | --- |
| App, 2 nós | 649 | 765 | 789 | 222 | 37 |
| Postgres com standby | 1.326 | 1.452 | 1.292 | 269 | 326 |
| Redis com réplica | 162 | 191 | 78 | 55 | 13 |
| Evolution, 1 ativo | 81 | 96 | 39 | 28 | 6 |
| Observabilidade | 162 | 191 | 197 | 55 | 10 |
| Discos das VMs | 64 | 96 | 58 | 40 | incluso |
| Backup | incluso no disco do banco | incluso na linha do banco | incluso na linha do banco | incluso no disco | 78 |
| Balanceador, NAT e saída | 246 | 210 | 175 | 35 | 24 |
| **Total, US$/mês** | **2.690** | **3.001** | **2.628** | **704** | **494** |
| **Total, R$/mês** | **14.800** | **16.510** | **14.460** | **3.870** | **2.720** |

De onde sai cada lista:

| Provedor | Região e falha | Banco | SKU de referência |
| --- | --- | --- | --- |
| AWS | `sa-east-1`, 3 zonas | RDS PostgreSQL Multi-AZ | App `c7g.2xlarge` a US$ 0,4443/h. Banco `db.m6g.2xlarge` a US$ 0,833/h na zona, o dobro no Multi-AZ. gp3 do RDS a cerca de US$ 0,276/GB, nas duas cópias. NAT Gateway a cerca de US$ 0,093/h, um por zona |
| Azure | Brazil South, zonas | Flexible Server, HA multi-zona | App `F8s_v2` a US$ 0,524/h. Banco 8 vCPU / 32 GB a US$ 0,96/h na zona, o dobro na HA. Redis e Evolution em `F2s_v2` a US$ 0,131/h |
| GCP | `southamerica-east1`, 3 zonas | Cloud SQL PostgreSQL, instância regional | App `c4-highcpu-8` a US$ 0,5402/h. Banco `db-n1-standard-8` (8 vCPU / 30 GB) a US$ 0,811/h na zona, o dobro na HA |
| Oracle | `sa-saopaulo-1`, 1 domínio e 3 fault domains | Par de VMs com replicação. A gente opera o failover | E5 Flex, US$ 0,03 por OCPU/h e US$ 0,002 por GB/h. Saída inclusa até 10 TB |
| Hetzner | Alemanha, dois datacenters, rede privada | Par `CCX33` com replicação. A gente opera o failover | Lista em dólar de 24/10/2026, sem VAT. App `CX43` a US$ 18,49. Banco `CCX33` a US$ 162,99, duas máquinas. Backup a 20% do servidor. 20 TB de saída inclusos em cada VM |

Reserva de um ano, sem pagamento adiantado, costuma tirar cerca de um terço do compute e do banco gerenciado. A lista acima é o teto, não o contrato.

A célula que atende a premissa de São Paulo e tira o failover do Postgres das nossas mãos fica na AWS ou no GCP, perto de R$ 15 mil por mês. A Azure repete o desenho e sai mais cara no Brasil Sul. A Oracle cabe em São Paulo e fica perto de R$ 4 mil, com um domínio só e o par de Postgres sob os nossos cuidados. A Hetzner é o piso, perto de R$ 2,7 mil, e o dado mora na Alemanha: serve de comparação e de laboratório, não de célula de cliente pagante enquanto o contrato pedir residência no Brasil.

## 6. Recuperação

O procedimento de hoje é `pg_dump` diário. A célula com cliente pagante arquiva WAL fora do nó e ensaia o restore. Dump que nunca voltou não é backup. A exportação de um tenant, para saída e LGPD, convive com o PITR da célula: o restore do volume inteiro não substitui a saída de um cliente.

Disponibilidade segue o SLO de [`SRE.md`](./SRE.md): 99,9% no webhook de banco em menos de 1 s (43 minutos em 30 dias) e 99,5% no painel. O zero de correção é o mesmo nas duas células.

| Meta | Célula compartilhada | Célula dedicada |
| --- | --- | --- |
| RPO | 15 minutos, WAL fora do nó | 5 minutos |
| RTO | 4 horas. Volume novo, quem escreve no banco parado | 1 hora, com standby |
| Correção | Zero no mês | Zero no mês |

## 7. Quando sair da célula compartilhada

O primeiro passo de um tenant barulhento é fila e worker próprios, ainda na mesma célula. Célula dedicada nasce quando um destes for verdade.

| Sinal | Primeiro passo | Célula dedicada quando |
| --- | --- | --- |
| CPU ou disco do Postgres no limite | Réplica de leitura para painel e métricas | O primário continua no limite com a baixa |
| Um tenant atrasa a régua dos outros | Fila e worker desse tenant. O RLS continua igual | A fila isolada ainda segura o ciclo dos demais |
| Task aceita some no restart do Redis | Broker durável. O lock de baixa pode continuar no Redis | O contrato pede fila e banco só dele |
| `audit_log` ou comprovantes acima do contrato | Retenção por tenant | O contrato pede bucket e backup exclusivos |
| Webhook em rajada | Gateway acima de 4 réplicas. A idempotência por E2E continua | O banco exige allowlist ou rede privada |
| LGPD com perímetro, VPC, pentest ou SLA com crédito | A célula compartilhada não assina isso | A célula nasce no onboarding |

## 8. O que espera um número

Kubernetes, banco por tenant, Kafka e duas regiões ativas esperam a seção de carga de [`DESENHO.md`](./DESENHO.md). Com uma célula compartilhada e poucas dedicadas, o Swarm e o Portainer continuam o lugar da produção: rollback, healthcheck e plantão já estão escritos para essa topologia.
