# Jornada de venda B2B

Como uma PME entra no Settlr, do primeiro contato até a carteira cobrando. Esta jornada é a do piloto. O produto também atende BPO e banco, com a mesma regra de conta, régua e baixa, e com isso abrange o mercado além da PME. A conta nasce desligada. O piloto são 5 a 10 faturas de quem topou receber. O título só quita quando o banco confirma.

O modelo desta jornada é o de 09/11/2026: fase 1 é conciliação em mensalidade fixa, Pix Automático só para pagador pessoa física, e a fatia B2B permanece na régua de PIX copia-e-cola e boleto. As regras estão em [PRODUTO.md](./PRODUTO.md) §5 e §12 e em [CONSELHO.md](./CONSELHO.md). O passo a passo da planilha está em [CADASTRAR-CLIENTE.md](./CADASTRAR-CLIENTE.md). Os fluxos de sistema estão em [FLUXOS.md](../FLUXOS.md).

---

## 1. Quem é quem

| Quem | No sistema | No exemplo |
| --- | --- | --- |
| Settlr | Operador dos dados. A equipe (`agencia`) conduz o piloto. | Quem percorre estas nove etapas |
| Empresa que contrata | Conta. Controladora dos clientes dela. | Software House Ltda |
| Cliente dessa empresa | Devedor. Nunca vê o painel. | Padaria do João Ltda, CNPJ da nota |
| Dono | Política, régua, horário, convite e aprovação. | Sócio que cria a conta |
| Financeiro | Importa a carteira, confirma a baixa e exporta o período. | Quem fecha o caixa |
| Atendente | Fila e conversa. Não confirma baixa. | Quem assume o WhatsApp quando o agente para |
| Contador | Recebe o arquivo do período. É a tese de escala, não o operador do piloto. | Quem pede o CSV |

A venda separa a carteira antes de falar de Pix Automático.

| Carteira | Quem paga | Régua | Pix Automático |
| --- | --- | --- | --- |
| Recorrência de pessoa física: clínica, escola, academia, assinatura | Pessoa física | Copia-e-cola até a adesão. Depois, convite e falha de débito | Cabe, se o CNPJ de quem recebe tem pelo menos seis meses |
| B2B | Pessoa jurídica | PIX copia-e-cola e boleto, de D-3 a D+30 | Fica de fora |
| Condomínio | Condomínio | A mesma régua de copia-e-cola e boleto | Fica de fora |
| Empresa nova | Qualquer pagador | Copia-e-cola e boleto | Fica de fora enquanto o CNPJ tiver menos de seis meses |

No exemplo que percorre as etapas, a Software House cobra a Padaria. Essa fatia é B2B e permanece na régua de copia-e-cola e boleto. A clínica que cobra o aluno é o outro recorte: ali o Pix Automático entra na conversa.

---

## 2. O modelo que a conversa usa

- **Fase 1.** Mensalidade fixa só pela conciliação, com o arquivo do contador. A faixa de teste é R$ 300 a R$ 1.500. O valor fechado sai das conversas em [CONSELHO.md](./CONSELHO.md), pela contagem de quem fecha 60 dias. Setup único (emissor, importação e régua) continua previsto.
- **Recuperação.** A variável sobre o valor recuperado só entra com grupo de controle: 10% dos títulos fora da régua.
- **Quem já tem Pix Automático.** A ordem da venda é (1) conciliação de todo dinheiro que entra, em qualquer banco ou emissor, com o arquivo do contador; (2) a falha de débito tratada por conversa e acordo dentro da política. Dinheiro fora do Asaas faz parte de (1).
- **Quem cobra outra empresa ou um condomínio.** A venda da régua é a de PIX copia-e-cola e boleto. Convite de adesão ao Pix Automático não entra nessa carteira.
- **Distribuição.** O piloto é operado pela equipe do Settlr. A escala se confirma quando o primeiro contador pede o arquivo do período (`GET /payments/export`).
- **WhatsApp de produção.** `WHATSAPP-BUSINESS`, com sessão `open` e template aprovado. A instância lida em 09/11/2026 é `WHATSAPP-BAILEYS`. Com ela, a ativação não passa. Migrar antes do piloto. A trava fica.
- **Custo na Meta.** No piloto, a mesma carteira compara dez etapas com quatro (D0, D+1, D+5, D+15) e mede a recuperação marginal de cada etapa.
- **Dados entre empresas.** Fechados no MVP. Score, antecipação e régua que aprende entre contas ficam de fora ([CONTRATO.md](./CONTRATO.md) §9).

---

## 3. As nove etapas

### 1. Qualificar

Antes do acesso. A venda começa pela carteira, não pelo agente. No piloto, o comprador é uma PME com recorrência ou parcelamento, de 100 a 5.000 cobranças por mês, recebendo em PIX e boleto. BPO e banco entram com a mesma conversa e outra carteira: o BPO traz várias empresas, cada uma numa conta; o banco traz a carteira dele e vira a conta, não um emissor.

**O que falar.** A gente não compra a dívida e não representa a empresa em juízo. Cobra o que ela já vendeu, no WhatsApp da pessoa certa, e só dá baixa quando o banco confirma.

**Pode avançar quando** há um dono, um financeiro e uma carteira real, e o piloto cabe em 5 a 10 faturas de quem topou receber. A carteira já está classificada: Pix Automático, copia-e-cola, ou as duas. A conversa para se a dor for protestar, negativar ou cobrar em grupo.

| Quem | O que acontece | Onde |
| --- | --- | --- |
| Comercial | Confirma volume, canal (PIX, boleto) e se a cobrança é recorrente ou parcelada. | Conversa |
| Comercial | Separa os dois clientes: a empresa que contrata (a conta) e quem ela cobra (o devedor). | Conversa |
| Comercial | Classifica o pagador (pessoa física ou jurídica) e a idade do CNPJ de quem recebe. | Conversa |
| Comercial | Pergunta o emissor. Asaas entra sozinho. Inter, Efí, iugu e Sicoob ficam no roadmap e, até lá, entram por planilha. | Conversa |
| Comercial | Mapeia quem opera: dono configura, financeiro baixa, atendente olha a fila e não baixa. | Conversa |

### 2. Propor

Antes do acesso. A primeira prova de valor é a conciliação: o dinheiro que entrou e a planilha não fechou. A fase 1 cobra só isso, em mensalidade fixa, com o arquivo do contador. A régua e o agente entram em seguida, porque falar com o devedor sem saber o que já foi pago gera cobrança indevida.

Para quem já tem Pix Automático, a proposta segue a ordem da seção 2. Para a Software House que cobra a Padaria, a régua oferecida é a de copia-e-cola e boleto.

**O que falar.** Três peças. A régua lembra sozinha. O agente só fala quando a pessoa responde, e só oferece o que a política já permite. O painel fica com o que o sistema não fecha. Na fase 1, a mensalidade é da conciliação. A parte variável sobre o recuperado espera o grupo de controle.

**Pode avançar quando** o comprador aceita um piloto com escopo escrito: emissor ou planilha, a régua do recorte (Pix Automático ou copia-e-cola) e a fila humana. O valor da mensalidade continua saindo da tabela de conversas. Setup único continua previsto.

| Quem | O que acontece | Onde |
| --- | --- | --- |
| Comercial | Mostra Pagamentos e Exceções com dinheiro que entrou e o matcher não fechou sozinho. | Pagamentos, Exceções |
| Comercial | Mostra um título: histórico da régua, status e baixa. O devedor nunca vê essa tela. | Títulos |
| Comercial | Mostra uma conversa pausada e uma aprovação fora da política. O agente não inventa condição. | Conversas, Aprovações |
| Comercial | Deixa explícito o que a régua de copia-e-cola não diz: desconto, número de parcelas, ameaça, protesto. | Textos da régua |
| Comercial | Se a carteira for de pessoa física elegível, mostra o que muda com o débito quitado: D-3 e D0 saem, e entram convite e falha de débito. | [PRODUTO.md](./PRODUTO.md) §5 |

### 3. Contratar

Antes de produção. A empresa que cobra é a controladora dos dados dos clientes dela. O Settlr é o operador: trata esses dados só para executar o contrato. Sem base legal declarada, a conta não ativa. Em produção, também não ativa sem o parecer registrado.

**O que falar.** Vocês declaram por que podem cobrar esse cliente. A gente cobra dentro do horário, sem grupo, sem ameaça, e para no instante em que a pessoa pede para parar.

**Pode avançar quando** a base legal está escrita (no piloto, execução do contrato com o cliente deles) e o parecer do SETL-15 está em `LEGAL_OPINION_REF`. A minuta sozinha não libera o primeiro cliente. Dados entre empresas permanecem fechados.

| Quem | O que acontece | Onde |
| --- | --- | --- |
| Jurídico | Registra o parecer no SETL-15. O valor da variável é o identificador do ticket, não o texto do parecer. | SETL-15 |
| Dono | Declara a base legal. No piloto: execução do contrato, LGPD art. 7º, V. | `legal_basis` |
| Jurídico | Combina CDC art. 42: sem ridículo, sem vexame, sem contato fora da janela, sem cobrança em grupo. | [CONTRATO.md](./CONTRATO.md) |
| Dono | Aceita o horário padrão, 8h às 20h, de segunda a sábado, ou pede outro antes de ligar. | Configurações |

### 4. Abrir conta

Dia 0. A conta nasce desligada de propósito. Dá tempo de importar, conferir telefone e PIX, e só então deixar a régua olhar os títulos. Política, régua e horário já vêm com o padrão. WhatsApp e base legal a criação não inventa.

**O que falar.** Vocês entram hoje e nenhuma mensagem sai. A conta só liga quando política, régua, horário, número pareado, template e base legal estiverem no lugar.

**Pode avançar quando** o dono entra no painel dessa conta, com o apelido certo. Financeiro e atendente têm convite próprio. A ativação, se tentada agora, devolve a lista do que falta.

| Quem | O que acontece | Onde |
| --- | --- | --- |
| Dono | Cria a conta: nome, apelido (letras minúsculas, número e hífen) e e-mail do dono. | `/comecar` |
| Sistema | Grava a política, a régua e o horário padrão. A conta fica inativa. | Cadastro |
| Dono | Convida financeiro e atendente. Um link por pessoa, sem senha no e-mail, sem login compartilhado. | Convite |
| Agência | No piloto, a equipe do Settlr cria a mesma conta pela API quando a empresa ainda não entra na tela. | `POST /admin/tenants` |

### 5. Configurar

Dia 0. O que for combinado aqui vira o teto. O modelo escolhe entre opções que o código já gerou. Pedido acima do teto pausa o agente e abre aprovação. A régua usa só template oficial da Meta. Texto livre fica na resposta, nunca no disparo.

A régua gravada depende do recorte da seção 1.

- **B2B, condomínio e CNPJ com menos de seis meses.** A tabela **Régua padrão** de [PRODUTO.md](./PRODUTO.md) (§5). Título sem PIX copia-e-cola e sem linha digitável não recebe etapa.
- **Pessoa física com Pix Automático.** Quando o débito quita, D-3 e D0 saem daquele título. Entram convite à adesão (no primeiro título ou no D+1 de quem não aderiu) e débito falhou (no dia em que o débito é recusado). Convite não confirmado não se repete em menos de 30 dias. Essas duas etapas não dependem de copia-e-cola.

No piloto, a mesma carteira compara essa régua de dez etapas com quatro: D0, D+1, D+5 e D+15.

**O que falar.** Desconto e parcela não saem no lembrete. Saem só se a pessoa responder, e só até o teto que vocês gravaram. Oito vezes com teto de seis vai para um humano.

**Pode avançar quando** o cliente aceitou o padrão por escrito ou ajustou os números, o número está pareado em `WHATSAPP-BUSINESS` e cada etapa de WhatsApp tem template aprovado. Instância Baileys não passa desta etapa.

| Quem | O que acontece | Onde |
| --- | --- | --- |
| Dono | Revisa o teto: 10% à vista, entrada mínima de 20%, até 6 parcelas, parcela mínima de R$ 50, intervalo de 30 dias, juros 0%, primeiro vencimento em 3 dias, promessa até 15 dias. | Configurações |
| Dono | Revisa a régua do recorte. Domingo e madrugada ficam quietos. | Configurações |
| Dono | Pareia o número na Evolution em `WHATSAPP-BUSINESS` e grava o nome do template de cada etapa. | Configurações |
| Dono | Cadastra até cinco números. O primeiro dispara. Os outros ficam de reserva, no botão Usar este. | Configurações |

### 6. Carregar

Dia 1. Uma linha é uma cobrança. O mesmo documento vira um devedor com vários títulos. Sem celular com DDD, o WhatsApp não sai. Sem PIX copia-e-cola ou linha digitável, o título da régua de copia-e-cola entra e fica na lista Sem PIX ou boleto, fora dessa régua. O link sozinho não libera o disparo.

**O que falar.** Manda a planilha do que ainda está em aberto, com a referência da nota. A gente confere uma nota real na tela antes de ligar. O piloto são 5 a 10 faturas de quem topou receber.

**Pode avançar quando** a importação termina com criados e zero erro. Um título na tela bate com a nota: nome, documento, valor, vencimento, status Aberto e o celular de quem paga.

| Quem | O que acontece | Onde |
| --- | --- | --- |
| Financeiro | Entrega CSV UTF-8 com o cabeçalho fixo: referência, nome, documento, telefone, e-mail, valor, vencimento, descrição, txid, linha digitável, PIX e link. | Planilha |
| Financeiro | Importa em Títulos, logado na conta certa. Uma linha inválida recusa o arquivo inteiro. | Títulos |
| Financeiro | Ou liga o Asaas: provedor, chave, token de webhook e PIX ou boleto. O id do Asaas vira a referência. | Emissor |
| Sistema | A cada 30 minutos puxa o recebido no emissor e, se configurado, os créditos do Open Finance. OFX e CSV de extrato ficam como exceção. | Extrato |
| Dono | Separa a lista Sem PIX ou boleto. Na régua de copia-e-cola, essas cobranças esperam o código. | Títulos |

### 7. Ativar

Dia 2. A ativação recusa com a lista do que falta: política, régua, horário, número pareado, template de cada etapa, base legal e, em produção, o parecer. Sem template aprovado na Meta, o que é o caso de `WHATSAPP-BAILEYS`, a conta não liga. Ligada a conta, ninguém aperta enviar título por título. No horário, sai só a etapa em que o título está hoje.

**O que falar.** Uma fatura com seis dias de atraso recebe o texto de D+5, não a sequência inteira atrasada. Antes de D-3, o título fica quieto. Na carteira com Pix Automático, título cujo débito quitou não recebe D-3 nem D0.

**Pode avançar quando** no primeiro dia útil, dentro do horário, o título do piloto passou de Aberto para Em cobrança. O evento aparece no detalhe e em Entregas. As pessoas do piloto confirmaram que chegou no celular certo.

| Quem | O que acontece | Onde |
| --- | --- | --- |
| Dono | Ativa a conta. Se faltar peça, completa e tenta de novo. | Ativação |
| Régua | Percorre a conta ativa, pula opt-out, pula título sem código na régua de copia-e-cola e espera a janela de horário. | Worker |
| Devedor | Recebe o template no WhatsApp, em conversa 1:1. Até cinco números, a mesma mensagem. Nunca em grupo. | WhatsApp |
| Dono | Confere entrega, falha e leitura. Falha de entrega libera a mesma etapa de novo, ainda no horário. | Entregas |

### 8. Operar

Semana 1 a 4. A venda vira operação. A régua é código. O modelo lê comprovante, classifica intenção e conversa. Quem decide dinheiro é o matcher, com o extrato como fonte da baixa. Humano entra no incerto, na contestação, na leitura fraca e no pedido fora da política.

**O que falar.** Se a pessoa mandar o comprovante, a gente anota e espera o banco. Comprovante sozinho não quita. Se pedir oito parcelas, a conversa para e cai para vocês. Se pedir para parar, a régua para na hora e o título continua na carteira. Se o débito automático falhar, a conversa trata essa falha dentro da política.

**Pode avançar quando** o financeiro fecha o dia em Pagamentos e Exceções. O atendente assume Conversas e não confirma baixa. O dono vê o aviso de item parado, por e-mail ou pelo WhatsApp interno, nunca no celular de quem está em opt-out.

| Quem | O que acontece | Onde |
| --- | --- | --- |
| Régua | Dispara a etapa do dia. Não repete etapa já entregue. Promessa ativa pausa até o dia seguinte à data. | Worker |
| Devedor | Responde. Antes de qualquer valor, informa os 3 primeiros dígitos do CPF ou do CNPJ. A confirmação vale só naquele dia. | WhatsApp |
| Agente | Oferece à vista ou parcelado dentro do teto. No aceite, emite a parcela no emissor e só então grava o acordo. Sem código, o acordo não fica salvo. | Negociação |
| Caixa | O pagamento entra por extrato, webhook ou comprovante. O comprovante fica aguardando o banco. | Pagamentos |
| Financeiro | Confirma sugestão, diferença e não identificado. A ação grava responsável e `audit_log`. Sem banco, a confirmação volta 409. | Exceções |

| Intenção | O que o produto faz | Quem decide |
| --- | --- | --- |
| Já paguei | Pede o comprovante e manda para a conciliação. Não quita pelo texto. | Código |
| Vou pagar dia X | Data futura, no máximo 15 dias. Pausa a régua até X+1. Só a baixa marca cumprida. | Código |
| Parcelar ou desconto | Mostra só à vista e parcelado dentro da política. Emite PIX ou boleto de cada parcela. | Agente |
| Pedido fora do teto | Pausa o agente e abre aprovação. | Dono |
| Valor errado | Não negocia. Abre contestação. A favor da cobrança volta à régua. A favor do devedor cancela. | Financeiro |
| Parar, hostil ou sensível | Opt-out na hora, ou a conversa vai para um humano. | Código |
| Débito recusado | Etapa débito falhou no mesmo dia. A conversa oferece acordo dentro da política. | Régua e agente |

| Camada | Critério | Resultado |
| --- | --- | --- |
| 1 | `txid` ou E2E igual ao do título | Baixa automática |
| 2 | Valor + documento do pagador + janela (10 dias antes até 60 depois) | Baixa automática |
| 3 | Valor + nome aproximado, ou a soma dos títulos do mesmo devedor | Sugestão para o financeiro |
| 4 | Sem candidato | Exceção: não identificado |

### 9. Expandir

Mês 2. O piloto já recebeu o primeiro disparo. Agora entra o resto da carteira. A referência estável atualiza valor, vencimento e código. Título pago, cancelado ou renegociado não muda numa reimportação e não volta para a régua. Com o Asaas ligado, o webhook cria e atualiza sozinho.

**O que falar.** A fase 1 olha a conciliação: o arquivo do período, o que baixou sozinho e o que ficou na fila. A variável sobre o recuperado não entra nesta conversa. Ela espera o grupo de controle. A escala se confirma quando o contador pede esse arquivo.

**Pode avançar quando** a base inteira está ativa, a lista sem código está zerada ou consciente, e a conversa de renovação usa a taxa de recuperação e o percentual de baixa automática do período. O primeiro CSV pedido pelo contador valida a distribuição.

| Quem | O que acontece | Onde |
| --- | --- | --- |
| Financeiro | Reenvia o CSV com a mesma referência para atualizar. Referência nova cria título. Célula de telefone vazia não apaga o número salvo. | Títulos |
| Sistema | O webhook do Asaas e a varredura de 30 minutos passam a ser o caminho diário. A planilha fica para o emissor que ainda não encaixa. | Emissor |
| Dono | Sobe o restante da carteira só depois de ver o piloto em Entregas e no detalhe do título. | Títulos |
| Comercial | Lê recuperação, DSO contra a linha de base da implantação, promessas cumpridas sobre feitas, baixa automática e tempo médio de exceção. | Métricas |
| Financeiro | Exporta o período para o contador: título, valor, data e E2E (ou txid). Comprovante ainda sem banco fica de fora. | Pagamentos |

---

## 4. Um título B2B, do silêncio até a baixa

É o demo da venda para a fatia em que o pagador é pessoa jurídica, com a Padaria e a NF-1042. A régua é a de PIX copia-e-cola e boleto. Ela não anuncia desconto. Negociação só existe se alguém responder. D+30 tira o título do automático.

A sequência que a pessoa vê, etapa por etapa, é a tabela **Régua padrão** de [PRODUTO.md](./PRODUTO.md) (§5). Quem decide cada etapa é a régua. A saída para a fila humana aparece no painel.

| Momento | O que a pessoa vê | Quem decide |
| --- | --- | --- |
| Antes de D-3 | Título aberto. Nenhuma mensagem. | Código |
| Quando o banco confirma | Título pago. O comprovante sozinho não chega aqui. | Matcher |

Janela de horário padrão: 8h às 20h, segunda a sábado. Fora dela, o envio espera. A mesma etapa não repete. No piloto, metade comparável da carteira pode rodar só D0, D+1, D+5 e D+15, para medir o que cada etapa a mais recupera.

---

## 5. Um título de pessoa física com Pix Automático

É o outro demo, para clínica, escola, academia ou assinatura cujo pagador é pessoa física e cujo CNPJ de quem recebe tem pelo menos seis meses. Condomínio não usa esta trilha.

| Momento | O que muda | Quem decide |
| --- | --- | --- |
| Primeiro título, ou D+1 de quem não aderiu | Convite à adesão. Sem confirmação, o mesmo convite não volta em menos de 30 dias. | Régua |
| Débito quitou | D-3 e D0 saem da régua desse título. | Código |
| Débito recusado | Etapa débito falhou no mesmo dia. A conversa oferece acordo dentro da política. | Régua e agente |
| Dinheiro em outro banco ou emissor | Entra na conciliação do mesmo jeito, com o arquivo do contador. | Matcher |

As etapas de convite e de débito falhou não dependem de PIX copia-e-cola. A trava de “título sem código não recebe etapa” continua valendo para a régua de copia-e-cola e boleto.

---

## 6. Funcionalidades, na etapa em que aparecem

| Funcionalidade | Etapa | Quem usa |
| --- | --- | --- |
| Classificação PF, B2B, condomínio e idade do CNPJ | Qualificar | Comercial |
| Fase 1: mensalidade fixa da conciliação | Propor | Comercial |
| Oferta para quem já tem Pix Automático | Propor | Comercial |
| Onboarding da conta | Abrir conta | Dono, em `/comecar`, ou a agência pela API |
| Papéis e convite sem senha | Abrir conta | Dono, financeiro, atendente |
| Base legal, horário e parecer SETL-15 | Contratar | Dono e jurídico |
| Dados entre empresas fechados | Contratar | Jurídico |
| Política de negociação | Configurar | Dono |
| Régua D-3 a D+30 | Configurar, Ativar, Operar | Devedor B2B, condomínio, ou PF ainda sem adesão |
| Régua curta do piloto (D0, D+1, D+5, D+15) | Configurar | Comercial, na mesma carteira |
| Convite à adesão e débito falhou | Configurar, Operar | Devedor pessoa física elegível |
| Horário e opt-out | Contratar, Operar | Régua |
| WhatsApp Business, sessão aberta e template Meta | Configurar | Dono |
| Números de reserva, até cinco | Configurar | Dono |
| Importação de CSV | Carregar | Financeiro |
| Webhook e varredura do Asaas | Carregar, Expandir | Sistema |
| Open Finance | Carregar | Sistema, a cada 30 min |
| OFX ou CSV de extrato | Carregar | Financeiro, só exceção |
| Lista sem PIX ou boleto | Carregar | Dono, antes de ligar a régua de copia-e-cola |
| Identidade antes do valor | Operar | Devedor, 3 dígitos do CPF ou do CNPJ |
| Promessa de pagamento | Operar | Código, conferida pela baixa |
| Acordo e novas parcelas | Operar | Agente, dentro da política |
| Aprovação fora da política | Operar | Dono |
| Comprovante aguardando banco | Operar | Conciliação |
| Matching em quatro camadas | Operar | Matcher |
| Baixa parcial e diferença | Operar | Financeiro |
| Exportação do período | Expandir | Contador |
| Seis tipos de exceção e D+30 | Operar | Financeiro e atendente |
| Contestação | Operar | Financeiro |
| Conversas assumidas por humano | Operar | Atendente |
| Entregas | Ativar | Dono |
| Aviso de fila parada | Operar | Dono, e-mail ou WhatsApp interno |
| Métricas de recuperação | Expandir | Dono e comercial |
| Auditoria | Operar | Toda ação de estado |
