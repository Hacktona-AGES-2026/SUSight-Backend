# Tarefas: Tribunal de IAs

Plano: ./plan.md

Cada tarefa é pequena, verificável e vira um commit atômico.

- [x] 1. Criar o esqueleto do módulo `tribunal` e os modelos Pydantic (contexto do caso, manifestação do agente, parecer, situação da proposta).
- [x] 2. Implementar o mascaramento do contexto (remove nome, CNS e município) com teste.
- [x] 3. Implementar as travas determinísticas (regra de ouro, limite de elevação configurável, hierarquia; a trava antiga de espera foi retirada na revisão da spec 002) com testes, incluindo o caso da regra de ouro com três votos `a_favor`.
- [x] 4. Implementar a consolidação por maioria (voto vencido em destaque; três votos diferentes resultam em ajustar) com testes.
- [x] 5. Escrever os prompts dos três agentes em português, proibindo diagnóstico e linguagem alarmante e exigindo citar evidências.
- [x] 6. Implementar o cliente do Gemini com saída estruturada, tempo limite por chamada e validação da resposta.
- [x] 7. Implementar o serviço do tribunal: travas, três agentes em paralelo, consolidação, travas na posição ajustada e sinalização de "sem comprovação".
- [x] 8. Persistir o parecer e a situação da proposta em SQLite.
- [x] 9. Implementar as novas tentativas em tarefa de fundo, com a situação `tribunal_indisponivel` após 3 falhas e a retomada ao subir a API.
- [x] 10. Expor `POST /propostas/{id}/tribunal` e `GET /propostas/{id}/parecer`.
- [x] 11. Teste ponta a ponta do serviço com o cliente do LLM substituído, cobrindo os critérios de aceite da spec.
- [ ] 12. Rodar um caso real do dataset contra o Gemini e conferir manualmente cada critério de aceite.

A tarefa 12 depende de credenciais e revisão humana. Sem chamada real realizada; ver `../../docs/backend-validation.md`.

## Complemento técnico concluído

- [x] Restringir operações por identidade, papel e paciente.
- [x] Vincular evidência a documento e exigir revisão profissional no registro do servidor.
- [x] Auditar revisão, decisão e cancelamento pela identidade autenticada.
- [x] Impedir publicação ou nova tentativa após expiração/cancelamento, inclusive durante chamada.
- [x] Eliminar conteúdo expirado e testar migração conservadora de banco legado.
- [x] Exigir citação de evidência nos votos favoráveis e de ajuste.

O teste real da tarefa 12 permanece fora da solicitação atual. Não houve chamada externa.

## Revisão planejada de BRAN

- [x] Retirar espera das travas e do contexto externo; testar invariância temporal.
- [x] Versionar política/fila e impedir aplicação de propostas desatualizadas, preservando pareceres anteriores para auditoria.
- [ ] Revisar o complemento de plano de BRAN e suficiência dos dados aprovados com a equipe.
- [ ] Após revisão, implementar contrato BRAN e pendência de indicação, sem exclusão autônoma.
- [ ] Após revisão, admitir parecer especializado com proveniência específica.
- [ ] Verificar contratos e autorização com provedor de teste, sem chamadas externas.
