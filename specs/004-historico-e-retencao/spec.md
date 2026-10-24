# Spec: Histórico, trilha de decisões e retenção

Issue: a definir
Status: aprovada para implementação (decisões do usuário em 2026-10-24)

## Contexto

O app do paciente (spec 003, Histórico) e o web do médico (specs 004 e 005) prometem um histórico completo e decisões registradas com nome, data e hora. A constituição (princípio 2) exige que toda decisão seja auditável. Hoje o backend apaga propostas, decisões, documentos e evidências em até 7 dias, o que apagaria o histórico depois de uma semana.

Esta spec separa o que expira (conteúdo de documentos e seus derivados) do que forma a trilha de auditoria e o histórico.

## Comportamento esperado

1. O backend mantém uma trilha de eventos por solicitação: entrada na fila, documento recebido, pedido de informação, prioridade validada, proposta aprovada, rejeitada ou devolvida, contestação, reavaliação concluída e mudança de posição aprovada.
2. Cada evento guarda tipo, solicitação, responsável (nome, ou "sistema"), data e hora e um texto curto em linguagem simples. O evento não guarda conteúdo de documento, nome do paciente completo nem CNS.
3. O histórico do paciente e o do médico são montados a partir desses eventos, do mais recente ao mais antigo. Só aparecem fatos registrados: proposta em análise ou em revisão não aparece como mudança de posição.
4. Documentos enviados, seus arquivos, evidências e trechos continuam expirando em até 7 dias (spec 001-extracao-de-exames). A expiração do documento não apaga o evento "documento recebido" da trilha.
5. A decisão do médico (nome, ação, motivo, data e hora) permanece consultável enquanto a solicitação existir. O parecer completo do tribunal segue a retenção da spec do tribunal.
6. O paciente só vê os eventos da própria solicitação; o médico, os dos casos que pode revisar. A permissão usa o vínculo do evento com o paciente, para que o histórico continue acessível depois que a fila importada expirar.
7. A trilha de eventos não expira. Ela não contém conteúdo de documento, nome nem CNS; o motivo da decisão é o texto informado pelo médico, limitado a 2000 caracteres, como já é hoje na decisão.
8. Esta spec registra os eventos que o backend já produz: entrada na fila, documento recebido, pedido de informação, proposta rejeitada, proposta cancelada e mudança de posição aprovada. Contestação e reavaliação são registradas pela spec 008 e exames pedidos pela spec 006, na mesma trilha. "Prioridade validada" depende de uma operação de validação pela regulação que ainda não existe no backend.

## Critérios de aceite

- [ ] Depois que um documento expira, o evento "documento recebido" continua no histórico, sem o conteúdo.
- [ ] Toda decisão do médico aparece no histórico com tipo, motivo, nome, data e hora.
- [ ] Nenhum evento da trilha contém texto de documento, nome completo ou CNS.
- [ ] Proposta ainda em análise não gera evento de mudança de posição.
- [ ] Um paciente não consegue ler eventos de outra solicitação.
- [ ] A ordem do histórico é do mais recente ao mais antigo.
- [ ] Depois que a fila importada expira, o paciente e o médico autorizado continuam lendo o histórico da solicitação.
- [ ] A mudança de posição aprovada registra a posição anterior e a nova.

## Testes (TDD)

Os testes vêm antes do código. Cada critério de aceite acima vira pelo menos um teste automatizado que falha primeiro (red), e a implementação só termina quando todos passam (green). Critério que não puder ser testado automaticamente leva uma justificativa escrita. Testes automatizados com pytest, incluindo o verificador oficial da fila quando houver `fila_priorizada.csv` (`tools/verificar_fila_priorizada.py`).

## Fora do escopo

- Telas de histórico (specs do app e do web).
- Política de guarda de prontuários reais.
- Exportação do histórico.

## Decisões

- A trilha não expira na demonstração (decisão do usuário, 2026-10-24).
- O motivo da decisão fica limitado a 2000 caracteres, sem revisão automática de conteúdo. Revisar antes de uso real.
