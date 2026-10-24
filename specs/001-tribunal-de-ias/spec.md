# Spec: Tribunal de IAs

Issue: Hacktona-AGES-2026/SUSight#8
Status: em revisão

## Contexto

Quando um evento novo (exame, laudo, relato de piora, rejeição do médico) sugere mudar a posição de um paciente na fila, a mudança precisa ser debatida antes de chegar ao médico. O tribunal de IAs reduz o risco de uma única IA propor algo injusto ou mal fundamentado: três agentes com papéis diferentes argumentam e o médico recebe o debate junto com a proposta.

O tribunal é consultivo. Quem decide é o médico (constituição, princípios 1 e 3).

## Comportamento esperado

1. O sistema convoca o tribunal quando uma proposta envolve ordenação incerta apontada pela ROR ou evidências conflitantes que precisam de revisão. A ordenação inicial não convoca o tribunal automaticamente; seus pares incertos ficam disponíveis para revisão.
2. A proposta chega ao tribunal com: paciente, posição atual, posição proposta, critérios que motivaram a mudança e as evidências (eventos clínicos e trechos de laudo ou exame).
3. Três agentes, cada um movido por um LLM real, dão cada um uma única manifestação, sem réplica. Não existe resposta simulada: todo parecer vem de uma análise feita de fato.
   - **Evidências:** argumenta a favor da mudança e cita as evidências usadas.
   - **Contestação:** argumenta contra e aponta o que falta confirmar.
   - **Equidade e regras:** confere a proposta contra os limites de equidade e o efeito sobre os pacientes que seriam ultrapassados.
4. Cada agente emite um veredito: `a_favor`, `contra` ou `ajustar`. Quem votar `ajustar` informa a posição que considera adequada.
5. O sistema consolida as três manifestações em um parecer legível para o médico, com a recomendação (aprovar, ajustar ou negar) e a justificativa em português simples, sem alarme. A recomendação segue a maioria dos votos (`a_favor` → aprovar, `contra` → negar, `ajustar` → ajustar). Quando há voto vencido, ele aparece em destaque no parecer. Quando os três votos são diferentes, a recomendação é ajustar.
6. As travas rígidas são aplicadas por regra determinística, fora do tribunal: a regra de ouro oncológica, o limite de elevação por reavaliação e a regra de não passar à frente de quem tem prioridade maior e mais espera. Nenhum veredito do tribunal pode produzir uma proposta que viole essas travas. Se a proposta violar, ela é barrada e o parecer registra o motivo.
7. A proposta com o parecer segue para o médico. Nada muda na fila antes da aprovação dele.
8. Relato do paciente sozinho (sem exame ou evento clínico) não sustenta o veredito `a_favor` do agente de Evidências; o parecer destaca a ausência de comprovação.
9. O parecer completo (as três manifestações, os vereditos e a recomendação) fica guardado e é vinculado à proposta, para consulta e auditoria.
10. Se algum agente falhar ou passar do tempo limite, a proposta fica retida com a situação "aguardando tribunal" e o sistema tenta de novo automaticamente. Depois de algumas tentativas sem sucesso, a proposta passa a exibir o aviso "tribunal indisponível" na lista de pendências, para que a equipe saiba que ela está parada, e o sistema continua tentando. Nenhuma proposta chega ao médico para decisão sem o parecer completo dos três agentes.

O valor do limite de elevação por reavaliação vem da spec de pontuação da fila (issue #6). O tribunal usa o valor definido lá.

## Critérios de aceite

- [ ] O tribunal é acionado para propostas com pares incertos ou evidências conflitantes; a fila inicial é gerada sem chamadas de IA.
- [ ] Cada caso gera exatamente três manifestações, uma por agente, cada uma com veredito e justificativa.
- [ ] A recomendação final é uma de: aprovar, ajustar ou negar, e segue a maioria dos votos.
- [ ] Com votos divididos, o voto vencido aparece em destaque; com três votos diferentes, a recomendação é ajustar.
- [ ] Se um agente falha ou passa do tempo limite, a proposta fica "aguardando tribunal", é reprocessada e não chega ao médico sem parecer completo. Após as tentativas iniciais falharem, ela mostra o aviso "tribunal indisponível".
- [ ] Uma proposta que viola a regra de ouro oncológica (CID `C*` abaixo de paciente sem urgência clínica) nunca chega ao médico como aprovável, mesmo com os três votos `a_favor`.
- [ ] Uma proposta que excede o limite de elevação por reavaliação é barrada ou reduzida ao limite, e o parecer informa isso.
- [ ] Caso sustentado só por relato do paciente é sinalizado como sem comprovação por exame.
- [ ] O parecer está em português do Brasil, em linguagem simples, e não contém diagnóstico.
- [ ] O parecer fica persistido e consultável pelo identificador da proposta.
- [ ] Os dados do paciente enviados ao tribunal e exibidos no parecer seguem a regra de mascaramento (LGPD).
- [ ] A checagem das travas é reprodutível: a mesma proposta com as mesmas evidências é sempre barrada (ou liberada) da mesma forma.

## Fora do escopo

- Ordenação inicial da fila (vem da pontuação, issue #6).
- Debate em várias rodadas ou réplica entre agentes.
- Memória entre casos: cada caso é julgado de forma isolada.
- Um advogado por paciente da lista.
- Aprovar, rejeitar ou aplicar a mudança na fila (é do médico, issues #17 e #19).
- Reavaliação após rejeição (issue #9), que apenas reaproveita o tribunal.
- Extração dos critérios a partir de exame ou laudo (issue #7).
- Tela de exibição do parecer (Pulse Clinical, issue #16).

## Questões em aberto

Nenhuma. A escolha do LLM e do provedor, o tempo limite por agente e a política de novas tentativas são decisões do plano.

## Alinhamento da implementação

Autorização de implementação pelo usuário em 2026-10-24. As travas usam a fila vigente do servidor; nenhuma posição é aplicada sem decisão médica. O provedor é configurável por ambiente e sua disponibilidade não implica validação clínica do parecer.

## Estado da implementação

Implementação e testes incluídos no PR consolidado. Evidências e critérios de aceitação ainda pendentes estão em `../../docs/backend-validation.md`; não declarar validação clínica nem aceitação da base completa antes de resolver essas pendências.
