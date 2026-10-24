# Plano: Histórico, trilha de decisões e retenção

Spec: ./spec.md
Status: em revisão

## Abordagem

Uma tabela `events` no mesmo SQLite do `Store`, sem coluna de expiração e fora de
`purge_expired`. Cada operação que já existe grava o seu evento na mesma transação,
para que fato e histórico nunca divirjam. Uma rota de leitura monta o histórico.

## Dados e interfaces

**`events`**: `id` (inteiro, ordem de gravação), `sid`, `paciente_id`, `tipo`, `actor`,
`texto`, `motivo` (opcional) e `created_at` (ISO 8601 UTC).

| Operação existente | Tipo do evento | Texto |
|---|---|---|
| `import_queue` (solicitação nova) | `entrada_na_fila` | Entrou na fila de cirurgia. |
| `register_document` | `documento_recebido` | Documento recebido. |
| `decide` com `pedir_informacoes` | `informacao_solicitada` | O médico pediu mais informações. |
| `decide` com `rejeitar` | `proposta_rejeitada` | A proposta de mudança não foi aprovada. |
| `decide` com `aprovar` | `posicao_alterada` | Posição alterada de Nª para Mª após aprovação médica. |
| `cancel` | `proposta_cancelada` | A proposta de mudança foi cancelada. |

`entrada_na_fila` só é gravado uma vez por solicitação, mesmo com reimportações.

**Rota**: `GET /solicitacoes/{sid}/historico` devolve `{"solicitacao_id", "eventos": [...]}`
do mais recente ao mais antigo, com `tipo`, `texto`, `responsavel`, `motivo` e `data_hora`.
Sem eventos, ou sem permissão, responde 404, sem revelar se a solicitação existe.

## Decisões

| Decisão | Alternativas consideradas | Motivo |
|---|---|---|
| Tabela própria sem expiração | Manter `decisions` sem expiração | `decisions` depende de propostas que expiram; a trilha precisa sobreviver a elas. |
| Permissão pelo `paciente_id` do evento | Exigir a solicitação na fila ativa | A fila expira em 7 dias; o histórico, não. |
| Gravar na mesma transação | Gravar depois da operação | Evita fato sem evento ou evento sem fato. |
| Textos fixos gerados pelo backend | Texto livre | Garante linguagem simples e nenhum conteúdo de documento. |

## Riscos

- Motivo livre do médico pode conter dado sensível: limitado a 2000 caracteres e sinalizado para revisão antes de uso real.
- Crescimento sem limite da tabela: aceitável no volume da demonstração.
