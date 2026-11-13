# Conselho — o que falta para responder

_09/11/2026. A pergunta do WhatsApp está respondida. A frase do Pix Automático e as decisões de preço, distribuição, custo e dados entre empresas estão escritas em [PRODUTO.md](./PRODUTO.md) e [CONTRATO.md](./CONTRATO.md). A pergunta da conciliação continua aberta: só fecha com conversa._

O parecer técnico está em [PRODUTO.md](./PRODUTO.md), [TECNICA.md](./TECNICA.md) e [CONCORRENTES.md](./CONCORRENTES.md). Este arquivo é o lado de mercado, plataforma e modelo de negócio.

---

## 1. Veredito

A parte técnica está madura: regras de ouro, LLM fora da decisão de dinheiro, deduplicação e compliance. O risco citado pelo conselho está no mercado, na plataforma e no modelo. Oito pontos, e o estado de cada um depois desta rodada:

| # | Ponto | Estado |
| --- | --- | --- |
| 1 | Pix Automático no lugar de D-3 e D0, com falha de débito na conversa | Decisão escrita em [PRODUTO.md](./PRODUTO.md) §5 |
| 2 | Fosso fora da régua da Asaas: conversa e conciliação com arquivo do contador | A frase de venda está no mesmo parágrafo. Dinheiro fora do Asaas entra na conciliação |
| 3 | Template oficial e sessão `open` ao mesmo tempo | Instância lida: `WHATSAPP-BAILEYS`. Migrar para `WHATSAPP-BUSINESS` antes do piloto. A trava de ativação fica |
| 4 | Preço variável na fase que não recupera valor | Fase 1 é mensalidade fixa só pela conciliação. Variável só com grupo de controle |
| 5 | Nenhum cliente citado | Roteiro de 5 a 8 conversas abaixo. A tabela ainda está vazia |
| 6 | Papel `agencia` como serviço | Piloto operado pela equipe. Escala pelo contador, validada quando o primeiro pedir o CSV |
| 7 | Custo do template acima do LLM | No piloto, comparar dez etapas com quatro (D0, D+1, D+5, D+15) |
| 8 | Regra de não cruzar empresas fecha o ativo de longo prazo | Fechado no MVP. Reabrir só com base legal e anonimização no contrato ([CONTRATO.md](./CONTRATO.md) §9) |

---

## 2. Pergunta 1 — Quem pagaria só pela conciliação, e quanto?

**Resposta hoje:** zero empresas pagando. O número não se inventa. A métrica da rodada é quantas pessoas disseram sim na pergunta 5 do roteiro, não a média do que responderam na pergunta 4.

### Roteiro

Cinco a oito conversas, com clínica, escola e academia. As cinco perguntas, nesta ordem:

1. Como vocês conferem hoje o PIX que entrou contra o que foi cobrado? Quem faz isso?
2. Quantas horas por mês isso toma? O contador cobra à parte por isso?
3. No último mês, quanto dinheiro ficou sem dono ou foi baixado errado?
4. Se isso saísse pronto, com o arquivo para o contador, quanto valeria por mês? A pessoa diz o número primeiro.
5. Fechamos por R$ X por mês, só conciliação, por 60 dias? O X testado fica na faixa de R$ 300 a R$ 1.500 de [CONCORRENTES.md](./CONCORRENTES.md) §5.

| Empresa | Tipo | Horas/mês | Sem dono no mês | Quanto disse (pergunta 4) | R$ testado | Fechou 60 dias? | Data |
| --- | --- | --- | --- | --- | --- | --- | --- |
| | | | | | | | |
| | | | | | | | |
| | | | | | | | |
| | | | | | | | |
| | | | | | | | |

Sim na pergunta 5: 0 de 0.

---

## 3. Pergunta 2 — O que o Settlr faz com o Pix Automático ligado

**Resposta:** escrita em [PRODUTO.md](./PRODUTO.md) §5. Resumo para a reunião.

Quando o débito automático quita, D-3 e D0 saem da régua daquele título. Entram duas etapas: convite à adesão (no primeiro título ou no D+1 de quem não aderiu) e débito falhou (no dia em que o débito é recusado).

Para quem já tem Pix Automático, a venda é, nesta ordem:

1. Conciliação de todo dinheiro que entra, em qualquer banco ou emissor, com o arquivo do contador.
2. Falha de débito tratada por conversa e acordo dentro da política.

Dinheiro que entrou fora do Asaas faz parte de (1).

Recorte que muda o público dessa régua nova:

- O pagador do Pix Automático é pessoa física. O recebedor é pessoa jurídica com CNPJ ativo há pelo menos seis meses (Resolução BCB nº 482). Empresa nova fica de fora no início.
- Título com pagador pessoa jurídica (a fatia B2B) e a carteira de condomínios permanecem na régua de PIX copia-e-cola e boleto.
- Convite de adesão que o pagador não confirmou não se repete em menos de 30 dias. O Banco Central trata o reenvio idêntico nesse prazo como excesso.

Fontes: [Agência Brasil, 13/10/2025](https://agenciabrasil.ebc.com.br/economia/noticia/2025-10/pix-automatico-torna-se-obrigatorio-partir-desta-segunda) (pagador pessoa física; CNPJ com mais de seis meses) e a Resolução BCB nº 482, de 5/6/2025, no art. 11-T do regulamento do Pix.

---

## 4. Pergunta 3 — Cloud API oficial ou Baileys?

**Resposta:** `WHATSAPP-BAILEYS`. A instância `Cobranca` em `https://apiwp.aiagentautomate.com.br` estava com `connectionStatus: open` na leitura de 09/11/2026.

```bash
curl -s https://apiwp.aiagentautomate.com.br/instance/fetchInstances \
  -H "apikey: $EVOLUTION_API_KEY" \
  | jq '.[] | {name, integration, connectionStatus}'
```

| Campo | Valor lido |
| --- | --- |
| Deploy | Evolution em `apiwp.aiagentautomate.com.br` |
| `name` | `Cobranca` |
| `integration` | `WHATSAPP-BAILEYS` |
| `connectionStatus` | `open` |
| Data | 09/11/2026 |

A ativação exige ao mesmo tempo `connectionState == open` e template `approved` em `/template/find` (`api/app/dunning/official.py`). Uma instância Baileys não tem template na Meta, então essa trava nunca passa nela. Com Baileys no ar, nenhuma conta consegue ativar em produção. Isso combina com o fato de só existir a Clínica Demo.

**Decisão:** migrar para `WHATSAPP-BUSINESS` antes do piloto. Afrouxar a trava não é opção.

---

## 5. Decisões, uma linha cada

- **Preço da fase 1:** mensalidade fixa só pela conciliação. A variável sobre o recuperado fica para quando houver grupo de controle (10% dos títulos fora da régua). Valor numérico: tabela da seção 2.
- **Distribuição:** o piloto é operado pela equipe (`agencia`). A tese de escala é o contador, e quem valida é o primeiro contador que pedir o CSV.
- **Custo na Meta:** comparar dez etapas contra quatro (D0, D+1, D+5, D+15) no piloto, medindo a recuperação marginal de cada etapa.
- **Dados entre empresas:** fechado no MVP. Reabrir só com base legal e anonimização de dados agregados escritas no contrato. A frase está em [CONTRATO.md](./CONTRATO.md) §9.

---

## 6. O que levar para a próxima reunião

- [x] Campo `integration` da instância: `WHATSAPP-BAILEYS`. Decisão de migrar para `WHATSAPP-BUSINESS` antes do piloto, sem afrouxar a trava.
- [x] Frase do Pix Automático em [PRODUTO.md](./PRODUTO.md) §5, com o recorte de pessoa física, seis meses, B2B e condomínio.
- [x] Preço da fase 1, distribuição, comparação de etapas e dados entre empresas escritos.
- [ ] Tabela da seção 2 com 5 a 8 conversas, e a contagem de sim na pergunta 5.
- [x] Jornada de venda no modelo desta rodada, em [JORNADA-VENDA-B2B.md](./JORNADA-VENDA-B2B.md).
