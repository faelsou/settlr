# Settlr — Análise de Concorrentes

_Atualizado em 07/11/2026_

## 1. Resumo executivo

Ninguém no mercado entrega hoje exatamente a combinação do Settlr para PME, BPO e banco: **régua determinística no WhatsApp + agente de IA que negocia só dentro da política + conciliação em camadas que não baixa título sem confirmação do banco + fila de exceções**. A PME é a primeira onda. BPO e banco entram na mesma oferta e ampliam o mercado. Mas cada peça tem concorrente forte, e dois players novos chegaram muito perto:

- **FinanceiroAI** é o concorrente mais parecido: régua no WhatsApp, IA que lê comprovante e marca **"pago provisório"** até o banco confirmar, plano grátis e assinatura de R$ 99/mês. Ainda está em fila de espera e não mostra negociação estruturada nem matcher em camadas.
- **Negocia.ai** tem bot generativo que negocia desconto e parcelamento, lê comprovante Pix e agrupa dívidas por CPF. Mas é caro (R$ 2.500 a R$ 6.000/mês) e voltado a operações de cobrança, não a PME.
- **Kobana** é a ameaça de médio prazo: gateway com mais de 40 bancos, conciliação, régua com WhatsApp e acordos (Dunning) e um agente de IA de finanças (Kadu). Desde 2024 o foco é grande empresa.
- **Asaas** é a ameaça estrutural: mais de 240 mil clientes PME, régua com WhatsApp a R$ 0,55 por envio e meta de R$ 1 bi de receita em 2026. Se lançar um agente de IA na régua, ocupa boa parte do espaço do Settlr dentro da própria base.

**Onde o Settlr ganha:** independência de banco e gateway (funciona sobre o que o cliente já usa), a regra "comprovante nunca quita", negociação limitada por política com aprovação humana, auditoria completa (`audit_log`) e métricas de recuperação, DSO e baixa automática.

## 2. Mapa do mercado

| Grupo | Quem | O que disputa com o Settlr |
| --- | --- | --- |
| Concorrentes diretos (IA + WhatsApp + baixa) | FinanceiroAI, Negocia.ai, GestãoClick | A proposta inteira, em versões parciais |
| Gateways / plataformas de cobrança | Asaas, iugu, Vindi, Conexa, Cobre Fácil, IRecebi | Régua e baixa automática dentro do próprio ecossistema |
| Infraestrutura bancária + IA | Kobana, Celcoin | Conciliação multi-banco e régua; foco enterprise |
| ERPs com conciliação nativa | Omie, Conta Azul | Fase 1 do Settlr (conciliação) |
| Recuperadoras com agente de IA | Monest (Mia), Belvo, Ligo, Bindflow | Agente negociador; carteira vencida de médias e grandes |
| Camada de WhatsApp | Avisa App, SocialHub, Zenvia, Wati, Jota | Disparo da régua, sem conciliação de verdade |

## 3. Matriz de funcionalidades

Legenda: ✅ tem · ⚠️ parcial ou não confirmado · ❌ não tem / não encontrado.

| Player | Régua WhatsApp | IA conversa / negocia | Lê comprovante | Comprovante não quita sem banco | Independe de gateway | Matcher + fila de exceções | Foco PME |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **Settlr (proposta)** | ✅ | ✅ dentro da política | ✅ | ✅ | ✅ | ✅ 4 camadas | ✅ |
| FinanceiroAI | ✅ | ⚠️ atende, negociação vaga | ✅ | ✅ pago provisório | ⚠️ Asaas, Sicoob, Inter + Pix direto | ❌ | ✅ |
| Negocia.ai | ✅ | ✅ desconto e parcelas | ✅ | ❌ baixa direto | ✅ | ⚠️ fila humana | ❌ |
| GestãoClick | ✅ | ❌ IA só consulta | ❌ | ✅ baixa pelo banco | ⚠️ bancos integrados | ⚠️ sugere matching, aprova em lote | ✅ |
| Kobana | ✅ Dunning | ⚠️ Kadu (agente interno) | ❌ | ✅ | ✅ 40+ bancos | ✅ | ⚠️ foco enterprise |
| Asaas | ✅ | ❌ | ❌ | ✅ (é o próprio banco) | ❌ | ❌ | ✅ |
| Monest | ✅ | ✅ Mia | ⚠️ | ⚠️ | ✅ | ⚠️ | ❌ médias e grandes |
| Omie / Conta Azul | ⚠️ via parceiros | ❌ | ❌ | ✅ | ⚠️ conta própria + bancos integrados | ⚠️ | ✅ |
| Avisa App / SocialHub | ✅ | ⚠️ chatbot genérico | ❌ | ❌ | ❌ depende do gateway | ❌ | ✅ |

## 4. Fichas dos concorrentes

### 4.1 FinanceiroAI — o mais parecido

- **O que é:** plataforma de recebíveis com IA. Notificações no WhatsApp oficial, follow-up com tom crescente, atendimento ao devedor e leitura de comprovante (confere valor, data e origem).
- **Lógica de baixa:** comprovante válido vira **"pago provisório"**. Com Pix direto, o operador confirma com um clique. Com banco integrado, a baixa vem por webhook. É a mesma ideia do `aguardando_banco` do Settlr.
- **Preço:** Free (5 faturas e 20 WhatsApp por ciclo). Assinatura de R$ 99/mês (50 faturas, 150 WhatsApp, módulo financeiro). Excedentes: R$ 0,80 por fatura e R$ 0,25 por WhatsApp. Add-ons de R$ 99/mês cada: banco integrado (por banco), número de WhatsApp próprio e NFS-e.
- **Bancos:** Asaas, Sicoob e Inter; Sicredi, BB e Efí em liberação.
- **Público:** escolas, academias, clínicas, condomínios, contadores, igrejas e SaaS — o mesmo ICP do Settlr.
- **Fraquezas:** acesso por fila de espera; negociação descrita só como "facilitação de condições"; sem matcher em camadas, sem fila de exceções e sem política de desconto ou parcelamento visível.
- **Ameaça:** 🔴 alta no topo do funil (preço baixo e grátis).

### 4.2 Negocia.ai

- **O que é:** bot generativo que negocia desconto e parcelas, lembra promessas e transfere para humano com resumo do caso. Tem console multi-operador, agrupamento de dívidas por CPF, leitura de comprovante Pix com baixa e auditoria por IA de 100% das conversas.
- **Preço:** Essencial R$ 2.500/mês (até 5 mil mensagens, sem bot de IA listado). Profissional R$ 6.000/mês (até 50 mil mensagens, com bot, leitura de Pix e operadores ilimitados). Enterprise sob consulta. A tarifa da Meta é cobrada à parte, direto no CNPJ do cliente.
- **Implantação:** cerca de 14 dias. Sede em Janaúba (MG).
- **Fraquezas para o ICP do Settlr:** preço fora do alcance de PME e baixa direta pelo comprovante, sem esperar o banco (risco de fraude).
- **Ameaça:** 🟡 média; disputa mais as assessorias de cobrança do que PMEs.

### 4.3 Kobana

- **O que é:** gateway bancário com uma API para mais de 40 bancos, mais de 5 milhões de transações/mês e mais de 15 anos de mercado (ex-Boleto Simples).
- **Produtos relevantes:** **Dunning** (cobrança do vencimento ao pagamento por e-mail, SMS e WhatsApp; para o fluxo quando o pagamento entra; acordos, portal do devedor e trilha de auditoria), **Smart Finance** (back office com conciliação bancária), **Kadu** (agente de IA de finanças, "powered by Claude", com aprovação humana) e **Kia** (ambiente de IA para o time financeiro).
- **Foco:** grandes empresas desde 2024. Preço não público.
- **Ameaça:** 🟠 média-alta. É a stack tecnicamente mais próxima. Se descer para PME com um agente que conversa com o devedor, vira concorrente direto. Também pode ser parceira (gateway para as camadas 1 e 2 do matcher).

### 4.4 Asaas

- **Porte:** mais de 240 mil clientes, 3,7 milhões de contas criadas e R$ 165,8 bi movimentados. Receita de R$ 560 mi em 2025, com meta de R$ 1 bi em 2026. Captou US$ 150 mi em 2023 (SoftBank e Bond) e prepara IPO. Fez quatro aquisições (Base ERP, Code Money, Mutuus e outra).
- **Modelo:** não cobra pelo software; ganha cerca de 1% do volume transacionado.
- **Taxas (out/2026):** Pix ou boleto R$ 1,99 (R$ 0,99 nos 3 primeiros meses); cartão 2,99% + R$ 0,49. Parceiros têm tabelas menores.
- **Régua:** WhatsApp R$ 0,55 por notificação; e-mail e SMS R$ 0,99; carta R$ 2,91; robô de voz após o vencimento; negativação Serasa.
- **Limites:** régua só para cobranças emitidas pelo próprio Asaas; sem agente conversacional; não concilia dinheiro que entra em outro banco.
- **Ameaça:** 🔴 estrutural. Ele é dono do canal. Estratégia sugerida: **integrar com o Asaas** (muitos clientes do Settlr vão emitir por lá) e vender o que ele não faz: conversa, negociação, conciliação de dinheiro que entra fora do Asaas e exceções.

### 4.5 Monest (Mia)

- **O que é:** recuperadora de crédito com agente de IA no WhatsApp e por voz (Mia Voz). Oferece SaaS, operação terceirizada e white-label.
- **Números:** mais de 6 milhões de conversas e R$ 500 mi negociados desde 2024; mais de 400 clientes; aporte de R$ 3,2 mi; meta de R$ 20 mi de receita em 2025. Case Jeitto: +470% recuperado no WhatsApp em 6 meses.
- **Foco:** médias e grandes empresas, carteira vencida.
- **Ameaça:** 🟡 média. Não faz régua preventiva nem conciliação; serve de referência de mercado para o agente.

### 4.6 GestãoClick

- **O que é:** ERP para micro e pequenas empresas, com régua de 5 etapas (WhatsApp pelo número oficial deles, e-mail e SMS), link Pix/boleto, área do cliente, carnê e recorrência.
- **Conciliação:** baixa pela confirmação do banco ou pelo retorno CNAB. Por Open Finance ou OFX, sugere o casamento e o operador aprova em lote.
- **IA:** só assistente interno ("quem está atrasado?"); não conversa com o devedor.
- **Ameaça:** 🟡 média para quem quer tudo dentro do ERP.

### 4.7 Conexa

- Cobrança recorrente para serviços (contabilidades, SaaS, agências, coworkings): contratos, NF, régua no WhatsApp e integração bancária. Nota 4,9 com 75 avaliações no B2B Stack. Preço sob consulta. Fundada em 2015.
- **Ameaça:** 🟡 média no segmento B2B de serviços.

### 4.8 Vindi (grupo LWSA/Locaweb)

- Recorrência e pagamentos, comprada pela Locaweb em 2021 por R$ 180 mi (ARR de R$ 35 mi à época). Régua por e-mail, WhatsApp e SMS; Pix Automático. A partir de R$ 1.399/mês.
- **Ameaça:** 🟢 baixa a média; foco em assinatura e e-commerce.

### 4.9 iugu

- Gateway e recorrência. Plano Essencial: Pix 0,99%, boleto R$ 2,19 + R$ 0,40 de processamento, cartão 3,34%. Entrada a partir de R$ 49/mês.
- **Ameaça:** 🟢 baixa; é gateway. Candidata a integração.

### 4.10 IRecebi

- "Financial engagement" omnichannel (WhatsApp, SMS, e-mail, voicebot, RCS). Nasceu em 2023 dentro da Innovare Cobranças. Foco em médias e grandes. A partir de cerca de R$ 209,99.
- **Ameaça:** 🟡 média; régua sofisticada, sem evidência de agente que negocia nem de conciliação.

### 4.11 Celcoin

- Infraestrutura financeira: cobrança multicanal (mais de 50 clientes, como Magalu, C&A e iFood), rede de mais de 100 assessorias, negativação e conciliação automática. Comprou a CobranSaaS (2024) e a Galax Pay. Cerca de 500 fintechs conectadas.
- **Ameaça:** 🟢 baixa para PME; foco em crédito e grandes carteiras.

### 4.12 Omie

- ERP com conta própria (Omie.Cash): boleto a R$ 1,99 liquidado, baixa e conciliação automáticas, integração de extrato com Itaú, Bradesco, Santander e Caixa, OFX para os demais. Plano Multivarejo a partir de R$ 419/mês.
- **Ponto fraco documentado:** a conciliação só olha 5 dias para trás, exige que o tipo de documento bata (boleto pago via Pix não concilia) e prioriza o título de valor exato. O matcher em camadas do Settlr resolve justamente esses casos.
- **Ameaça:** 🟡 média na fase 1.

### 4.13 Conta Azul

- ERP com mais de 100 mil empresas: cobrança automática, contratos recorrentes, bolepix com baixa automática e conciliação. Planos aproximados de R$ 159,90 a R$ 719,90/mês, conforme faturamento. Há relatos de reajustes fortes.
- **Ameaça:** 🟡 média na fase 1; régua no WhatsApp depende de parceiros (Avisa App, SocialHub).

### 4.14 Camada de WhatsApp e assistentes

- **Avisa App:** dispara avisos com integração a Asaas, Conta Azul e OpenPix. Conecta o número da própria empresa por QR Code (não é API oficial, com risco de banimento).
- **SocialHub:** CRM e chatbot no WhatsApp para PME, de R$ 99 a R$ 399/mês, com fluxos de cobrança prontos e integração com Asaas e PagBank.
- **Jota:** conta digital e assistente financeiro dentro do WhatsApp; gera cobrança Pix sem taxa e avisa o recebimento.
- **Ameaça:** 🟢 baixa individualmente, mas definem a expectativa de preço baixo.

### 4.15 Outros no radar

- **Cobre Fácil:** recorrência para prestadores de serviço; cerca de 7 funcionários, pre-seed (2017).
- **Belvo, Ligo, Bindflow, BBTS:** agentes de voz e WhatsApp para bancos, telecom e recuperadoras. Mostram que o modelo funciona (BBTS: +306% de conversões), mas não miram PME.
- **Serasa Experian:** agente de IA no WhatsApp para PMEs, voltado a crédito e venda a prazo. Adjacente; pode avançar para cobrança.

## 5. Comparativo de preços

| Player | Mensalidade | Variável |
| --- | --- | --- |
| FinanceiroAI | R$ 0 (Free) / R$ 99 | R$ 0,80 por fatura excedente; R$ 0,25 por WhatsApp; + R$ 99 por banco |
| Asaas | R$ 0 | Pix ou boleto R$ 1,99; WhatsApp R$ 0,55 por envio |
| iugu | a partir de R$ 49 | Pix 0,99%; boleto R$ 2,59 |
| SocialHub | R$ 99–399 | mensagens Meta |
| IRecebi | a partir de ~R$ 210 | — |
| Conta Azul | ~R$ 160–720 | — |
| Omie | a partir de R$ 419 (Multivarejo) | boleto R$ 1,99 |
| Vindi | a partir de R$ 1.399 | % sobre transações |
| Negocia.ai | R$ 2.500 / R$ 6.000 | mensagens Meta |
| Kobana, Conexa, Monest, Celcoin | sob consulta | — |

**Leitura para a precificação do Settlr:** existem duas âncoras. Embaixo, R$ 0 a R$ 99 (FinanceiroAI, Asaas, SocialHub). Em cima, R$ 2.500+ (Negocia.ai). Uma faixa de **R$ 300 a R$ 1.500/mês por volume de títulos + variável sobre o recuperado** fica no espaço vazio entre as duas, desde que o Settlr prove valor com a conciliação.

## 6. Custos da Meta que afetam todos

- Desde 1º/out/2026 a Meta cobra **mensagens de serviço** (respostas dentro da janela): ~R$ 0,035 por mensagem entregue depois de 1.000 grátis por mês por número.
- Templates de **utilidade** (lembretes de cobrança): ~R$ 0,04–0,05. **Marketing:** até ~R$ 0,38.
- Há uma tarifa de ~R$ 0,33 por mensagem para **chatbots de IA de uso geral** (ChatGPT, Luzia etc.), em discussão no Cade. Pela cobertura disponível, ela mira IA vendida como produto, não o bot de atendimento de uma empresa. **Vale acompanhar**, porque o agente do Settlr conversa em texto livre.
- Consequência: a régua do Settlr deve usar templates de **utilidade** (não marketing), e o agente deve resolver em poucas mensagens.

## 7. Ameaças em ordem

1. **Asaas lançar um agente de IA na régua.** Defesa: integração nativa com o Asaas, conciliação de outras contas por Open Finance ou arquivo, e exceções.
2. **FinanceiroAI sair da fila de espera e escalar barato.** Defesa: negociação por política, matcher em camadas, painel de exceções e métricas que eles não mostram.
3. **Kobana descer para PME** com Dunning + Kadu conversando com o devedor. Defesa: velocidade, foco no segmento e no WhatsApp; considerar parceria.
4. **ERPs (Omie, Conta Azul) colocarem régua no WhatsApp nativa.** Defesa: o Settlr funciona por cima do ERP e do banco que o cliente já tem.
5. **Custo da Meta** comprimindo margem de conversas longas.

## 8. Posicionamento recomendado

- **Para quem:** PME na primeira onda; BPO, com uma conta por empresa e sem cruzar dado; banco, como conta da própria carteira. O banco comprador não é um emissor novo.
- **Frase:** "Cobra pelo WhatsApp, negocia dentro da sua regra e confere cada centavo contra o banco — em cima do banco e do sistema que você já usa."
- **Diferenciais para colocar na página e no pitch:**
  - Comprovante nunca quita sozinho (anti-fraude), com prova no `audit_log`.
  - O agente não inventa condição: só oferece o que a política gerou; o que passar disso vai para aprovação humana.
  - Conciliação em 4 camadas que resolve o que ERP não resolve: Pix pago em boleto, soma de títulos, nome aproximado, pagamento parcial.
  - Métricas de recuperação, DSO, promessas cumpridas e % de baixa automática.
  - Conciliação do Asaas e de qualquer conta pelo Open Finance (cliente genérico da API de contas) ou pelo arquivo do contador. Inter, Efí, iugu e Sicoob ficam no roadmap de emissor.
- **Venda de entrada:** a conciliação (fase 1) como prova de valor, comparada à conciliação de ERP, que só olha 5 dias e exige tipo de documento igual.

## 9. O que ainda falta verificar

- Preços de Kobana (Dunning e Kadu), Conexa, Monest e GestãoClick: pedir demonstração ou cotação.
- Se o FinanceiroAI já negocia parcelamento e como trata contestação.
- Se o Essencial da Negocia.ai inclui IA.
- O enquadramento oficial da tarifa da Meta para agentes de empresas (Cade).
- Taxas atuais do Asaas direto na página oficial (há tabelas de parceiros mais baratas).

## 10. Fontes

- [FinanceiroAI — site e planos](https://financeiro.ai/)
- [Negocia.ai — site e planos](https://negocia.ai/)
- [Kobana — produtos](https://www.kobana.com.br/en/products/) · [Kadu](https://www.kobana.com.br/en/ia/kadu)
- [GestãoClick — cobrança automática](https://gestaoclick.com.br/cobranca-automatica/)
- [Asaas — preços e taxas](https://www.asaas.com/precos-e-taxas) · [Asaas e iugu: tarifas (QUASA, out/2026)](https://quasa.io/pt/media/asaas-ou-iugu-tarifa-publicada-vence-ate-o-volume-pedir-proposta) · [Asaas cobrança recorrente](https://materiais.asaas.com/cobranca-recorrente)
- [Asaas planeja aquisições em 2026](https://blog.asaas.com/release/asaas-planeja-novas-aquisicoes-em-2026/amp/) · [Aquisição da Mutuus](https://legismap.com.br/conteudos/artigos-e-noticias/asaas-estreia-no-mercado-de-seguros-e-anuncia-aquisicao-da-mutuus-seguros) · [Portal Tela](https://www.portaltela.com/noticias/economia/2025/08/19/asaas-levanta-r-100-milhoes-e-projeta-r-1-bilhao-em-receita-ate-2026/) · [Brazil Journal](https://braziljournal.com/asaas-levanta-r-100-milhoes-startup-quer-faturar-r-1-bi-com-solucoes-para-pmes/)
- [Monest — aporte (Startups)](https://startups.com.br/negocios/rodada-de-investimento/exclusivo-monest-levanta-r-32m-com-nestal/) · [Canaltech](https://canaltech.com.br/mercado/ia-ja-renegociou-mais-de-r-500-milhoes-em-dividas-no-brasil/) · [Startupi](https://startupi.com.br/?p=256389) · [Jeitto (Let's Money)](https://www.letsmoney.com.br/noticias/jeitto-monest-ia-cobranca-whatsapp/)
- [Conexa (B2B Stack)](https://www.b2bstack.com.br/product/conexa) · [Vindi vs iugu (B2B Stack)](https://www.b2bstack.com.br/compare/vindi-vs-iugu) · [IRecebi (B2B Stack)](https://www.b2bstack.com.br/product/irecebi) · [Cobre Fácil (Bouncewatch)](https://bouncewatch.com/company/cobre-facil)
- [Vindi — ARR na aquisição (IstoÉ Dinheiro)](https://istoedinheiro.com.br/locaweb-conclui-aquisicao-de-plataforma-de-assinaturas-vindi) · [Vindi Pix Automático](https://www.letsmoney.com.br/noticias/vindi-passa-oferecer-pix-automatico-cobrancas-recorrentes/)
- [Celcoin cobrança multicanal (Finsiders)](https://finsidersbrasil.com.br/?p=322160) · [Celcoin compra CobranSaaS](https://www.baguete.com.br/public/noticias/celcoin-compra-cobransaas)
- [Omie.Cash](https://ajuda.omie.com.br/pt-BR/articles/6365605-o-que-e-a-omie-cash-conta-completa) · [Regras da conciliação Omie](https://ajuda.omie.com.br/pt-BR/articles/6803720-guia-de-configuracoes-para-a-conciliacao-na-omie-cash-conta-completa) · [Planos Omie](https://www.omie.com.br/blog/planos-omie-como-contratar-o-nosso-sistema-de-gestao/)
- [Conta Azul planos](https://contaazul.com/pro/planos/) · [Conta Azul +100 mil empresas](https://contaazul.com/mais/planos/)
- [Avisa App (B2B Stack)](https://www.b2bstack.com.br/product/avisa-app) · [SocialHub](https://www.socialhub.pro/?p=27767) · [Jota](https://blog.jota.ai/cobranca-pix-whatsapp/)
- [Meta: mensagens de serviço desde out/2026](https://diariodocomercio.com.br/negocios/cobranca-whatsapp-business-outubro/) · [Preços da API no Brasil 2026](https://www.messagecentral.com/pt-br/blog/whatsapp-business-api-pricing-brazil) · [Tarifa de chatbots de IA (Tecnoblog)](https://tecnoblog.net/noticias/meta-vai-cobrar-chatbots-de-ia-por-uso-do-whatsapp/) · [Cade (Economic News)](https://economicnewsbrasil.com.br/2026/03/19/cobranca-de-chatbots-no-whatsapp-cade/)
- [BBTS +306% (TI Inside)](https://tiinside.com.br/13/07/2026/bbts-aumenta-conversoes-em-whatsapp-em-306-com-estrutura-de-cobranca-digital-com-ia/) · [Serasa agente para PMEs](https://www.mobiletime.com.br/noticias/20/08/2025/serasa-experian-whatsapp/)
