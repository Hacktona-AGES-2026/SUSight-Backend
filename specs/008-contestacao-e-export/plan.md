# Plano: Contestação e registro de export

Spec: ./spec.md
Status: em revisão

## Abordagem

Duas tabelas novas no SQLite do `Store`, sem expiração: `disputes` e `exports`.
A contestação grava evento na trilha (spec 004) na mesma transação. O export gera o
CSV com o módulo `csv` da biblioteca padrão, que já trata vírgula, aspas e quebra de linha.

## Dados e interfaces

**`disputes`**: `id`, `sid`, `paciente_id`, `actor`, `motivo`, `created_at`,
`status` (`em_reavaliacao` | `concluida`), `resultado` (`nova_proposta` | `posicao_mantida`),
`justificativa`, `concluded_at`.

**`exports`**: `id`, `actor`, `created_at`, `versao_fila`, `linhas`. Sem o conteúdo do CSV.

| Rota | Quem | Efeito |
|---|---|---|
| `POST /solicitacoes/{sid}/contestacao` `{motivo}` | médico ou admin do caso | cria contestação `em_reavaliacao`; 409 se já houver uma aberta |
| `POST /solicitacoes/{sid}/contestacao/conclusao` `{justificativa}` | médico ou admin do caso | conclui com `posicao_mantida` |
| `POST /propostas` | já existente | se houver contestação aberta, conclui com `nova_proposta` |
| `GET /fila/exportacao.csv` | admin (tudo) ou médico (seus casos) | CSV `solicitacao_id,posicao,justificativa` e registro em `exports` |

`QueuePatient` ganha `justificativa` opcional (até 2000 caracteres). `GET /fila`
acrescenta `em_reavaliacao` a cada solicitação.

## Decisões

| Decisão | Alternativas consideradas | Motivo |
|---|---|---|
| Concluir pela nova proposta ou manualmente | Reanálise automática pela IA | O tribunal exige evidência aprovada; a spec deixa reanálise automática fora. |
| `csv` da biblioteca padrão | Montar texto à mão | Escapa vírgula, aspas e quebra de linha corretamente. |
| Médico exporta só seus casos | Médico exporta tudo | Mantém o princípio de acesso por necessidade. |

## Riscos

- Fila importada sem justificativa gera coluna vazia: o importador deve copiar a justificativa de `fila_priorizada.csv`.
