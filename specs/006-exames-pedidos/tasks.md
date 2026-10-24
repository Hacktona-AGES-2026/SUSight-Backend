# Tarefas: Exames pedidos pelo médico

Plano: ./plan.md

- [x] 1. Testes primeiro, commitados antes do código (`tests/test_exam_requests.py`, 6 vistos falhando; `test_history` ajustado para enviar exames).
- [x] 2. `Decision.exames`, `DocumentInput.pedido_id` e tabela `exam_requests`.
- [x] 3. Transições de situação no registro de documento, de evidência e na revisão.
- [x] 4. Rota `GET /solicitacoes/{sid}/exames-pedidos` com contagem de pendentes.
- [x] 5. Rodar a suíte completa, Ruff e formatação: 86 testes passando.
