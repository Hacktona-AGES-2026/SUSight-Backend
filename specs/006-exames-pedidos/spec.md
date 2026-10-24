# Spec: Exames pedidos pelo médico

Issue: a definir
Status: aprovada para implementação (decisões do usuário em 2026-10-24)

## Contexto

Quando o médico escolhe "pedir informações" (web 004), o paciente precisa ver um exame ou laudo como "Pendente" na aba Documentos (app 001) e enviá-lo por lá. O widget mostra a quantidade de exames pendentes (app 004). Hoje `pedir_informacoes` é só uma decisão com motivo; o exame pedido e sua situação não são guardados.

## Comportamento esperado

1. Ao pedir informações, o médico indica o exame ou laudo desejado (nome) e, se quiser, uma explicação curta. O backend cria um pedido ligado à proposta e à solicitação, com responsável, data e hora.
2. O pedido tem situação: `pendente` (ainda não enviado), `recebido` (documento enviado) e `em_analise` (extração em andamento, spec 001-extracao-de-exames). Concluída a extração, o pedido é dado como atendido.
3. O envio de um documento pode ser ligado a um pedido pendente. O vínculo muda a situação para `recebido`.
4. O paciente lista seus pedidos e vê o nome do exame e a situação. O médico vê se o paciente respondeu.
5. Quando o paciente envia o exame pedido, o médico recebe aviso (spec 005) e a proposta volta para análise.
6. Pedir informações não altera a fila (princípio 1).
7. Enquanto a extração automática (spec 001) não existe, `em_analise` começa quando a primeira evidência do documento é registrada e o pedido fica `atendido` quando essa evidência é revisada pelo profissional.
8. "A proposta volta para análise" significa: o recebimento entra na trilha (spec 004) como `exame_recebido` e o médico pode criar nova proposta com as evidências aprovadas. A proposta encerrada não é reaberta automaticamente, porque o tribunal só analisa evidências aprovadas.
9. Um documento só pode ser ligado a um pedido `pendente` da mesma solicitação. Pedir informações sem informar ao menos um exame é recusado; as demais decisões não aceitam exames.

## Critérios de aceite

- [ ] Pedir informações cria um pedido `pendente`, com nome do exame, responsável, data e hora.
- [ ] O paciente vê o pedido como Pendente e o médico não consegue alterá-lo depois do envio.
- [ ] Enviar o documento do pedido muda a situação para `recebido` e depois `em_analise`.
- [ ] Um paciente só vê pedidos da própria solicitação.
- [ ] Pedir informações não muda posição na fila.
- [ ] A quantidade de pedidos pendentes pode ser consultada para o widget.
- [ ] A revisão da evidência do documento ligado muda o pedido para `atendido`.
- [ ] Ligar documento a pedido de outra solicitação ou já respondido é recusado.
- [ ] Pedir informações sem exame é recusado, e exames em outra decisão também.
- [ ] O recebimento do exame pedido aparece no histórico da solicitação.

## Testes (TDD)

Os testes vêm antes do código. Cada critério de aceite acima vira pelo menos um teste automatizado que falha primeiro (red), e a implementação só termina quando todos passam (green). Critério que não puder ser testado automaticamente leva uma justificativa escrita. Testes automatizados com pytest, incluindo o verificador oficial da fila quando houver `fila_priorizada.csv` (`tools/verificar_fila_priorizada.py`).

## Fora do escopo

- Telas de upload e de revisão.
- Cancelamento do pedido pelo paciente.
- Situação "Revisado" e pedido de confirmação ao paciente sobre um documento (fora do MVP do app).

## Decisões

- O pedido não tem prazo, só a data de criação.
- O médico pode pedir até 10 exames na mesma decisão; cada um vira um pedido.
- O paciente não exclui documento já enviado nesta etapa.
- Pedidos não expiram, como a trilha da spec 004: guardam só nome do exame e explicação.
