# Templates WhatsApp (Meta) — onboarding PME e BPO

Versão dos textos: `2026-11-08` ([TEXTOS-REGUA.md](./TEXTOS-REGUA.md)).  
JSON pronto para colar em Configurações / API: [templates-whatsapp-meta.json](./templates-whatsapp-meta.json).

## PME × BPO

A régua é a mesma. **Uma conta por empresa**, com o mesmo conjunto de 9 templates.

| Comprador | O que muda | Templates |
| --- | --- | --- |
| PME | Uma conta, um (ou até cinco) WhatsApp | Estes 9, na WABA desse número |
| BPO | Várias empresas = várias contas | Os **mesmos 9** em cada conta / número da carteira |
| D+30 | Só handoff para a fila humana | Sem template |

Pix Automático (convite à adesão / débito falhou) ainda não está nestes textos canônicos. Enquanto não entrar em [TEXTOS-REGUA.md](./TEXTOS-REGUA.md), não cadastre etapa extra na Meta para o piloto de copia-e-cola.

## O que cadastrar onde

1. **Meta Business / WhatsApp Manager** — criar os 9 templates abaixo (categoria **Utilidade**, idioma `pt_BR`), esperar `APPROVED`.
2. **Settlr → Configurações → Régua** — em cada chave (`lembrete`, `vencimento_hoje`, …) preencher:
   - **Template oficial (nome na Meta)** = `name` da tabela
   - **Idioma** = `pt_BR`
   - **Params** = placeholders na ordem das variáveis `{{1}}`, `{{2}}`, …
3. **Ativar a conta** — a ativação confere sessão `open` e catálogo aprovado. Sem isso, 422.

Instância `WHATSAPP-BAILEYS` não passa. Precisa `WHATSAPP-BUSINESS`.

## Regras ao criar na Meta

- Categoria: **UTILITY** (utilidade / atualização de conta). Não use marketing.
- Idioma: **Portuguese (BR)** → `pt_BR`.
- Corpo com variáveis `{{1}}`, `{{2}}`, … na mesma ordem dos `params` do Settlr.
- Não comece o texto com variável (a Meta recusa).
- Exemplos de amostra (para a análise): nome `Maria`, descrição `Mensalidade novembro`, valor `R$ 350,00`, vencimento `20/11/2026`, PIX `00020126...`, link `https://pay.exemplo.com/abc`.
- Sem ameaça, sem negativação, sem desconto anunciado, sem número de parcelas no disparo.

## Os 9 modelos

### 1. `settlr_lembrete` — etapa D-3 · chave Settlr `lembrete`

| Campo | Valor |
| --- | --- |
| Nome | `settlr_lembrete` |
| Params | `{nome}`, `{descricao}`, `{valor}`, `{vencimento}`, `{pix}` |

**Corpo (Meta):**

```text
Olá, {{1}}! Passando para lembrar que o pagamento de {{2}} no valor de {{3}} vence em {{4}}. PIX copia e cola: {{5}}
```

### 2. `settlr_vencimento_hoje` — etapa D0 · chave `vencimento_hoje`

| Campo | Valor |
| --- | --- |
| Nome | `settlr_vencimento_hoje` |
| Params | `{nome}`, `{descricao}`, `{valor}`, `{pix}` |

**Corpo (Meta):**

```text
Olá, {{1}}. O pagamento de {{2}} ({{3}}) vence hoje. PIX: {{4}}
```

### 3. `settlr_segunda_via` — etapa D+1 · chave `segunda_via`

| Campo | Valor |
| --- | --- |
| Nome | `settlr_segunda_via` |
| Params | `{nome}`, `{descricao}`, `{valor}`, `{vencimento}`, `{link}` |

**Corpo (Meta):**

```text
Olá, {{1}}. Ainda não identificamos o pagamento de {{2}} ({{3}}), vencido em {{4}}. Segue a segunda via: {{5}}. Se já pagou, é só responder com o comprovante.
```

### 4. `settlr_convite_quitar` — etapa D+3 · chave `convite_quitar`

| Campo | Valor |
| --- | --- |
| Nome | `settlr_convite_quitar` |
| Params | `{nome}`, `{descricao}`, `{valor}`, `{vencimento}`, `{pix}` |

**Corpo (Meta):**

```text
Olá, {{1}}. {{2}} ({{3}}) venceu em {{4}}. O PIX para quitar é {{5}}. Se precisar de outra forma, responda esta mensagem.
```

### 5. `settlr_oferta_negociacao` — etapa D+5 · chave `oferta_negociacao`

| Campo | Valor |
| --- | --- |
| Nome | `settlr_oferta_negociacao` |
| Params | `{nome}`, `{descricao}` |

**Corpo (Meta):**

```text
Olá, {{1}}. Sabemos que imprevistos acontecem. Se precisar, podemos combinar uma forma de pagamento para {{2}}. É só responder esta mensagem.
```

### 6. `settlr_convite_conversa` — etapa D+7 · chave `convite_conversa`

| Campo | Valor |
| --- | --- |
| Nome | `settlr_convite_conversa` |
| Params | `{nome}`, `{descricao}`, `{valor}`, `{vencimento}`, `{pix}` |

**Corpo (Meta):**

```text
Olá, {{1}}. {{2}} ({{3}}) segue em aberto desde {{4}}. Se quiser conversar sobre o pagamento, responda esta mensagem. O PIX para quitar é {{5}}.
```

### 7. `settlr_lembrete_aberto` — etapa D+10 · chave `lembrete_aberto`

| Campo | Valor |
| --- | --- |
| Nome | `settlr_lembrete_aberto` |
| Params | `{nome}`, `{descricao}`, `{valor}`, `{vencimento}`, `{pix}` |

**Corpo (Meta):**

```text
Olá, {{1}}. {{2}} ({{3}}) segue em aberto desde {{4}}. O PIX para quitar é {{5}}. Se a forma precisar ser outra, responda esta mensagem.
```

### 8. `settlr_ultima_tentativa` — etapa D+15 · chave `ultima_tentativa`

Também sai por e-mail com o texto livre da régua (não é template Meta no e-mail).

| Campo | Valor |
| --- | --- |
| Nome | `settlr_ultima_tentativa` |
| Params | `{nome}`, `{descricao}`, `{valor}` |

**Corpo (Meta):**

```text
Olá, {{1}}. Esta é nossa última mensagem automática sobre {{2}} ({{3}}). Depois dela, o atendimento passa para nossa equipe.
```

### 9. `settlr_aviso_equipe` — etapa D+21 · chave `aviso_equipe`

| Campo | Valor |
| --- | --- |
| Nome | `settlr_aviso_equipe` |
| Params | `{nome}`, `{descricao}`, `{valor}`, `{vencimento}`, `{pix}` |

**Corpo (Meta):**

```text
Olá, {{1}}. {{2}} ({{3}}) segue em aberto desde {{4}}. Esta mensagem é automática. Depois dela, a equipe assume o atendimento. Quite pelo PIX {{5}} ou responda se quiser conversar.
```

## Checklist rápido do onboarding

- [ ] 9 templates criados na Meta (UTILITY, `pt_BR`)
- [ ] Status `APPROVED` no catálogo da Evolution
- [ ] Nomes e params gravados em Configurações (ou via `PUT` de settings com o JSON)
- [ ] Número pareado (`open`) em `WHATSAPP-BUSINESS`
- [ ] Base legal preenchida
- [ ] Em produção: `LEGAL_OPINION_REF` apontando o SETL-15
- [ ] Conta ativada sem 422

## Piloto enxuto (4 etapas)

Se a carteira do piloto comparar só D0, D+1, D+5 e D+15, ainda assim a Meta precisa dos templates das etapas que estiverem na régua gravada. Com a régua padrão completa, cadastre os nove. Com régua reduzida, cadastre só as chaves presentes em `dunning_rules.steps`.
