# Spec: Lista e detalhe de propostas para revisão médica

Issue: a definir
Status: implementada (PR #20, na dev pelo PR #21); resta avisar o time do web dos nomes dos campos

## Contexto

O SUSight Clínica (web) passou a usar as rotas do backend diretamente. As telas de revisões pendentes (web 003) e de decisão (web 004) precisam descobrir as propostas que aguardam o médico e mostrar tudo o que sustenta cada uma. Hoje o backend só cria propostas, roda o tribunal, devolve o parecer (`GET /propostas/{id}/parecer`) e registra a decisão. Não há como listar propostas, e o parecer não traz posição atual, critérios, evidências nem histórico. A notificação de nova proposta (spec 005) informa a solicitação, mas não a proposta.

Sem essas duas rotas, o médico não consegue revisar nada pelo web. Esta spec cobre só elas. Depende da trilha de histórico (spec 004).

## Comportamento esperado

**Lista**

1. O profissional pede a lista de propostas e recebe as dos casos que pode revisar, da mais antiga para a mais nova. O administrador recebe todas. O paciente não acessa a lista.
2. Por padrão vêm as propostas prontas para o médico decidir (`pronta_para_medico`). É possível filtrar por uma ou mais situações: `aguardando_tribunal`, `processando`, `tribunal_indisponivel`, `pronta_para_medico`, `aprovar`, `rejeitar`, `pedir_informacoes`, `cancelada` e `desatualizada`.
3. Cada item traz: identificador da proposta, solicitação, situação, posição atual na fila vigente, posição proposta, recomendação do tribunal (quando houver parecer), se a ordenação é incerta, se há evidências conflitantes e data e hora de criação. Também traz o total de itens.
4. Propostas expiradas não aparecem.

**Detalhe**

5. O profissional do caso abre uma proposta e recebe, além dos dados do item da lista:
   - a classe SWALIS, a prioridade da regulação (só informativa) e os seis critérios da pontuação da solicitação, quando a fila importada os trouxer;
   - as evidências aprovadas que sustentam a proposta, cada uma com tipo, resultado, data, trecho, página e quem aprovou;
   - o parecer do tribunal: as três manifestações (agente, veredito, posição sugerida, justificativa e evidências citadas), a recomendação, as divergências, as travas aplicadas e a posição liberada;
   - o histórico da solicitação (spec 004), do mais recente ao mais antigo;
   - a decisão, quando já houver: ação, motivo, responsável e data e hora.
6. Proposta de outro caso responde como inexistente, sem revelar que existe. O paciente não acessa o detalhe.
7. Os dados vêm só do que o backend já guarda. Nada é recalculado nem enviado à IA para montar a lista ou o detalhe.

**Fila importada**

8. A importação da fila passa a aceitar, de forma opcional, os seis critérios (`limitacao`, `asa`, `dor`, `comorbidades`, `deterioracao`, `distancia`), a classe SWALIS e a prioridade da regulação, como já saem no `fila.json` da pontuação. Sem eles, o detalhe mostra esses campos vazios.

## Critérios de aceite

- [ ] A lista devolve só propostas de casos permitidos ao profissional, da mais antiga para a mais nova, com o total.
- [ ] Sem filtro, a lista traz só `pronta_para_medico`; com filtro, só as situações pedidas. Situação desconhecida é recusada.
- [ ] Cada item tem posição atual na fila vigente e posição proposta.
- [ ] O paciente recebe 403 na lista e no detalhe; o médico de outro caso recebe 404 no detalhe.
- [ ] O detalhe traz evidências aprovadas com trecho, página e revisor, o parecer completo e o histórico da solicitação.
- [ ] Depois da decisão, o detalhe mostra ação, motivo, responsável e data e hora.
- [ ] Proposta expirada não aparece na lista e responde 404 no detalhe.
- [ ] A fila importada com critérios, SWALIS e prioridade os devolve no detalhe; sem eles, os campos vêm nulos e a importação continua válida.
- [ ] Montar a lista e o detalhe não chama o provedor de IA.

## Testes (TDD)

Os testes vêm antes do código. Cada critério de aceite acima vira pelo menos um teste automatizado que falha primeiro (red), e a implementação só termina quando todos passam (green). Critério que não puder ser testado automaticamente leva uma justificativa escrita. Testes automatizados com pytest e `TestClient`, usando a fixture `history_api` e o provedor falso do tribunal.

## Fora do escopo

- Nome, CNS mascarado e procedimento do paciente na fila: a fila importada não tem esses dados e o dataset não tem CNS.
- Lista geral de decisões registradas (web 009).
- Remover e restaurar paciente da fila (web 009).
- Reanálise automática pela IA depois de rejeição.
- Telas do web.

## Questões em aberto

- O web precisa de paginação na lista? Com até 925 solicitações e poucas propostas abertas, esta spec devolve a lista inteira.
