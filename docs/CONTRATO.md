# Minuta — contrato de prestação de serviço

Minuta para o parecer do [SETL-15](https://rafadsouz.atlassian.net/browse/SETL-15). Não é parecer jurídico, não está assinada e não autoriza ativar o primeiro cliente. O advogado confirma o recorte de CDC e LGPD e o registro fica no ticket. Produção só ativa a conta com `LEGAL_OPINION_REF` apontando esse registro.

## 1. Partes

- **Contratante:** a empresa que cobra os próprios clientes. É a controladora dos dados desses clientes.
- **Contratada:** o Settlr. É a operadora. Trata os dados só para executar este contrato e segundo as instruções da contratante.

## 2. Objeto

Cobrança amigável dos títulos que a contratante carregar, por WhatsApp e e-mail, dentro da régua e do horário configurados, com conciliação de pagamentos e painel para a equipe da contratante.

A contratada não compra a dívida, não representa a contratante em juízo e não decide base legal no lugar dela.

## 3. Base legal

A contratante declara, antes de ativar a conta, a base legal do tratamento dos dados de quem deve. No piloto a base prevista é a execução do contrato entre a contratante e o seu cliente (LGPD art. 7º, V), informada no campo `legal_basis`.

A contratada trata esses dados como operadora, nas instruções deste contrato (LGPD art. 39). Sem `legal_basis` preenchida, a conta não ativa.

## 4. Dados tratados

Nome, documento, telefone, e-mail, descrição e valor do título, vencimento, identificadores de PIX ou boleto, mensagens da régua e da resposta, comprovantes e a trilha de auditoria de quem fez o quê.

A mensagem proativa não vai para grupo. A resposta só informa valor depois de confirmar a identidade. Pedido de parar interrompe a régua na hora.

## 5. Retenção

Prazo proposto, para o parecer confirmar:

- Mensagens, eventos da régua, trilha de auditoria e comprovantes ficam guardados por 5 anos depois da baixa, do cancelamento ou da renegociação do título. A referência é o prazo de prescrição da cobrança de dívida líquida (Código Civil art. 206, §5º, I).
- Conta encerrada usa o mesmo prazo, contado do encerramento, para o que ainda não tiver prazo próprio.
- No fim do prazo, a contratada exclui ou anonimiza. Guarda maior só se a contratante apontar, por escrito, obrigação legal que exija.

## 6. Cobrança (CDC)

A cobrança segue o art. 42 do CDC: não expõe a pessoa a ridículo e não é vexatória.

- Sem ameaça, sem menção a restrição de crédito, protesto ou negativação.
- Sem contato fora do horário da conta. O padrão é 08:00–20:00, de segunda a sábado.
- Sem cobrança em grupo.
- O disparo proativo usa só o texto da versão em [TEXTOS-REGUA.md](./TEXTOS-REGUA.md). Esse texto não anuncia desconto, número de parcelas nem entrada.
- Desconto e parcelamento, quando existem, nascem na resposta e só dentro da política que a contratante configurou.

## 7. Suboperadores

A contratada usa, para executar o objeto, o provedor do WhatsApp (Evolution e Meta), o armazenamento dos comprovantes e, na resposta, um modelo de linguagem. A contratada responde pelo tratamento feito por esses suboperadores nos limites deste contrato.

## 8. Ativação do primeiro cliente

O primeiro cliente em produção não é ativado sem o parecer registrado no SETL-15. A ativação recusa com `parecer jurídico (SETL-15)` enquanto `LEGAL_OPINION_REF` estiver vazio. O valor dessa variável é o identificador do registro no ticket, não um substituto do parecer.

## 9. Fora desta minuta

Preço, faixa e variável sobre valor recuperado ficam para outra decisão. Esta minuta não vale como contrato assinado.
