# Plano: BPO opera a carteira de várias empresas

Tarefas no Jira, épico [SETL-54](https://rafadsouz.atlassian.net/browse/SETL-54). Este arquivo guarda as decisões, os riscos e a ordem; o detalhe de cada tarefa está no ticket.

## Visão geral

Hoje um login vale para uma empresa (`app_metadata.tenant_id` no JWT), o painel não troca de empresa e o papel `agencia` é da equipe do Settlr, sem limite de carteira. O BPO precisa de um login que opere várias empresas, sem que uma carteira enxergue a outra.

## Decisões de arquitetura

- Uma `organization` agrupa as empresas do BPO. `tenants.organization_id` é nulável: empresa sem organização segue como hoje.
- A empresa é escolhida a cada requisição pelo header `X-Tenant-Id`, validado contra a organização do token.
- A transação continua escopada a um tenant pelo RLS. Visões consolidadas abrem um `tenant_session` por empresa; nenhuma role contorna o RLS.
- `require_agency` fica só para a equipe do Settlr. O BPO ganha papéis próprios (`bpo_admin`, `bpo_operador`).

## Ordem das tarefas

### Fase 1: Decisão e base
- [ ] [SETL-55](https://rafadsouz.atlassian.net/browse/SETL-55) Contrato, LGPD e preço do BPO (depende de [SETL-35](https://rafadsouz.atlassian.net/browse/SETL-35))
- [ ] [SETL-56](https://rafadsouz.atlassian.net/browse/SETL-56) Organização agrupa as empresas
- [ ] [SETL-57](https://rafadsouz.atlassian.net/browse/SETL-57) Escopo por requisição dentro da carteira

### Checkpoint: isolamento
- [ ] Testes HTTP provam 403 entre carteiras; `pytest` verde

### Fase 2: BPO opera de ponta a ponta
- [ ] [SETL-58](https://rafadsouz.atlassian.net/browse/SETL-58) Painel troca de empresa sem novo login
- [ ] [SETL-60](https://rafadsouz.atlassian.net/browse/SETL-60) Convite de operadores do BPO
- [ ] [SETL-59](https://rafadsouz.atlassian.net/browse/SETL-59) Admin do BPO cria e ativa empresas da carteira

### Checkpoint: operação
- [ ] Operador do BPO Demo entra, troca entre as duas empresas e resolve uma exceção em cada

### Fase 3: Escala da carteira
- [ ] [SETL-61](https://rafadsouz.atlassian.net/browse/SETL-61) Fila de exceções consolidada
- [ ] [SETL-62](https://rafadsouz.atlassian.net/browse/SETL-62) Aviso da fila humana chega ao BPO
- [ ] [SETL-63](https://rafadsouz.atlassian.net/browse/SETL-63) Métricas das empresas lado a lado

### Checkpoint: completo
- [ ] Critérios de aceite do SETL-54 atendidos

## Riscos

| Risco | Impacto | Mitigação |
| --- | --- | --- |
| Carteira de um BPO vaza para outro | Alto | SETL-57 primeiro, com teste HTTP de 403 antes de qualquer tela |
| Visão consolidada vira sessão multiempresa | Alto | Um `tenant_session` por empresa; teste de que empresa fora da organização não aparece |
| BPO quer um número de WhatsApp para várias empresas, e `_ensure_unique_instances` proíbe | Médio | Decidir em SETL-55 antes de SETL-59 |
| Papel do BPO na LGPD indefinido | Alto | SETL-55 bloqueia a venda, não o código das fases 1 e 2 |

## Perguntas em aberto

Propostas em [docs/CONTRATO-BPO.md](../docs/CONTRATO-BPO.md) (aguardam parecer SETL-55):

- A empresa cliente do BPO também tem login de dono, ou só o BPO opera? → **Proposta:** login `dono` opcional; BPO opera no dia a dia.
- O preço é por organização ou por empresa? → **Proposta:** mensalidade da organização + valor por empresa ativa.
- `bpo_operador` confirma baixa (como financeiro) ou só acompanha (como atendente)? → **Proposta:** só acompanha (como atendente); baixa fica com financeiro/`bpo_admin` se o anexo comercial permitir.
- WhatsApp compartilhado entre empresas? → **Proposta:** não; mantém `_ensure_unique_instances`.
- Cadeia LGPD? → **Proposta:** empresa controladora → BPO operador → Settlr suboperador.
