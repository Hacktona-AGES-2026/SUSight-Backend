# Plano: Notificações, preferências e contatos

Spec: ./spec.md
Status: em revisão

## Abordagem

Notificações nascem dentro das mesmas transações que gravam os fatos: o `Store`
ganha um ponto único `_notify`, chamado ao gravar os eventos da trilha (spec 004),
na revisão de evidência e quando o tribunal deixa a proposta pronta. Textos fixos,
sem diagnóstico, nome ou CNS. Preferências, contatos e dispositivos são tabelas
simples, sempre ligadas ao paciente da identidade autenticada.

## Dados e interfaces

- **`notifications`**: `id`, `publico` (`paciente` | `profissional`), `paciente_id`, `sid`, `tipo`, `titulo`, `texto`, `created_at`.
- **`notification_reads`**: `notification_id`, `leitor`; a leitura é por pessoa.
- **`notification_prefs`**: `paciente_id`, `tipo`, `ativo`.
- **`contacts`**: `id`, `paciente_id`, `nome`, `parentesco`, `telefone`, `created_at`.
- **`devices`**: `id`, `principal_id`, `paciente_id`, `plataforma` (`ios` | `android` | `windows`), `token`, `created_at`.

| Origem | Público | Tipo | Título |
|---|---|---|---|
| evento `documento_recebido` | paciente | `documento_recebido` | Documento recebido |
| revisão de evidência | paciente | `analise_concluida` | Análise do documento concluída |
| evento `informacao_solicitada` | paciente | `exame_pedido` (obrigatório) | Falta um exame |
| evento `posicao_alterada` | paciente | `posicao_alterada` | Sua posição mudou |
| evento `posicao_alterada` | profissional | `fila_atualizada` | Fila aprovada e atualizada |
| evento `reavaliacao_concluida` | paciente | `reavaliacao_concluida` | Reavaliação concluída |
| evento `exame_recebido` | profissional | `paciente_respondeu` | Paciente respondeu ao pedido |
| proposta `pronta_para_medico` | profissional | `proposta_para_revisao` | Nova proposta para revisão |

Rotas:

- `GET /notificacoes` (paciente: as suas; médico: dos seus casos; admin: todas de profissional) e `POST /notificacoes/{id}/lida`.
- `GET /preferencias/notificacoes` e `PUT /preferencias/notificacoes` (paciente).
- `GET /contatos`, `POST /contatos` e `DELETE /contatos/{id}` (paciente).
- `GET /dispositivos`, `POST /dispositivos` e `DELETE /dispositivos/{id}` (a própria identidade).

## Decisões

| Decisão | Alternativas consideradas | Motivo |
|---|---|---|
| Notificar na mesma transação do fato | Processo separado lendo a trilha | Nada é notificado sem o fato, e nenhum fato fica sem aviso. |
| Leitura por pessoa | Campo `lida` único | Vários médicos podem ver o mesmo aviso do caso. |
| Preferência consultada na criação | Filtrar na leitura | A spec pede que preferência desligada impeça a notificação. |
| Telefone mascarado na leitura | Guardar só mascarado | A entrega futura precisa do número completo. |

## Riscos

- Volume de notificações de profissional cresce com a fila: aceitável na demonstração.
