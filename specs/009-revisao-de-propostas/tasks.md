# Tarefas: Lista e detalhe de propostas para revisão médica

Plano: ./plan.md

Cada tarefa é pequena, verificável e vira um commit atômico. Os testes são commitados antes da implementação (red), e a implementação vem no commit seguinte (green). Branch de implementação: `feature/proposal-review`, empilhada sobre `feature/exam-extraction` (#18).

- [ ] 1. Testes (`tests/test_proposal_review.py`), commitados vermelhos:
  - lista só com casos permitidos, ordem de criação e total;
  - filtro padrão `pronta_para_medico`, filtro por várias situações e recusa de situação desconhecida (422);
  - posição atual da fila vigente e posição proposta em cada item;
  - paciente recebe 403 na lista e no detalhe; médico de outro caso recebe 404 no detalhe;
  - detalhe com evidências (trecho, página, revisor), parecer completo e histórico;
  - detalhe depois da decisão com ação, motivo, responsável e data e hora;
  - proposta expirada fora da lista e 404 no detalhe;
  - fila importada com `criterios`, `swalis` e `prioridade_regulacao` aparece no detalhe; sem eles, campos nulos;
  - lista e detalhe não chamam o provedor (contagem de chamadas do provedor falso inalterada).
- [ ] 2. `QueuePatient` com `criterios`, `swalis` e `prioridade_regulacao` opcionais.
- [ ] 3. `Store.list_proposals` e rota `GET /propostas`.
- [ ] 4. `Store.proposal_detail` e rota `GET /propostas/{id}`.
- [ ] 5. Documentar as rotas em `docs/backend-api.md` e rodar a suíte completa, Ruff e formatação.
- [ ] 6. Avisar o time do web dos nomes dos campos, para a camada de dados do SUSight-Web.
