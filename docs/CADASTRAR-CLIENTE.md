# Como colocar os dados do cliente para o agente disparar

Este guia é para quem vai ligar uma empresa B2B no app. A jornada comercial, da qualificação até a carteira, está em [JORNADA-VENDA-B2B.md](./JORNADA-VENDA-B2B.md). Aqui a conta já existe e a planilha vai entrar: a empresa é cliente nosso, os clientes dela são quem vai receber a cobrança, e cada cobrança vira uma linha. Sem essa linha, o agente não tem o que falar nem para quem falar.

O agente não inventa cobrança. Ele só dispara o que já está cadastrado, no horário combinado, para o celular da pessoa certa.

---

## Quem é quem

Ajuda separar os dois “clientes”, porque os dois entram no sistema de jeitos diferentes.

| Quem | No sistema | Exemplo |
| --- | --- | --- |
| A empresa que contratou a gente | Conta (tenant) | Uma software house que cobra mensalidade de outras empresas |
| O cliente dessa empresa, quem deve | Devedor | A loja que assinou o contrato e ainda não pagou a fatura |
| Cada fatura, boleto ou parcela | Título | Mensalidade de março, NF 1042, parcela 2 de 6 |

Uma loja pode ter várias faturas. No arquivo, isso são várias linhas com o mesmo CNPJ. O sistema junta as linhas na mesma pessoa e cria um título para cada linha.

O disparo vai para os **celulares de WhatsApp do devedor** — até cinco, cadastrados no título. Não vai para um grupo. Cobrança em grupo não acontece.

---

## O que precisa existir antes do primeiro disparo

Marque isso com a empresa antes de importar a planilha. Se faltar um item, o título até entra, mas a mensagem não sai.

1. **Conta da empresa criada e ativa.** Enquanto a conta estiver desligada, a régua ignora os títulos dela.
2. **WhatsApp da empresa conectado.** É o número que envia. A empresa pode ter até cinco. O primeiro da lista dispara; os outros ficam de reserva. Sem a instância, o sistema pula o WhatsApp.
3. **Base legal combinada.** Contrato ou outro fundamento da LGPD. Sem isso a conta não ativa.
4. **Horário de envio.** O padrão é das 8h às 20h, de segunda a sábado. Domingo e madrugada ficam quietos.
5. **Régua.** Etapas, ação e canal estão na tabela **Régua padrão** de [PRODUTO.md](./PRODUTO.md) (§5). A última etapa tira o título da régua automática e o coloca na fila humana do painel.
6. **Celulares de quem paga**, com DDD, até cinco por devedor. Sem telefone, aquele título não recebe WhatsApp. O e-mail só entra na etapa D+15.
7. **PIX copia e cola ou linha digitável do boleto.** Sem um dos dois, o título entra na base e aparece na lista **Sem PIX ou boleto**, mas não recebe etapa da régua. O link sozinho não libera o disparo. Quando o código chega, o título entra só na etapa do dia, sem rajada das anteriores.

Política de negociação, régua e horário já nascem com um padrão sensato na hora de criar a conta. Dá para ajustar depois em **Configurações**. O que a criação **não** preenche sozinha é o WhatsApp e a base legal. Os números de disparo também se cadastram em **Configurações**: até cinco, com a instância da Evolution e o celular. Se um número cair, apague essa linha e cadastre outro. O disparo passa a sair pelo primeiro que restar. Para trocar o que envia sem apagar os demais, use **Usar este** e salve.

---

## Passo 1. Abrir a conta da empresa

Há dois caminhos. Nos dois a conta nasce desligada.

- **A empresa cria sozinha**, em `/comecar` (link **Criar a conta** no login). Ela preenche nome, apelido, e-mail do dono, política, régua, horário, WhatsApp, base legal e o atraso médio de antes da implantação. O dono entra na hora e liga a conta em **Configurações**, quando estiver tudo pronto.
- **A agência cria pela API**, com um usuário de role `agencia`. A agência é a equipe do Settlr que opera as contas, não um intermediário. Use esse caminho quando a empresa preferir que a gente monte a conta antes de entregar o painel. O resto deste passo descreve esse caminho.

Crie a conta com nome, um apelido curto (só letras minúsculas, números e hífen, por exemplo `software-house`) e, se já tiver, o WhatsApp e a base legal.

Exemplo:

```json
{
  "name": "Software House Ltda",
  "slug": "software-house",
  "whatsapp_instance": "nome-da-instancia-na-evolution",
  "whatsapp_number": "5511999990000",
  "legal_basis": "Execução de contrato de prestação de serviço, conforme contrato assinado em 01/03/2026"
}
```

A conta nasce **desligada**. Isso é de propósito: dá tempo de importar a base e conferir antes de qualquer mensagem sair.

Se o WhatsApp ou a base legal ainda não estiverem prontos, complete depois com um ajuste na mesma conta. Para ligar de verdade:

`POST /admin/tenants/{id}/activate`

Na conta que a empresa criou pela tela, quem liga é o dono, em **Configurações** (`POST /settings/activate`). As recusas são as mesmas.

Se ainda faltar política, régua, horário, instância do WhatsApp ou base legal, a ativação recusa e devolve a lista do que falta. Também recusa quando o número não está pareado na Evolution (a sessão precisa estar aberta) ou quando alguma etapa de WhatsApp não tem template oficial aprovado na Meta. Em produção, recusa ainda se o parecer do SETL-15 não estiver em `LEGAL_OPINION_REF`. O nome de cada template fica em **Configurações**, na seção Régua. Os textos dessa versão estão em [TEXTOS-REGUA.md](./TEXTOS-REGUA.md). Não force. Complete e tente de novo.

Crie também o usuário do operador dessa empresa (o financeiro ou o dono que vai olhar o painel). Ele entra com o e-mail dele e o apelido da conta. É esse login que importa a planilha.

---

## Passo 2. Pedir a planilha para o financeiro

Peça um CSV, não um PDF e não uma planilha com várias abas. Uma linha é uma cobrança em aberto. Cabeçalho na primeira linha, exatamente com estes nomes:

`referencia,nome,documento,telefone,email,valor,vencimento,descricao,txid,linha_digitavel,pix_copia_cola,link`

Pode usar vírgula ou ponto e vírgula. O arquivo precisa estar em UTF-8 (o Excel em português costuma salvar melhor como “CSV UTF-8”).

### O que cada coluna significa

| Coluna | Obrigatória | Como preencher |
| --- | --- | --- |
| `referencia` | sim | Um código que não se repete naquela empresa. Número da NF, id do boleto, id do contrato + parcela. Se você reenviar o arquivo, esta coluna é o que evita duplicar. |
| `nome` | sim | Nome de quem deve. Em B2B, a razão social. O primeiro nome da mensagem sai daqui, então “Padaria do João Ltda” vira “Padaria”. |
| `documento` | sim | CNPJ (14 dígitos) ou CPF (11). Pode vir com ponto, barra e traço. O sistema guarda só os números. |
| `telefone` | para o WhatsApp sair | Celular de uma pessoa, com DDD. Ex.: `11988887777`. O sistema coloca o `55` na frente. Se já vier `5511988887777`, também aceita. Telefone fixo não recebe WhatsApp. Dá para cadastrar até cinco: vários números na mesma célula separados por barra vertical, ou as colunas opcionais `telefone2`, `telefone3`, `telefone4` e `telefone5`. O primeiro é o principal. Célula vazia não apaga número que já estava salvo. |
| `email` | só para o aviso de D+15 | E-mail do financeiro. Sem ele, o WhatsApp segue e o e-mail dessa etapa é pulado. |
| `valor` | sim | Maior que zero. `1500,00` ou `1500.00` ou `R$ 1.500,00`. |
| `vencimento` | sim | `15/04/2026` ou `2026-04-15`. É esta data que decide quando a mensagem sai. |
| `descricao` | vale muito a pena | O que a pessoa reconhece. “Mensalidade março — plano suporte”. Aparece no texto. Se ficar vazio, a mensagem fala “título” e a referência. |
| `txid` | quando existir | Identificador do PIX no banco. Ajuda a conciliação a achar o pagamento sozinha. |
| `linha_digitavel` | quando for boleto | Linha digitável. Se não houver link, ela entra no lugar do link na segunda via. |
| `pix_copia_cola` | quando existir | O código PIX inteiro. É o que o cliente cola no banco no lembrete de D-3 e no aviso do dia do vencimento. |
| `link` | quando existir | URL da fatura ou do boleto. Entra na mensagem de segunda via (D+1). |

Não invente coluna com outro nome. `cliente`, `cnpj` ou `whatsapp` são ignoradas. O arquivo precisa usar os nomes da tabela. As únicas colunas a mais que o sistema lê são `telefone2` até `telefone5`.

### Exemplo de um cliente B2B

Uma software house cobrando três faturas. Duas são da mesma loja (mesmo CNPJ, referências diferentes). A terceira é de outra empresa.

```csv
referencia,nome,documento,telefone,email,valor,vencimento,descricao,txid,linha_digitavel,pix_copia_cola,link
NF-1042,Padaria do Joao Ltda,12.345.678/0001-90,11988887777,financeiro@padaria.com.br,"1.500,00",15/04/2026,Mensalidade marco - plano suporte,,,00020126PIXEXEMPLO,https://cobranca.exemplo/nf-1042
NF-1108,Padaria do Joao Ltda,12345678000190,11988887777,financeiro@padaria.com.br,890.00,20/04/2026,Horas extras de implantacao,,,,
NF-1110,Mercado Central ME,98.765.432/0001-10,21977776666,pagar@mercadocentral.com.br,"2.300,50",18/04/2026,Mensalidade marco - plano completo,,,00020126OUTROPIX,https://cobranca.exemplo/nf-1110
```

A Padaria fica com dois títulos e um único cadastro. O Mercado Central é outro devedor. Os dois celulares são de gente do financeiro, não o telefone da recepção.

---

## Passo 3. Importar no painel

1. Entre no painel com o usuário **daquela empresa**. Se entrar na conta errada, a planilha cai no cliente errado.
2. Abra **Títulos**.
3. Clique em **Importar CSV** e escolha o arquivo.
4. Espere o aviso no topo da tela.

O aviso bom é deste tipo: `Importação: 3 criados, 0 atualizados.`

Se uma linha estiver errada, **o arquivo inteiro é recusado**. Nada é gravado. A mensagem aponta a linha (a primeira linha de dados é a linha 2, porque a 1 é o cabeçalho). Corrija e envie de novo.

Erros comuns:

- CNPJ com dígito faltando, ou um documento que não tem 11 nem 14 números.
- Telefone com ramal, com texto (“falar com a Ana”) ou sem DDD.
- Valor zero, vazio ou com letra.
- Vencimento em outro formato, tipo `15-04-26` ou `abril/2026`.
- A mesma `referencia` duas vezes no arquivo, com dados diferentes. A segunda linha pisa na primeira.
- Arquivo que não é CSV de verdade (Excel `.xlsx` renomeado).

---

## Passo 4. Conferir antes de ligar a conta

Ainda em **Títulos**, olhe a lista. Para cada linha que você espera cobrar, confira:

- o nome e o documento de quem deve;
- a referência;
- o valor;
- o vencimento;
- o status **Aberto**.

Abra um título. Os celulares aparecem no topo e no bloco **WhatsApp**, onde dá para incluir ou tirar números (no máximo cinco) e salvar. A lista vale para todos os títulos daquele devedor. A régua manda a mesma mensagem para cada número.

Na mesma tela, a lista **Sem PIX ou boleto** fica separada da carteira. É a conferência de antes de ligar a conta: esses títulos não são cobrados. Se o código chegar depois, por planilha ou pelo emissor, a régua manda só a etapa em que o título está naquele dia.

Se a conta ainda estiver desligada, este é o momento de ativar (passo 1). A partir daí a régua passa a olhar os títulos que já têm PIX ou boleto.

---

## Passo 5. O que o agente faz depois

Ninguém aperta “enviar” título por título. De tempos em tempos o sistema percorre as contas **ativas** e decide sozinho.

Para cada título em aberto ele olha a diferença entre hoje e o vencimento:

| Quando | O que a pessoa recebe |
| --- | --- |
| 3 dias antes | Lembrete com valor, vencimento e PIX |
| No dia | Aviso de que vence hoje, com o PIX |
| 1 dia depois | “Ainda não identificamos o pagamento” e o link ou a linha digitável |
| 3 dias depois | Convite a quitar, sem anunciar desconto |
| 5 dias depois | Convite para responder e combinar, sem inventar desconto |
| 7 dias depois | Novo convite a conversar, com o PIX |
| 10 dias depois | Lembrete de que o título segue em aberto |
| 15 dias depois | Última tentativa automática, no WhatsApp e, se houver e-mail, por e-mail |
| 21 dias depois | Aviso de que a equipe assume o atendimento, sem ameaça |
| 30 dias depois | Para de mandar mensagem e o título aparece na fila humana do painel |

Detalhes que evitam susto:

- **Antes de D-3, não sai nada.** Um vencimento daqui a 20 dias fica quieto até faltarem 3 dias. Isso é o comportamento certo.
- **Se o vencimento já passou**, não sai uma rajada com todas as mensagens atrasadas. Sai só a etapa em que o título está hoje. Uma fatura com 6 dias de atraso recebe o texto de D+5, não o de D-3, D0, D+1 e D+3 juntos.
- **A mesma etapa não repete.** Reimportar a planilha não faz a mensagem ir de novo.
- **Fora do horário, espera.** Se a importação terminou às 21h, o primeiro envio fica para a manhã seguinte, dentro da janela.
- **Quem pediu para parar não é cobrado de novo.** O título continua no sistema, a mensagem não.
- **Promessa de pagamento pausa a régua** até o dia seguinte à data combinada. Se o dinheiro não entrar, a cobrança volta.
- **Título pago, cancelado ou renegociado não é atualizado** numa reimportação e não entra na régua.

Quando o disparo acontece, o título passa de **Aberto** para **Em cobrança**. No detalhe do título aparece o histórico do disparo. Se continuar “Aberto” no dia em que a etapa já deveria ter saído, olhe telefone, horário, conta ativa e se o vencimento realmente já chegou na etapa.

Se a pessoa responder no WhatsApp, aí sim o agente de conversa entra: pede comprovante, anota promessa ou oferece só o parcelamento que a política da empresa permite. A mensagem proativa, a da régua, não é texto livre. Ela segue o modelo da etapa.

---

## Quando a base muda todo mês

Duas formas, e as duas podem conviver.

### Mandar a planilha de novo

Use a **mesma `referencia`** para a fatura que já existe. O sistema atualiza valor, vencimento, PIX e link. Nome novo na mesma referência não troca o devedor; o devedor é reconhecido pelo CNPJ ou CPF.

Referência nova cria título novo. CNPJ que já existe reaproveita a pessoa e só atualiza telefone ou e-mail se a célula vier preenchida. Célula vazia não apaga o telefone que já estava salvo. Um telefone novo na coluna `telefone` vira o principal e tira o principal anterior; os outros números continuam até alguém apagar no título. Se a planilha trouxer `telefone2` em diante, esses números entram na lista, sem passar de cinco.

Não inclua na planilha o que já foi pago se a ideia for “atualizar”. Título pago é ignorado. Manda só o que ainda está em aberto, ou manda tudo e aceite que o pago não muda.

### Ligar o emissor (Asaas)

Se a empresa emite cobrança no Asaas, dá para não depender da planilha no dia a dia.

1. Na conta, informe o provedor `asaas` e a chave da API do Asaas dessa empresa.
2. O sistema devolve um token de webhook. Guarde esse token.
3. No Asaas, aponte o webhook de cobrança para `POST /webhooks/emissor` com esse token.

Quando o Asaas avisa que um pagamento foi criado ou atualizado, o sistema busca o cliente lá (nome, CNPJ, celular, e-mail) e grava ou atualiza o título com valor, vencimento, linha digitável e link. O id do pagamento no Asaas vira a referência. Pagamento confirmado entra na conciliação, não como cobrança nova.

O webhook não é o único caminho. A cada 30 minutos o sistema puxa as cobranças recebidas no Asaas e registra o que ainda não entrou. Sem o webhook, o extrato do emissor ainda fecha o caixa.

Open Finance entra no mesmo ciclo quando a conta tem `bank_feed.open_finance` com `base_url`, `token` e `account_id` (a raiz da API de contas). A planilha de extrato fica para quem não tem nenhum dos dois.

Quando o devedor aceita um acordo, o sistema cria a cobrança dessa parcela no Asaas e grava o PIX ou o boleto antes de confirmar. Sem essa cobrança, o acordo não fica registrado. `issuer_config.billing_type` escolhe `PIX` (padrão) ou `BOLETO`.



---

## Checklist do dia da virada

Use esta lista na implantação. Quando todos os itens estiverem sim, a empresa pode ficar ativa.

- [ ] Conta criada com o apelido certo e o operador consegue entrar no painel dessa conta.
- [ ] Pelo menos um WhatsApp da empresa conectado e testado. Se houver reserva, os outros números estão em Configurações (no máximo cinco) e o que dispara é o primeiro da lista.
- [ ] Base legal registrada.
- [ ] Horário e régua revisados com o cliente (ou o padrão aceito por escrito).
- [ ] Planilha só com cobranças em aberto.
- [ ] Cada linha tem referência única, CNPJ válido, pelo menos um celular com DDD e vencimento. Se houver mais de um WhatsApp, estão na mesma célula separados por `|` ou nas colunas `telefone2` a `telefone5`.
- [ ] PIX ou boleto preenchido nas cobranças que devem entrar na régua. As que ficaram sem código estão na lista separada e não são cobradas até o código chegar.
- [ ] Importação terminou com “criados” e zero erro.
- [ ] Na tela Títulos, um caso real bate com a NF: nome, valor, vencimento e os números de WhatsApp (até cinco).
- [ ] Conta ativada só depois dessa conferência.
- [ ] No primeiro dia útil dentro do horário, o título que já está na janela da régua mudou para **Em cobrança** e o disparo aparece no detalhe.

Se o cliente quiser um piloto, importe só 5 a 10 faturas de pessoas que toparam receber, ative, e acompanhe o primeiro disparo com elas antes de subir a base inteira.
