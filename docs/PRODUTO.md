# Produto e regras de negócio

Documento do **Settlr** como produto: o que entrega, para quem, e as regras que o código aplica. O detalhe operacional dos fluxos está em [`FLUXOS.md`](../FLUXOS.md). A visão original está em [`Settlr — Arquitetura.md`](../Settlr%20%E2%80%94%20Arquitetura.md).

---

## 1. Promessa

Cobrar, negociar e confirmar pagamentos pelo WhatsApp, e conferir cada entrada contra o que foi vendido — **sem a equipe precisar cobrar na mão ou bater planilha**.

O cliente da primeira onda, e o do piloto, é PME com recorrência ou parcelamento (clínicas, escolas, academias, condomínios, assinaturas, B2B), 100 a 5.000 cobranças/mês, recebendo principalmente PIX e boleto.

O produto também atende BPO e banco. Com esses três compradores ele abrange o mercado de quem cobra e de quem confere o que entrou, e não fica preso à PME do piloto. A regra não muda: uma conta por empresa, comprovante que não quita sozinho, política como teto. Dado de uma conta não entra na outra.

| Comprador | Carteira | No produto |
| --- | --- | --- |
| PME | A própria | Primeira onda e piloto. A equipe do Settlr opera a conta |
| BPO | Várias empresas | Cada empresa é uma conta. O BPO opera a cobrança; o dado de um cliente dele não cruza com o do outro |
| Banco | A carteira do banco | A mesma régua e a mesma baixa. O banco é a conta, não um emissor a mais. O adaptador de emissor em `main` continua o Asaas |

## 2. Três peças do produto

| Peça | Para quem | O que faz |
| --- | --- | --- |
| Régua de cobrança | Devedor | Lembra antes e depois do vencimento, com template oficial |
| Agente de WhatsApp | Devedor | Responde quando a pessoa fala ou manda áudio: comprovante, promessa, parcelamento, contestação, opt-out |
| Painel | Operador do tenant | Resolve o que o sistema não baixa sozinho e configura a política |

O devedor nunca vê o painel. Quem opera nunca escreve no banco direto: cada ação passa pela API e deixa rastro no `audit_log`.

A jornada comercial, etapa por etapa, está em [JORNADA-VENDA-B2B.md](./JORNADA-VENDA-B2B.md). A conta abre por um de dois caminhos, e nos dois nasce desligada:

| Caminho | Quem faz | Onde | Quem liga a conta |
| --- | --- | --- | --- |
| Pela tela | A própria empresa, que entra como dono | `/comecar` | O dono, em Configurações |
| Pela API | A agência: a equipe do Settlr que opera várias contas (role `agencia`) | `POST /admin/tenants` | A agência, em `POST /admin/tenants/{id}/activate` |

A conta precisa de política, régua, horário, WhatsApp e base legal. Sem um deles, a ativação recusa. A agência é o próprio Settlr, operador dos dados no contrato, e não um intermediário entre o Settlr e a empresa. O piloto é operado por essa equipe. A tese de escala é o contador, e quem a valida é o primeiro contador que pedir o arquivo do período (`GET /payments/export`).

| Papel | O que faz |
| --- | --- |
| Dono | Configura a política, a régua, o horário e convida a equipe |
| Financeiro | Confirma a baixa |
| Atendente | Acompanha a fila e não confirma baixa |

O convite sai por e-mail, com um link só da pessoa. Não há senha nesse e-mail e ninguém compartilha o próprio login.

## 3. O que o operador vê (fases do MVP)

| Fase | Telas | Papel no negócio |
| --- | --- | --- |
| 1 | Login, Exceções, Pagamentos | Conferir dinheiro que entrou e baixar o que o matcher não fechou |
| 2 | Títulos | Ver o título, a régua que já rodou e as baixas |
| 3 | Conversas, Entregas, Aprovações | Assumir o WhatsApp, ver se a mensagem chegou e decidir pedido fora da política |
| 4 | Configurações, Métricas | Política, horário, templates; recuperação, DSO contra a linha de base da implantação, baixa automática |

A conciliação vem primeiro: não fala com o devedor e gera prova de valor para vender a régua.

## 4. Regras de ouro

1. **O LLM não decide dinheiro.** Ele lê comprovante, transcreve áudio, classifica intenção e conversa. Régua, matching e baixa são código. A régua continua em template de texto.
2. **O banco é a fonte da verdade da baixa.** Comprovante sozinho nunca quita o título.
3. **A política do tenant é o teto.** O agente só oferece opções que o código já gerou.
4. **Humano é a última instância.** Match incerto, contestação, leitura fraca, áudio sem transcrição e pedido fora da política vão para a fila.
5. **Tudo é por tenant.** Nenhum fluxo cruza dados entre empresas clientes. Score, antecipação e régua que aprende entre empresas ficam fechados no MVP. Reabrir exige base legal e anonimização de dados agregados escritas no contrato. A decisão desta versão é manter fechado ([CONTRATO.md](./CONTRATO.md)).

---

## 5. Regras de cobrança (régua)

A régua é **determinística** e dispara por cron. O agente de IA só entra quando o devedor responde.

### Régua padrão (configurável)

| Momento | Ação | Canal |
| --- | --- | --- |
| D-3 | Lembrete amigável + PIX copia-e-cola | WhatsApp template |
| D0 | Vence hoje | WhatsApp template |
| D+1 | Não identificamos o pagamento + 2ª via | WhatsApp template |
| D+3 | Convite a quitar, sem anunciar desconto | WhatsApp template |
| D+5 | Convite a negociar (sem inventar condição) | WhatsApp template |
| D+7 | Novo convite a conversar, com o PIX | WhatsApp template |
| D+10 | Lembrete do título em aberto | WhatsApp template |
| D+15 | Última tentativa automática | WhatsApp + e-mail |
| D+21 | Aviso de que a equipe assume, sem ameaça | WhatsApp template |
| D+30 | Sai da régua → fila humana | Painel |

### Pix Automático

Decisão: Settlr com Pix Automático ligado. Quando o débito automático quita, D-3 e D0 saem da régua do título. A régua ganha duas etapas: convite à adesão (no primeiro título ou no D+1 de quem não aderiu) e débito falhou (no dia em que o débito é recusado). O que vendemos para quem já tem Pix Automático é, nesta ordem: (1) conciliação de todo dinheiro que entra, em qualquer banco ou emissor, com o arquivo do contador; (2) a falha de débito tratada por conversa e acordo dentro da política. Dinheiro fora do Asaas é parte de (1).

O pagador do Pix Automático é pessoa física. O recebedor é pessoa jurídica com CNPJ ativo há pelo menos seis meses (Resolução BCB nº 482). Empresa com menos tempo de atividade fica de fora no início. Título cujo pagador é pessoa jurídica, a fatia B2B, permanece na régua de PIX copia-e-cola e boleto. Condomínios também permanecem nessa régua. Convite de adesão que o pagador não confirmou não se repete em menos de 30 dias: o Banco Central trata o reenvio idêntico nesse prazo como excesso.

As duas etapas novas não dependem de PIX copia-e-cola. A trava de “título sem código de pagamento não recebe etapa” continua valendo para a régua de copia-e-cola e boleto.

No piloto, a mesma carteira compara a régua de dez etapas com quatro (D0, D+1, D+5, D+15) e mede a recuperação marginal de cada etapa. O custo que pesa é o template da Meta por disparo.

### Regras duras

- Nunca envia fora do **horário permitido** do tenant (padrão: 08:00–20:00, seg–sáb).
- Nunca reenvia a mesma etapa no mesmo canal.
- **Opt-out** interrompe a régua na hora; o título continua existindo.
- Devedor em opt-out **é ingerido**, mas **não entra na régua ativa**.
- Promessa ativa **pausa** a régua até `data_prometida + 1`.
- Se o cron atrasar, envia só a **etapa mais recente**, não uma rajada das anteriores.
- Título sem PIX copia-e-cola e sem linha digitável de boleto **não recebe etapa**. O operador vê essa lista separada antes de ativar a conta. Quando o código chega, entra só a etapa vigente.
- Disparo proativo usa **template oficial aprovado na Meta**. Texto livre do modelo fica na resposta, nunca na régua.
- A conta só liga a régua com o **número pareado** (sessão `open` na Evolution) e com template aprovado em cada etapa de WhatsApp. Sem os dois, a ativação recusa. Instância `WHATSAPP-BAILEYS` não tem template na Meta, então essa trava não passa nela. Afrouxar a trava não é o caminho: a régua em produção espera a integração `WHATSAPP-BUSINESS`. O estado da instância está em [CONSELHO.md](./CONSELHO.md).
- Em produção a conta também não liga sem o parecer do [SETL-15](https://rafadsouz.atlassian.net/browse/SETL-15) registrado em `LEGAL_OPINION_REF`. Os textos dessa versão estão em [TEXTOS-REGUA.md](./TEXTOS-REGUA.md).
- Nunca ameaça, nunca menciona terceiros, nunca cobra em grupo.

---

## 6. Regras de conversa (quando o devedor responde)

Antes de mostrar valor: **confirmar identidade** (ex.: 3 dígitos do CPF). Falha repetida encerra.

| Intenção | O que o produto faz | Agente conversa? |
| --- | --- | --- |
| Já paguei | Pede comprovante e manda para conciliação | não |
| Vou pagar dia X | Registra promessa, pausa régua até X+1 | não |
| Parcelar / desconto | Oferece só o que cabe na política | sim |
| Contestação / valor errado | **Não negocia.** Abre exceção e chama humano | não |
| Parar / hostil / sensível | Opt-out ou escalonamento imediato | não |
| Dúvida simples | Responde com dados dos títulos | sim |

Nota de voz e áudio de um devedor conhecido viram transcrição e seguem a mesma tabela. A transcrição fica na conversa, com o título citado quando a pessoa responde em cima de um envio. Imagem e documento continuam comprovante: áudio não entra no OCR.

A resposta do agente pode sair como nota de voz, dentro do horário do tenant. O texto dessa resposta fica gravado. Fora do horário, a mesma frase sai escrita. Grupo não recebe resposta de cobrança em voz. Sem transcrição utilizável, o turno não inventa o que foi dito e abre a exceção `transcricao_indisponivel`.

### Promessa

- A data precisa ser **futura** e dentro do limite do tenant (padrão: 15 dias).
- Cumprimento **não** é confiança no texto: só a conciliação marca `cumprida`.
- Se até X+1 não houver baixa, a régua retoma e a métrica conta promessa quebrada.

### Negociação

Política padrão (editável na tela Configurações):

| Parâmetro | Padrão | Significado |
| --- | --- | --- |
| Desconto máx. à vista | 10% | Teto do desconto à vista |
| Entrada mínima | 20% | Teto inferior da entrada no parcelado |
| Máx. de parcelas | 6 | Inclui a entrada |
| Parcela mínima | R$ 50 | Abaixo disso a opção não é gerada |
| Intervalo | 30 dias | Entre parcelas |
| Juros ao mês | 0% | Sobre o valor financiado |
| Primeiro vencimento | 3 dias | A partir de hoje |
| Promessa máxima | 15 dias | Teto da data prometida |

O código gera as opções (`à vista` e `parcelado_Nx`). O LLM **escolhe entre elas**. Pedido fora da política (ex.: 8x quando o teto é 6) **pausa o agente** e abre aprovação no painel.

Ao aceitar um acordo: o emissor do tenant gera PIX ou boleto para cada parcela; os títulos de origem viram `renegociado`; nascem parcelas novas ligadas por `parent_id` / `agreement_id`, já com o código de pagamento. Sem emissor ou sem código, o acordo não fica gravado. Pedido fora da política continua na aprovação, sem o agente inventar condição.

---

## 7. Regras de conciliação

Todo dinheiro que entra vira um `payment`. No caminho feliz isso acontece sem arquivo: o Open Finance da conta ou o extrato do emissor. A importação de OFX ou CSV continua no painel, só como exceção. O matcher tenta casar com título em aberto e **para no primeiro critério que fecha**.

| Camada | Critério | Resultado |
| --- | --- | --- |
| 1 | `txid` ou E2E igual ao do título | Baixa automática |
| 2 | Valor + documento do pagador + janela de data | Baixa automática |
| 3 | Valor + nome aproximado + data, ou soma de títulos do mesmo devedor | Sugestão com score → humano |
| 4 | Sem candidato | Exceção “não identificado” |

### Proteções de caixa

- **Deduplicação:** o mesmo `e2e_id` ou `file_hash` não baixa duas vezes. O extrato automático também ignora o lançamento que já entrou (`source_id` ou `txid` do emissor).
- **Comprovante falso:** origem `comprovante` fica `aguardando_banco`. Só vira baixa definitiva com extrato ou webhook.
- **Diferença de valor:** juros/desconto dentro da regra do tenant aplica; parcial deixa o título `parcialmente_pago`; fora da regra vira exceção.
- Um pagamento pode quitar vários títulos; vários pagamentos podem quitar um título (`matches` N:N).
- Título que fica `pago` marca a cobrança como recebida no emissor do piloto (Asaas, id `pay_`). O devedor não recebe aviso novo do emissor. Cobrança que o próprio webhook do emissor já quitou não é marcada de novo. Referência de planilha não vai para o emissor.
- O único adaptador de emissor em `main` é o Asaas. Inter, Efí, iugu e Sicoob ficam no roadmap; até lá a planilha cobre esses títulos.
- O Open Finance é cliente genérico da API de contas. A conta informa `base_url`, `token` e `account_id` em `bank_feed.open_finance`. O código não nomeia um banco.
- Em Pagamentos, o arquivo do período traz título, valor, data e identificador bancário (o E2E; se o banco não mandou, o txid). Só entra baixa definitiva. Comprovante ainda sem banco fica de fora.

### Janela de data (padrão)

- 10 dias antes do vencimento até 60 dias depois.
- Sobrepagamento tolerado: 2%.
- Subpagamento: 0% (a menos que baixa parcial esteja ligada).

---

## 8. Fila de exceções (revisão humana)

| Tipo | Quando nasce | O que o operador faz |
| --- | --- | --- |
| `pagamento_nao_identificado` | Camada 4 | Procura o título e confirma a alocação |
| `sugestao_match` | Camada 3 | Confirma ou rejeita a sugestão |
| `diferenca_valor` | Valor fora da regra | Aplica parcial/total ou rejeita |
| `leitura_baixa_confianca` | OCR/LLM falhou na validação | Corrige valor, data, E2E, pagador |
| `contestacao` | Devedor contestou | Decide a favor da cobrança (volta à régua) ou do devedor (cancela) |
| `fila_humana` | Título em D+30 | Sai da régua automática |

Item novo nessa fila — exceção, contestação, aprovação fora da política ou título em D+30 — avisa o dono da empresa. O aviso sai por e-mail ou, sem e-mail, pelo WhatsApp interno cadastrado em Configurações. O texto diz o tipo e há quanto tempo o item está parado. O devedor não recebe esse aviso: contato de quem está em opt-out nunca é o destino.

Confirmar pagamento **sem confirmação do banco** é recusado (409). Rejeitar uma sugestão reabre o pagamento como “não identificado”. Toda decisão grava responsável e `audit_log`.

---

## 9. Máquinas de estado

### Título

`aberto` → `em_cobranca` → (`promessa` \| `em_negociacao` \| `parcialmente_pago`) → `pago`

Saídas laterais: `renegociado` (acordo), `fila_humana` (D+30), `contestado`, `cancelado`.

`pago`, `cancelado` e `renegociado` são finais.

### Pagamento

- Comprovante: `recebido_comprovante` → `aguardando_banco` → `confirmado` → `conciliado` ou `em_excecao`
- Banco/extrato: `recebido_banco` → `confirmado` → `conciliado` ou `em_excecao`
- Exceção: humano confirma (`conciliado`) ou descarta (`descartado`)

---

## 10. Compliance (guardrails de produto)

| Risco | Regra |
| --- | --- |
| Cobrança vexatória (CDC art. 42) | Textos versionados; sem ameaça; horário por tenant |
| Pessoa errada | Identidade antes de valores; nunca cobrar em grupo |
| LGPD | Base legal por tenant; RLS; `audit_log`; retenção na minuta do contrato |
| Banimento do número | Template oficial + rate limit + opt-out imediato |
| Agente inventa condição | Tools só devolvem opções da política |
| Alucinação no comprovante | Validação de E2E, data e valor; baixa confiança → exceção |

Nenhum tenant entra em produção sem política, régua, horário, número WhatsApp, base legal e o parecer registrado no SETL-15. A minuta está em [CONTRATO.md](./CONTRATO.md).

## 11. Métricas que o painel mostra

- Taxa de recuperação: valor recebido após o vencimento ÷ valor vencido
- Dias médios de atraso (DSO) do período, comparados com a linha de base gravada no onboarding
- Promessas cumpridas ÷ feitas
- % de baixa automática (sem humano)
- Exceções abertas e tempo médio de resolução

## 12. Precificação

- **Fase 1:** mensalidade fixa só pela conciliação, com o arquivo do contador. O valor sai de conversas com clínica, escola e academia. O roteiro e a faixa de teste (R$ 300 a R$ 1.500) estão em [CONSELHO.md](./CONSELHO.md). A métrica é quantas pessoas fecham, não a média do que disseram que pagariam.
- **Recuperação:** a variável sobre valor recuperado só entra quando houver grupo de controle (10% dos títulos fora da régua).
- Setup único (emissor + importação + régua) continua previsto. A faixa numérica da mensalidade espera as conversas.
