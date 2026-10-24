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
   - **Contestação:** questiona a mudança e a sustentação da indicação cirúrgica atual, usando BRAN: benefícios esperados, riscos, alternativas documentadas e consequências de não realizar o procedimento. Aponta evidência ausente ou conflitante para revisão médica, sem concluir por conta própria que a cirurgia é desnecessária. Ausência de documentação não comprova ausência de indicação.
   - **Equidade e regras:** confere a proposta contra os limites de equidade e o efeito sobre os pacientes que seriam ultrapassados.
4. Cada agente emite um veredito: `a_favor`, `contra` ou `ajustar`. Quem votar `ajustar` informa a posição que considera adequada.
5. O sistema consolida as três manifestações em um parecer legível para o médico, com a recomendação (aprovar, ajustar ou negar) e a justificativa em português simples, sem alarme. A recomendação segue a maioria dos votos (`a_favor` → aprovar, `contra` → negar, `ajustar` → ajustar). Quando há voto vencido, ele aparece em destaque no parecer. Quando os três votos são diferentes, a recomendação é ajustar.
6. As travas rígidas são aplicadas por regra determinística, fora do tribunal: a regra de ouro oncológica, o limite de elevação por reavaliação e a hierarquia de prioridade definida na spec 002, sem preferência por tempo de espera. Nenhum veredito do tribunal pode produzir uma proposta que viole essas travas. Se a proposta violar, ela é barrada e o parecer registra o motivo.
7. A proposta com o parecer segue para o médico. Nada muda na fila antes da aprovação dele.
8. Relato do paciente sozinho (sem exame ou evento clínico) não sustenta o veredito `a_favor` do agente de Evidências; o parecer destaca a ausência de comprovação.
9. O parecer completo (as três manifestações, os vereditos e a recomendação) fica guardado e é vinculado à proposta, para consulta e auditoria.
10. Se algum agente falhar ou passar do tempo limite, a proposta fica retida com a situação "aguardando tribunal" e o sistema tenta de novo automaticamente. Depois de algumas tentativas sem sucesso, a proposta passa a exibir o aviso "tribunal indisponível" na lista de pendências, para que a equipe saiba que ela está parada, e o sistema continua tentando. Nenhuma proposta chega ao médico para decisão sem o parecer completo dos três agentes.

O valor do limite de elevação por reavaliação vem da spec de pontuação da fila (issue #6). O tribunal usa o valor definido lá.

### Recomendações adotadas para o MVP

- **Demonstração:** usar exclusivamente pacientes, filas e evidências sintéticos. Serviços externos recebem apenas o contexto mínimo necessário, pseudonimizado e sem nome, CNS, município, endereço ou texto livre identificável. Mascaramento não autoriza envio de dados reais nem uso clínico real. O fornecedor e o modelo são decisões do plano, sujeitos à conferência dos termos pelo responsável de Backend.
- **Integração com extração:** a extração descrita em `specs/001-extracao-de-exames/spec.md` (PR #7) entrega propostas com evidência e confiança. Uma proposta de alta confiança não equivale a dado aprovado. Campos incertos, ilegíveis, conflitantes ou fora do domínio da pontuação exigem revisão profissional; o tribunal não preenche seus valores nem resolve lacunas de leitura por voto.
- **Comprovação:** cada afirmação usada pelo agente deve apontar uma evidência disponível no caso. Referência inexistente, troca de identidade de agente, posição fora da fila ou resposta sem os campos obrigatórios invalida o parecer e aciona nova tentativa. Relato ou valor imputado não é apresentado como exame confirmatório.
- **Falhas:** cada agente tem até 30 segundos por tentativa. Tentativas automáticas usam espera crescente, de cinco segundos até no máximo cinco minutos; após três falhas consecutivas, exibir "tribunal indisponível". A proposta permanece retida, com opção de reprocessamento. As tentativas cessam se a proposta perder validade, for encerrada ou expirar; nenhum resultado simulado substitui o parecer real.
- **Maioria e ajuste:** manter os três votos e a divergência visíveis. Havendo várias posições sugeridas, a proposta de ajuste usa a posição menos adiantada entre elas e passa novamente pelas travas. Empate entre três vereditos diferentes continua resultando em ajustar, com a divergência explícita.
- **Autoridade e equidade:** o médico pode discordar do parecer consultivo, registrando motivo. Essa decisão não dispensa as travas nem permite ao tribunal autorizar elevação acima de 10%, salvo a prevalência explícita da regra de ouro. Biópsia positiva com CID ainda não `C*` exige revisão, sem alteração automática do diagnóstico. Conflito entre a ROR e uma trava é uma pendência de modelo, não um caso que a maioria dos agentes possa liberar.
- **Versão e auditoria:** se a fila mudar durante a análise ou antes da decisão, exigir nova proposta ou revalidação explícita, sem aplicar o parecer antigo silenciosamente. Guardar versão de fila, evidências, três manifestações, recomendação, tentativas, decisão, responsável e data/hora. Nome de profissional informado na demo não comprova identidade clínica verificada.
- **Acesso e guarda:** restringir o caso aos envolvidos autorizados; pacientes não acessam evidências de outros pacientes nem o contexto interno do debate. Artefatos e decisões sintéticos da demonstração expiram em até sete dias da criação da proposta, ou antes por solicitação do responsável. Uma referência a documento que expire antes não permanece disponível ao provedor em tentativas futuras. Registros operacionais não contêm documentos, pareceres integrais, identificadores pessoais ou credenciais.

As recomendações definem comportamento esperado. Sua inclusão não comprova implementação de expiração, autorização por paciente, validação semântica de linguagem clínica ou execução de um caso real no provedor.

### Revisão clínica de 2026-10-24

O papel ampliado de Contestação está em revisão e ainda não foi implementado nem testado. Mantêm-se três agentes e o acionamento por caso incerto/conflitante, sem varredura automática de toda a fila. Suspeita de indicação inadequada gera pendência de revisão; não implica cancelar, excluir ou reposicionar uma solicitação por voto. A decisão profissional e sua justificativa continuam obrigatórias. BRAN organiza perguntas, sem produzir pontuação. Ver [registro e referências](../../docs/clinical-review-2026-10-24.md).

## Critérios de aceite

- [ ] O tribunal é acionado para propostas com pares incertos ou evidências conflitantes; a fila inicial é gerada sem chamadas de IA.
- [ ] Contestação distingue evidência ausente de indicação inadequada, registra as quatro perguntas BRAN e encaminha dúvidas ao médico; nenhuma solicitação é excluída automaticamente.
- [ ] Alterar apenas o tempo de espera não modifica a decisão das travas.
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
- [ ] Três falhas geram o aviso previsto; expiração, encerramento ou perda de validade impedem novas tentativas com documentos ou versões antigas.
- [ ] Evidência inexistente e valor documental ainda não aprovado não são aceitos como comprovação clínica por simples votação.
- [ ] Discordância médica é auditada e continua sujeita às travas; o tribunal não libera um conflito de modelagem nem altera o CID.
- [ ] O cenário sintético de aceitação verifica retenção de até sete dias e impede acesso por usuário sem permissão para o caso.

## Testes (TDD)

Os testes vêm antes do código. Cada critério de aceite acima vira pelo menos um teste automatizado que falha primeiro (red), e a implementação só termina quando todos passam (green). Critério que não puder ser testado automaticamente leva uma justificativa escrita. Testes automatizados com pytest, incluindo o verificador oficial da fila quando houver `fila_priorizada.csv` (`tools/verificar_fila_priorizada.py`).

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

Nenhuma decisão de escopo do MVP pendente. Tempo limite, aviso e política de falha estão definidos acima; a seleção de ferramenta, LLM e provedor permanece no plano. Conferir os termos do serviço, executar o caso real com dados sintéticos e verificar os controles de acesso/expiração são condições de aceitação, não resultados presumidos.

## Alinhamento da implementação

Autorização de implementação pelo usuário em 2026-10-24. As travas usam a fila vigente do servidor; nenhuma posição é aplicada sem decisão médica. O provedor é configurável por ambiente e sua disponibilidade não implica validação clínica do parecer.

## Estado da implementação

Implementação e testes incluídos no PR consolidado. Evidências e critérios de aceitação ainda pendentes estão em `../../docs/backend-validation.md`; não declarar validação clínica nem aceitação da base completa antes de resolver essas pendências.
