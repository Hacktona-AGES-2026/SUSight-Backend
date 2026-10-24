# Tarefas: Tribunal de IAs

Plano: ./plan.md

Cada tarefa é pequena, verificável e vira um commit atômico.

- [ ] 1. Criar o esqueleto do módulo `tribunal` e os modelos Pydantic (contexto do caso, manifestação do agente, parecer, situação da proposta).
- [ ] 2. Implementar o mascaramento do contexto (remove nome, CNS e município) com teste.
- [ ] 3. Implementar as travas determinísticas (regra de ouro, limite de elevação configurável, não ultrapassar quem tem prioridade maior e mais espera) com testes, incluindo o caso da regra de ouro com três votos `a_favor`.
- [ ] 4. Implementar a consolidação por maioria (voto vencido em destaque; três votos diferentes resultam em ajustar) com testes.
- [ ] 5. Escrever os prompts dos três agentes em português, proibindo diagnóstico e linguagem alarmante e exigindo citar evidências.
- [ ] 6. Implementar o cliente do Gemini com saída estruturada, tempo limite por chamada e validação da resposta.
- [ ] 7. Implementar o serviço do tribunal: travas, três agentes em paralelo, consolidação, travas na posição ajustada e sinalização de "sem comprovação".
- [ ] 8. Persistir o parecer e a situação da proposta em SQLite.
- [ ] 9. Implementar as novas tentativas em tarefa de fundo, com a situação `tribunal_indisponivel` após 3 falhas e a retomada ao subir a API.
- [ ] 10. Expor `POST /propostas/{id}/tribunal` e `GET /propostas/{id}/parecer`.
- [ ] 11. Teste ponta a ponta do serviço com o cliente do LLM substituído, cobrindo os critérios de aceite da spec.
- [ ] 12. Rodar um caso real do dataset contra o Gemini e conferir manualmente cada critério de aceite.
