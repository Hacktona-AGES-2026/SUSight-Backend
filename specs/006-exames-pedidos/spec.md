# Spec: Exames pedidos pelo médico

Issue: a definir
Status: rascunho

## Contexto

Quando o médico escolhe "pedir informações" (web 004), o paciente precisa ver um exame ou laudo como "Pendente" na aba Documentos (app 001) e enviá-lo por lá. O widget mostra a quantidade de exames pendentes (app 004). Hoje `pedir_informacoes` é só uma decisão com motivo; o exame pedido e sua situação não são guardados.

## Comportamento esperado

1. Ao pedir informações, o médico indica o exame ou laudo desejado (nome) e, se quiser, uma explicação curta. O backend cria um pedido ligado à proposta e à solicitação, com responsável, data e hora.
2. O pedido tem situação: `pendente` (ainda não enviado), `recebido` (documento enviado) e `em_analise` (extração em andamento, spec 001-extracao-de-exames). Concluída a extração, o pedido é dado como atendido.
3. O envio de um documento pode ser ligado a um pedido pendente. O vínculo muda a situação para `recebido`.
4. O paciente lista seus pedidos e vê o nome do exame e a situação. O médico vê se o paciente respondeu.
5. Quando o paciente envia o exame pedido, o médico recebe aviso (spec 005) e a proposta volta para análise.
6. Pedir informações não altera a fila (princípio 1).

## Critérios de aceite

- [ ] Pedir informações cria um pedido `pendente`, com nome do exame, responsável, data e hora.
- [ ] O paciente vê o pedido como Pendente e o médico não consegue alterá-lo depois do envio.
- [ ] Enviar o documento do pedido muda a situação para `recebido` e depois `em_analise`.
- [ ] Um paciente só vê pedidos da própria solicitação.
- [ ] Pedir informações não muda posição na fila.
- [ ] A quantidade de pedidos pendentes pode ser consultada para o widget.

## Fora do escopo

- Telas de upload e de revisão.
- Cancelamento do pedido pelo paciente.
- Situação "Revisado" e pedido de confirmação ao paciente sobre um documento (fora do MVP do app).

## Questões em aberto

- O pedido tem prazo (como "Enviar até sexta") ou só a data de criação?
- O médico pode pedir mais de um exame na mesma decisão?
- O paciente pode excluir um documento já enviado? (pergunta em aberto na spec 001 do app)
