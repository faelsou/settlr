# Prospecção — 30 dias

_De 23/11/2026 a 22/12/2026. O objetivo é preencher a tabela de [CONSELHO.md](./CONSELHO.md) §2 com conversas reais e sair do "0 de 0" na pergunta 5._

O produto está pronto para o piloto, mas o comercial ainda não começou. Neste mês, 80% do tempo vai para vendas e 20% para código. Do código, só entra o que destrava o piloto (seção 8).

---

## 1. Meta do mês

| Funil | Clínicas | Contadores |
| --- | --- | --- |
| Abordados | 60 | 20 |
| Responderam | 20 | 8 |
| Conversa feita (roteiro do CONSELHO) | 12 | 5 |
| Diagnóstico entregue (seção 3) | 6 | — |
| Proposta enviada | 4 | — |
| **Fechou 60 dias pagando** | **3** | — |
| **Parceiro que indicou ao menos 1 clínica** | — | **2** |

O número que importa é **3 clínicas pagando**. Os números de cima servem para saber em que etapa o funil está travando.

Dezembro esfria a partir do dia 15. As propostas precisam sair até 12/12. Quem só decide em janeiro entra no funil com data marcada, e não conta como perdido.

---

## 2. Para quem (ICP)

Um nicho só neste mês: **clínica com recorrência de pessoa física**. É onde a dor é clara e o Pix Automático cabe ([PRODUTO.md](./PRODUTO.md) §5).

| Critério | Entra | Fica de fora neste mês |
| --- | --- | --- |
| Tipo | Odontologia (ortodontia, implante parcelado), estética, fisioterapia, psicologia, nutrição | Hospital, laboratório, clínica que só atende convênio |
| Volume | 100 a 5.000 cobranças por mês | Menos de 100 |
| Recebimento | PIX e boleto. Asaas ou Inter é ótimo, planilha também serve | Só cartão ou maquininha |
| CNPJ | Ativo há pelo menos seis meses | Mais novo que isso |
| Quem decide | Dono ou sócio que fala com a gente | Rede com compras centralizadas |

**Sinal de dor:** "a secretária confere o PIX no extrato", "tem paciente que diz que pagou e eu não acho", "o contador reclama do fechamento".

BPO, banco, escola, academia e condomínio ficam para depois de 10 clínicas pagando.

---

## 3. A oferta

### Porta de entrada: diagnóstico de conciliação (grátis, 48 h)

A clínica manda o extrato de um mês e a lista do que foi cobrado (planilha ou exportação do Asaas ou Inter). Em 48 horas, devolvemos:

- O total que entrou e não tem dono.
- Os títulos que foram baixados errado ou que ficaram em aberto mesmo pagos.
- As horas que a equipe gastou conferindo, a partir da pergunta 2 do roteiro.

O diagnóstico é feito na Clínica Demo ou numa conta de piloto desligada. Nenhuma mensagem sai para os pacientes. O arquivo recebido fica só nessa conta e é apagado se a clínica não fechar ([CONTRATO.md](./CONTRATO.md)).

### Proposta: fase 1, só conciliação, 60 dias

| Item | Hipótese a testar |
| --- | --- |
| Mensalidade | Começar oferecendo R$ 1.200. Descer até R$ 600 só se o "não" for por preço |
| Setup | R$ 900, abatido se ficar depois dos 60 dias |
| Garantia | Se o primeiro mês não achar pelo menos uma mensalidade em dinheiro sem dono ou horas economizadas, devolvemos o mês |
| O que entrega | Conciliação de todo dinheiro que entra, painel de exceções e o arquivo do contador (`GET /payments/export`) |
| O que não entra | Régua e agente. Eles vêm depois, como upgrade |

Registre o preço testado e a resposta de cada clínica na tabela do CONSELHO. O preço final vem da contagem de quem fecha, não da média do que as clínicas dizem.

---

## 4. Canais

| Canal | Quanto por semana | Observação |
| --- | --- | --- |
| Rede pessoal e indicação | Pedir 5 indicações | "Conhece dono de clínica que cobra parcelado?" Converte mais que qualquer outro canal |
| LinkedIn | 15 convites com nota | Donos e sócios de clínica na sua cidade |
| Instagram e Google Maps | 10 mensagens 1:1 | Lista feita à mão. Uma mensagem por pessoa, nunca em massa |
| Contadores de clínicas | 5 abordagens | É o canal de escala. Oferecer 20% recorrente por clínica indicada enquanto ela pagar |
| Presencial | 1 visita ou evento | Associação regional, coworking de saúde, feira |

Não fazer disparo em massa pelo WhatsApp. É o mesmo risco de banimento e de LGPD que o produto evita.

---

## 5. Semana a semana

### Semana 0 — 21 e 22/11 (preparação)

- [ ] Lista com 80 clínicas e 25 contadores numa planilha de CRM (seção 7).
- [ ] Perfil do LinkedIn: título "Conciliação de PIX e boleto para clínicas".
- [ ] Modelo do diagnóstico: uma página com o total sem dono, a lista de exceções e as horas.
- [ ] Rodar um diagnóstico de ponta a ponta na Clínica Demo e cronometrar.

### Semana 1 — 23 a 29/11 (abrir o funil)

- [ ] 20 clínicas e 5 contadores abordados.
- [ ] 4 conversas feitas com o roteiro do CONSELHO.
- [ ] 1 post sobre a dor (seção 6).
- [ ] Sexta: revisão do funil (seção 7).

### Semana 2 — 30/11 a 06/12 (conversar e diagnosticar)

- [ ] Mais 20 clínicas e 5 contadores abordados.
- [ ] 4 conversas a mais, chegando a 8 no total.
- [ ] 3 diagnósticos entregues.
- [ ] 1 contador em conversa sobre parceria.
- [ ] 2 posts.

### Semana 3 — 07 a 13/12 (propor e fechar)

- [ ] Mais 20 clínicas abordadas.
- [ ] Chegar a 12 conversas e 6 diagnósticos.
- [ ] 4 propostas enviadas até 12/12.
- [ ] Primeira clínica fechada.
- [ ] 2 posts, um deles com o número de um diagnóstico, anonimizado e com autorização.

### Semana 4 — 14 a 20/12 (fechar e implantar)

- [ ] Follow-up de todas as propostas.
- [ ] 3 clínicas fechadas, com contrato e base legal ([JORNADA-VENDA-B2B.md](./JORNADA-VENDA-B2B.md) §3).
- [ ] Primeira importação real ([CADASTRAR-CLIENTE.md](./CADASTRAR-CLIENTE.md)).
- [ ] Quem ficou para janeiro sai com data de retorno na agenda.

### Dias 21 e 22/12 — retrospectiva

Preencher a seção 9 e decidir o mês seguinte.

---

## 6. Roteiros

### Primeira mensagem para a clínica (LinkedIn ou WhatsApp, 1:1)

> Oi, [nome]. Trabalho com conciliação de PIX e boleto para clínicas. Na maioria das que eu vejo, todo mês tem pagamento que entrou e ninguém sabe de qual paciente é. Faço um diagnóstico grátis em 48 h com o extrato de um mês. Você mostra o que é seu dinheiro sem dono. Faz sentido conversar 15 minutos?

### Primeira mensagem para o contador

> Oi, [nome]. Vi que você atende clínicas. O fechamento delas costuma travar no PIX sem identificação, certo? A gente entrega a conciliação pronta e o arquivo do período para o contador. Para quem indica, pagamos 20% recorrente. Topa 15 minutos para eu mostrar o arquivo?

### Follow-up (a mesma lógica da régua)

| Dia | Mensagem |
| --- | --- |
| D0 | Primeira mensagem |
| D+2 | "Consegue ver isso essa semana?" |
| D+5 | Um número concreto: "Na última clínica que analisei, R$ X estavam sem dono" |
| D+10 | "Vou encerrar por aqui. Se fizer sentido depois, é só chamar" |

Depois do D+10, a pessoa sai da cadência. Quem pedir para parar sai na hora.

### Conversa

São as cinco perguntas do [CONSELHO.md](./CONSELHO.md) §2, nessa ordem. Termine sempre pedindo o extrato para o diagnóstico. Sem extrato, o próximo passo não existe.

### Conteúdo (2 posts por semana)

- Quanto uma clínica perde por mês com PIX sem identificação.
- "O paciente diz que pagou": como resolver sem constranger ninguém.
- O que o contador precisa receber da clínica no fechamento.
- Bastidores do diagnóstico, com números anonimizados e autorizados.

---

## 7. CRM e ritmo

Uma planilha basta. Colunas: empresa, tipo, contato, canal, etapa, data do último toque, próximo passo, data do próximo passo, preço testado, motivo da perda.

Etapas: `lista` → `abordado` → `respondeu` → `conversa` → `diagnóstico` → `proposta` → `fechou` / `perdeu` / `janeiro`.

| Bloco diário | Tempo |
| --- | --- |
| Abordagem e follow-up | 1 h 30 (manhã) |
| Conversas e diagnósticos | 2 h |
| Conteúdo | 30 min |
| Código (seção 8) | O que sobrar, no máximo 2 h |

**Revisão semanal (sexta, 30 min):** os números de cada etapa contra a seção 1, onde o funil travou e uma mudança para a semana seguinte. Assunto técnico fica fora dessa reunião.

---

## 8. O que o código pode fazer neste mês

Só entra:

1. Migrar a instância de `WHATSAPP-BAILEYS` para `WHATSAPP-BUSINESS` e aprovar os templates ([TEMPLATES-WHATSAPP-META.md](./TEMPLATES-WHATSAPP-META.md)). Sem isso, a régua não liga para quem fizer o upgrade.
2. O que o diagnóstico precisar para sair em 48 h: importar o extrato e a planilha da clínica e exportar a página do resultado.
3. Bug que um cliente pagante encontrar.

O resto fica congelado até haver 3 clínicas pagando: nova cloud, observabilidade, AIOps, BPO, banco e novos emissores.

---

## 9. Decisão no dia 30

| Resultado | Leitura | Próximo mês |
| --- | --- | --- |
| 3 ou mais pagando | Nicho e oferta validados | Mesmo nicho, meta de 10. Começar a régua como upgrade e o grupo de controle |
| 1 ou 2 pagando | A oferta funciona, o volume está baixo | Dobrar abordagens e apostar no contador |
| 0 pagando, com 12 ou mais conversas | Problema na oferta ou no nicho | Rever o preço e a garantia, ou testar escola ou academia |
| Menos de 8 conversas | Problema no topo do funil | Rever canal e mensagem antes de mexer na oferta |

| Resultado real | Valor |
| --- | --- |
| Abordados | |
| Conversas | |
| Diagnósticos | |
| Propostas | |
| Fechados | |
| Ticket médio | |
| Contadores parceiros | |
| Principal motivo de perda | |
