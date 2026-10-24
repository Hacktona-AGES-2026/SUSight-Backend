# Spec: Tribunal de IAs

Issue: Hacktona-AGES-2026/SUSight#8
Status: rascunho

## Contexto

Quando um evento novo (exame, laudo, relato de piora, rejeição do médico) sugere mudar a posição de um paciente na fila, a mudança precisa ser debatida antes de chegar ao médico. O tribunal de IAs reduz o risco de uma única IA propor algo injusto ou mal fundamentado: três agentes com papéis diferentes argumentam e o médico recebe o debate junto com a proposta.

O tribunal é consultivo. Quem decide é o médico (constituição, princípios 1 e 3).

## Comportamento esperado

1. O sistema convoca o tribunal só quando existe uma proposta de mudança de posição para um paciente. A ordenação inicial da fila não passa pelo tribunal.
2. A proposta chega ao tribunal com: paciente, posição atual, posição proposta, critérios que motivaram a mudança e as evidências (eventos clínicos e trechos de laudo ou exame).
3. Três agentes dão cada um uma única manifestação, sem réplica:
   - **Evidências:** argumenta a favor da mudança e cita as evidências usadas.
   - **Contestação:** argumenta contra e aponta o que falta confirmar.
   - **Equidade e regras:** confere a proposta contra os limites de equidade e o efeito sobre os pacientes que seriam ultrapassados.
4. Cada agente emite um veredito: `a_favor`, `contra` ou `ajustar`. Quem votar `ajustar` informa a posição que considera adequada.
5. O sistema consolida as três manifestações em um parecer legível para o médico, com a recomendação (aprovar, ajustar ou negar) e a justificativa em português simples, sem alarme.
6. As travas rígidas são aplicadas por regra determinística, fora do tribunal: a regra de ouro oncológica, o limite de elevação por reavaliação e a regra de não passar à frente de quem tem prioridade maior e mais espera. Nenhum veredito do tribunal pode produzir uma proposta que viole essas travas. Se a proposta violar, ela é barrada e o parecer registra o motivo.
7. A proposta com o parecer segue para o médico. Nada muda na fila antes da aprovação dele.
8. Relato do paciente sozinho (sem exame ou evento clínico) não sustenta o veredito `a_favor` do agente de Evidências; o parecer destaca a ausência de comprovação.
9. O parecer completo (as três manifestações, os vereditos e a recomendação) fica guardado e é vinculado à proposta, para consulta e auditoria.

## Critérios de aceite

- [ ] O tribunal só é acionado quando há proposta de mudança de posição; a fila inicial é gerada sem ele.
- [ ] Cada caso gera exatamente três manifestações, uma por agente, cada uma com veredito e justificativa.
- [ ] A recomendação final é uma de: aprovar, ajustar ou negar.
- [ ] Uma proposta que viola a regra de ouro oncológica (CID `C*` abaixo de paciente sem urgência clínica) nunca chega ao médico como aprovável, mesmo com os três votos `a_favor`.
- [ ] Uma proposta que excede o limite de elevação por reavaliação é barrada ou reduzida ao limite, e o parecer informa isso.
- [ ] Caso sustentado só por relato do paciente é sinalizado como sem comprovação por exame.
- [ ] O parecer está em português do Brasil, em linguagem simples, e não contém diagnóstico.
- [ ] O parecer fica persistido e consultável pelo identificador da proposta.
- [ ] Os dados do paciente enviados ao tribunal e exibidos no parecer seguem a regra de mascaramento (LGPD).
- [ ] Mesma proposta, mesmas evidências e mesmas travas produzem sempre a mesma barragem de regras (a parte determinística é reprodutível).

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

- Qual LLM e provedor usar, e se a demo usa respostas reais ou simuladas e determinísticas.
- O que mais o time quer deixar fora da primeira versão (a resposta "outro" no levantamento veio sem texto).
- Valor do limite de elevação por reavaliação (depende da issue #6).
- Quando os agentes discordam (por exemplo 2 a favor e 1 contra), a recomendação segue maioria ou o parecer só apresenta o empate para o médico?
- Quanto tempo o tribunal pode levar por caso antes de a proposta seguir sem parecer, ou ficar retida.
- Se o tribunal falhar ou ficar indisponível, a proposta vai ao médico sem parecer (marcada como tal) ou fica retida?
