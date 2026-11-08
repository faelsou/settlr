# Produto e regras de negócio

Documento do **Settlr** como produto: o que entrega, para quem, e as regras que o código aplica. O detalhe operacional dos fluxos está em [`FLUXOS.md`](../FLUXOS.md). A visão original está em [`Settlr — Arquitetura.md`](../Settlr%20%E2%80%94%20Arquitetura.md).

---

## 1. Promessa

Cobrar, negociar e confirmar pagamentos pelo WhatsApp, e conferir cada entrada contra o que foi vendido — **sem a equipe precisar cobrar na mão ou bater planilha**.

O cliente da primeira onda é PME com recorrência ou parcelamento (clínicas, escolas, academias, condomínios, assinaturas, B2B), 100 a 5.000 cobranças/mês, recebendo principalmente PIX e boleto.

## 2. Três peças do produto

| Peça | Para quem | O que faz |
| --- | --- | --- |
| Régua de cobrança | Devedor | Lembra antes e depois do vencimento, com template oficial |
| Agente de WhatsApp | Devedor | Responde quando a pessoa fala: comprovante, promessa, parcelamento, contestação, opt-out |
| Painel | Operador do tenant | Resolve o que o sistema não baixa sozinho e configura a política |

O devedor nunca vê o painel. O operador nunca escreve no banco direto: cada ação passa pela API e deixa rastro no `audit_log`.

## 3. O que o operador vê (fases do MVP)

| Fase | Telas | Papel no negócio |
| --- | --- | --- |
| 1 | Login, Exceções, Pagamentos | Conferir dinheiro que entrou e baixar o que o matcher não fechou |
| 2 | Títulos | Ver o título, a régua que já rodou e as baixas |
| 3 | Conversas, Aprovações | Assumir o WhatsApp e decidir pedido fora da política |
| 4 | Configurações, Métricas | Política, horário, templates; recuperação, DSO, baixa automática |

A conciliação vem primeiro: não fala com o devedor e gera prova de valor para vender a régua.

## 4. Regras de ouro

1. **O LLM não decide dinheiro.** Ele lê comprovante, classifica intenção e conversa. Régua, matching e baixa são código.
2. **O banco é a fonte da verdade da baixa.** Comprovante sozinho nunca quita o título.
3. **A política do tenant é o teto.** O agente só oferece opções que o código já gerou.
4. **Humano é a última instância.** Match incerto, contestação, leitura fraca e pedido fora da política vão para a fila.
5. **Tudo é por tenant.** Nenhum fluxo cruza dados entre clientes da agência.

---

## 5. Regras de cobrança (régua)

A régua é **determinística** e dispara por cron. O agente de IA só entra quando o devedor responde.

### Régua padrão (configurável)

| Momento | Ação | Canal |
| --- | --- | --- |
| D-3 | Lembrete amigável + PIX copia-e-cola | WhatsApp template |
| D0 | Vence hoje | WhatsApp template |
| D+1 | Não identificamos o pagamento + 2ª via | WhatsApp template |
| D+5 | Convite a negociar (sem inventar condição) | WhatsApp template |
| D+15 | Última tentativa automática | WhatsApp + e-mail |
| D+30 | Sai da régua → fila humana | Painel |

### Regras duras

- Nunca envia fora do **horário permitido** do tenant (padrão: 08:00–20:00, seg–sáb).
- Nunca reenvia a mesma etapa no mesmo canal.
- **Opt-out** interrompe a régua na hora; o título continua existindo.
- Devedor em opt-out **é ingerido**, mas **não entra na régua ativa**.
- Promessa ativa **pausa** a régua até `data_prometida + 1`.
- Se o cron atrasar, envia só a **etapa mais recente**, não uma rajada das anteriores.
- Título sem PIX copia-e-cola e sem linha digitável de boleto **não recebe etapa**. O operador vê essa lista separada antes de ativar a conta. Quando o código chega, entra só a etapa vigente.
- Disparo proativo usa **template oficial** (não texto livre do LLM).
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

Todo dinheiro que entra vira um `payment`. O matcher tenta casar com título em aberto e **para no primeiro critério que fecha**.

| Camada | Critério | Resultado |
| --- | --- | --- |
| 1 | `txid` ou E2E igual ao do título | Baixa automática |
| 2 | Valor + documento do pagador + janela de data | Baixa automática |
| 3 | Valor + nome aproximado + data, ou soma de títulos do mesmo devedor | Sugestão com score → humano |
| 4 | Sem candidato | Exceção “não identificado” |

### Proteções de caixa

- **Deduplicação:** o mesmo `e2e_id` ou `file_hash` não baixa duas vezes.
- **Comprovante falso:** origem `comprovante` fica `aguardando_banco`. Só vira baixa definitiva com extrato ou webhook.
- **Diferença de valor:** juros/desconto dentro da regra do tenant aplica; parcial deixa o título `parcialmente_pago`; fora da regra vira exceção.
- Um pagamento pode quitar vários títulos; vários pagamentos podem quitar um título (`matches` N:N).

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
| Cobrança vexatória (CDC art. 42) | Templates revisados; sem ameaça; horário por tenant |
| Pessoa errada | Identidade antes de valores; nunca cobrar em grupo |
| LGPD | Base legal por tenant; RLS; `audit_log`; retenção definida no contrato |
| Banimento do número | Template oficial + rate limit + opt-out imediato |
| Agente inventa condição | Tools só devolvem opções da política |
| Alucinação no comprovante | Validação de E2E, data e valor; baixa confiança → exceção |

Nenhum tenant entra em produção sem política, régua, horário, número WhatsApp e base legal.

## 11. Métricas que o painel mostra

- Taxa de recuperação: valor recebido após o vencimento ÷ valor vencido
- Dias médios de atraso (DSO)
- Promessas cumpridas ÷ feitas
- % de baixa automática (sem humano)
- Exceções abertas e tempo médio de resolução

## 12. Precificação proposta (ainda em aberto)

- Setup único (emissor + importação + régua)
- Mensalidade por faixa de títulos ativos
- Variável sobre valor recuperado de títulos vencidos

Valores de faixa ficam para o piloto, depois de medir custo real por título.
