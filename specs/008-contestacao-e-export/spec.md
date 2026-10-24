# Spec: Contestação e registro de export

Issue: a definir
Status: rascunho

## Contexto

O web (specs 005 e 006) permite ao médico contestar a posição de um paciente na fila e exportar a fila ordenada em CSV, e promete registrar ambas as ações com nome, data e hora. O backend não tem contestação nem registro de export. Reavaliação automática depois de rejeição está fora da feature atual da API.

## Comportamento esperado

**Contestação**

1. O médico abre um paciente da fila e contesta a posição, com motivo obrigatório. O backend registra a contestação com responsável, data e hora, ligada à solicitação.
2. Contestar não muda a fila. A solicitação passa a "Em reavaliação" e é enviada para nova análise da IA.
3. O resultado fica no histórico: nova proposta gerada, ou posição mantida com a justificativa. Qualquer mudança de posição continua dependendo de aprovação do médico.
4. Enquanto estiver em reavaliação, uma segunda contestação da mesma solicitação é recusada.

**Export**

5. O médico exporta a fila ordenada, a versão atual, em CSV. O backend registra o export com responsável, data e hora, versão da fila e quantidade de linhas.
6. Campos com vírgula, aspas ou quebra de linha não quebram as colunas.
7. O CSV segue a ordem da fila vigente e não inclui propostas ainda não aprovadas.
8. O log do export não guarda o conteúdo do CSV.

## Critérios de aceite

- [ ] Contestação registrada guarda motivo, responsável, data e hora e não altera a posição.
- [ ] A solicitação contestada aparece como "Em reavaliação" até a conclusão.
- [ ] Contestar duas vezes seguidas a mesma solicitação em reavaliação é recusado.
- [ ] O resultado da contestação aparece no histórico (spec 004-historico-e-retencao).
- [ ] O export registra responsável, data, hora, versão da fila e quantidade de linhas.
- [ ] CSV com campo contendo vírgula, aspas ou quebra de linha mantém as colunas.
- [ ] O CSV só tem a ordem da fila aprovada.
- [ ] Usuário sem autenticação ou sem permissão não exporta nem contesta.

## Testes (TDD)

Os testes vêm antes do código. Cada critério de aceite acima vira pelo menos um teste automatizado que falha primeiro (red), e a implementação só termina quando todos passam (green). Critério que não puder ser testado automaticamente leva uma justificativa escrita. Testes automatizados com pytest, incluindo o verificador oficial da fila quando houver `fila_priorizada.csv` (`tools/verificar_fila_priorizada.py`).

## Fora do escopo

- Telas de contestação e de export.
- Export de revisões pendentes ou do histórico de decisões.
- Reavaliação automática depois de rejeição.

## Questões em aberto

- O CSV leva CNS completo, mascarado ou identificador anônimo (LGPD)?
- Quem pode contestar: qualquer médico autorizado ou só o da solicitação?
- Colunas e ordem do CSV, que pertencem ao web (spec 006).
