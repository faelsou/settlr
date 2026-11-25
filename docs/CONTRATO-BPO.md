# Minuta — contrato BPO (plataforma + LGPD)

Minuta para o parecer do [SETL-55](https://rafadsouz.atlassian.net/browse/SETL-55) (recorte BPO do [SETL-35](https://rafadsouz.atlassian.net/browse/SETL-35)). Complementa [CONTRATO.md](./CONTRATO.md). **Não é parecer jurídico, não está assinada e não autoriza vender nem ativar carteira de BPO em produção.**

Versão proposta: `2026-11-14`. O advogado confirma a cadeia controlador → operador → suboperador, o CDC e o preço; o registro do parecer fica no SETL-55 (e, se houver parecer separado dos textos da régua, no SETL-15).

---

## Decisões propostas (SETL-55)

| Pergunta | Proposta desta minuta | Motivo |
| --- | --- | --- |
| Cadeia LGPD | Empresa da carteira = **controladora**; BPO = **operador**; Kitou = **suboperador** | O BPO opera em nome da empresa; a Kitou só executa a plataforma sob instrução do BPO e do contrato |
| Login da empresa | Opcional: a empresa **pode** ter `dono`; o BPO opera com `bpo_admin` / `bpo_operador` | Não bloqueia a operação; permite auditoria e saída limpa se o BPO sair |
| Preço | Mensalidade da **organização** + valor por **empresa ativa** | Alinha com carteira (BPO) e com custo por tenant (infra, WhatsApp, LLM) |
| WhatsApp compartilhado | **Mantém a trava**: uma instância por empresa | Evita cobrança no número errado e vazamento entre controladoras; `_ensure_unique_instances` permanece |
| Modelo de venda (SETL-35) | **Venda direta ao BPO** (parceiro operacional, não revenda white-label nesta versão) | A Kitou contrata com o BPO; cada empresa adere por termo/mandato. Revenda white-label fica fora |

Corrigir qualquer linha acima antes do parecer. Sem essa confirmação, SETL-55 não fecha.

---

## Parte A — Contrato de prestação (Kitou ↔ BPO)

### A1. Partes

- **Contratante:** o BPO (razão social, CNPJ). Opera cobrança e conciliação em nome das empresas da carteira.
- **Contratada:** a Kitou. Disponibiliza a plataforma (régua, agente, painel, conciliação) e trata dados como **suboperador**, nos limites desta minuta e do Anexo B.

### A2. Objeto

Disponibilizar a plataforma Kitou para o BPO operar **várias empresas**, cada uma em uma conta (`tenant`) agrupada numa organização (`organization`), sem cruzar dados entre empresas nem entre organizações.

Inclui: régua por WhatsApp/e-mail, agente de resposta dentro da política de cada empresa, conciliação, fila de exceções e painel multiempresa.

Não inclui: compra de dívida, representação em juízo, negativação, protesto, decisão de base legal no lugar da controladora, nem cruzamento de carteiras.

### A3. Organização e contas

- O BPO recebe uma **organização**. Cada empresa da carteira é um **tenant** com `organization_id` dessa organização.
- Dado de um tenant não entra em outro (RLS, `audit_log`, sem score cruzado — ver [CONTRATO.md](./CONTRATO.md) §9).
- Papéis do BPO: `bpo_admin` (cria/ativa empresas, convida operadores, política quando autorizado) e `bpo_operador` (fila e conversa; **não** confirma baixa — espelha o atendente, salvo anexo comercial em contrário).
- A equipe interna da Kitou continua com role `agencia` (não é o BPO).

### A4. Onboarding de cada empresa

Antes de ativar um tenant da carteira:

1. Termo de adesão / mandato da empresa (Parte C) assinado ou aceito.
2. `legal_basis` preenchida na conta (controladora declara o fundamento).
3. Política, régua, horário e WhatsApp **próprio** daquela empresa configurados.
4. Templates oficiais da Meta aprovados e mapeados ([TEMPLATES-WHATSAPP-META.md](./TEMPLATES-WHATSAPP-META.md)).
5. Em produção: parecer(es) referenciados (`LEGAL_OPINION_REF` / registro SETL-55).

Sem isso, a ativação recusa (mesmo mecanismo da PME).

### A5. WhatsApp

- Cada empresa usa **número e instância próprios**. A mesma instância Evolution não pode estar em dois tenants.
- Disparo só com template aprovado, horário da conta, conversa 1:1, opt-out imediato.
- Textos proativos: versão em [TEXTOS-REGUA.md](./TEXTOS-REGUA.md).

### A6. Preço (proposta comercial)

Estrutura sugerida — valores numéricos ficam para a tabela comercial / conversas; esta cláusula só fixa a **forma**:

| Componente | O que cobre |
| --- | --- |
| Setup da organização | Integração inicial, treino, primeira empresa |
| Mensalidade da organização | Painel multiempresa, suporte ao BPO |
| Mensalidade por empresa ativa | Infra, WhatsApp e LLM daquela conta |
| Setup por empresa (opcional) | Importação e régua daquela carteira |

Fase 1 do produto (conciliação em mensalidade fixa) aplica-se por empresa, salvo acordo escrito de pacote. Variável sobre recuperado só com grupo de controle, como em [CONSELHO.md](./CONSELHO.md).

### A7. Obrigações do BPO

- Obter e manter mandato/adesão de cada empresa controladora.
- Declarar e manter `legal_basis` verdadeira por tenant.
- Não usar a plataforma para cobrança vexatória (CDC art. 42).
- Não solicitar nem tentar cruzar dados entre empresas.
- Respeitar opt-out e horário.
- Informar a Kitou de incidente, contestação judicial ou pedido de titular que afete o tratamento.

### A8. Obrigações da Kitou

- Isolar tenants e organizações.
- Tratar dados só para executar o objeto e as instruções documentadas.
- Manter `audit_log` e retenção do Anexo B.
- Suboperadores técnicos: Meta/Evolution, armazenamento de comprovantes, modelo de linguagem — com a mesma responsabilidade de [CONTRATO.md](./CONTRATO.md) §7, no papel de suboperador.

### A9. Saída e portabilidade

- Encerrada a empresa na carteira: exportação dos dados do tenant (títulos, pagamentos, mensagens conforme retenção) e exclusão/anonimização no fim do prazo.
- Encerrada a organização: o mesmo, empresa a empresa.
- Login opcional de `dono` da empresa facilita a transição se o BPO deixar de operar aquela controladora.

### A10. Fora desta minuta

Valores em reais, SLA com crédito, célula dedicada, white-label e revenda com marca do parceiro. Esta minuta não vale como contrato assinado.

---

## Parte B — Anexo de tratamento de dados (DPA)

### B1. Papéis (LGPD)

| Papel | Quem | Base |
| --- | --- | --- |
| Controladora | Cada empresa da carteira (titular da relação com o devedor) | Decide a finalidade; declara `legal_basis` |
| Operador | O BPO | Trata sob instrução da controladora (mandato + este contrato) |
| Suboperador | A Kitou | Trata sob instrução do BPO e desta minuta (LGPD art. 39 e encadeamento de operadores) |

A Kitou **não** decide base legal. Sem `legal_basis` no tenant, a conta não ativa.

### B2. Base legal típica no piloto

Execução de contrato entre a empresa e o seu cliente (LGPD art. 7º, V), informada em `legal_basis`. Outro fundamento só com texto escrito pela controladora e revisão jurídica.

### B3. Categorias de dados

As mesmas de [CONTRATO.md](./CONTRATO.md) §4: identificação e contato do devedor, título, PIX/boleto, mensagens, comprovantes, auditoria de quem operou (incluindo usuário do BPO).

### B4. Finalidade

Cobrança amigável e conciliação dos títulos carregados pela controladora (via BPO), no horário e na política da conta.

### B5. Retenção

Igual a [CONTRATO.md](./CONTRATO.md) §5 (proposta: 5 anos após baixa/cancelamento/renegociação ou encerramento, alinhado ao CC art. 206, §5º, I), salvo prazo diferente escrito pela controladora.

### B6. Isolamento

- Sem mistura de dados entre tenants.
- Sem score, antecipação ou régua aprendida entre empresas no MVP.
- Operador do BPO só acessa tenants da própria organização; tentativa fora da carteira deve falhar (403).

### B7. Direitos do titular e incidentes

Pedidos do titular (acesso, correção, eliminação, oposição) entram pela controladora ou pelo BPO e são executados no tenant correto. Incidente de segurança: BPO e Kitou se avisam sem demora injustificada; a controladora é informada pelo BPO quando a lei exigir.

### B8. Suboperadores técnicos da Kitou

Meta/Evolution (WhatsApp), storage de comprovantes, provedor de LLM/áudio. Lista atualizada sob pedido. Troca que aumente risco exige aviso prévio razoável ao BPO.

---

## Parte C — Termo de adesão / mandato (Empresa → BPO)

Texto curto para a **empresa controladora** autorizar o BPO a operar a conta dela na Kitou. Anexar ao contrato do BPO com a empresa ou coletar no onboarding.

### C1. Identificação

- Empresa controladora: \[razão social, CNPJ\]
- BPO operador: \[razão social, CNPJ\]
- Conta Kitou (apelido/`slug`): \[ \]

### C2. Mandato

A empresa nomeia o BPO como **operador** para, em seu nome:

- configurar política, régua, horário e WhatsApp da conta;
- importar títulos e tratar a fila de exceções;
- operar cobrança amigável e conciliação via plataforma Kitou.

A empresa permanece **controladora** dos dados dos seus clientes/devedores e declara a base legal em `legal_basis`.

### C3. Kitou

A empresa reconhece que a Kitou atua como **suboperador** técnico da plataforma, sem comprar dívida e sem representar a empresa em juízo.

### C4. WhatsApp e CDC

A empresa autoriza disparos no número configurado para esta conta, só com templates aprovados, sem grupo, sem ameaça, no horário combinado. Opt-out do destinatário deve ser respeitado.

### C5. Login próprio (opcional)

A empresa \[ \] deseja / \[ \] não deseja um usuário `dono` no painel desta conta.

### C6. Vigência

Até revogação escrita pela empresa, encerramento da conta ou fim do contrato entre empresa e BPO. Revogação não apaga de imediato os dados sujeitos à retenção do Anexo B.

### C7. Aceite

Local, data, nome e assinatura (ou aceite eletrônico registrado) do representante da empresa e do BPO.

---

## Checklist para o jurídico (SETL-55)

- [ ] Confirmar cadeia controladora → BPO operador → Kitou suboperador
- [ ] Confirmar que venda direta ao BPO (sem white-label) basta nesta versão
- [ ] Validar retenção de 5 anos e CDC art. 42 nos textos da régua (SETL-15)
- [ ] Validar preço por organização + por empresa (só a forma; valores à parte)
- [ ] Confirmar manutenção da trava de WhatsApp (1 instância / empresa)
- [ ] Registrar parecer e apontar identificador no ticket SETL-55
- [ ] Atualizar `LEGAL_OPINION_REF` / processo de ativação se o parecer BPO for condição aparte do SETL-15

## Relação com a PME

A minuta [CONTRATO.md](./CONTRATO.md) continua valendo para **venda direta à PME** (empresa = controladora, Kitou = operador). Esta minuta BPO **não substitui** a da PME; aplica-se quando o comprador é o BPO com carteira multiempresa.
