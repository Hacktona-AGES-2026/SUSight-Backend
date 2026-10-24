# Plano: Exames pedidos pelo médico

Spec: ./spec.md
Status: em revisão

## Abordagem

Tabela `exam_requests` no SQLite do `Store`, sem expiração. Os pedidos nascem na
mesma transação da decisão `pedir_informacoes` e mudam de situação nas operações que
já existem: registro de documento, registro de evidência e revisão de evidência.

## Dados e interfaces

**`exam_requests`**: `id`, `sid`, `paciente_id`, `proposal_id`, `exame`, `explicacao`,
`actor`, `created_at`, `status` (`pendente` | `recebido` | `em_analise` | `atendido`),
`document_id`, `updated_at`.

| Operação | Efeito no pedido |
|---|---|
| `POST /propostas/{id}/decisao` com `pedir_informacoes` e `exames` | cria um pedido `pendente` por exame |
| `POST /documentos` com `pedido_id` | `pendente` → `recebido`; evento `exame_recebido` na trilha |
| `POST /evidencias` sobre o documento ligado | `recebido` → `em_analise` |
| `POST /evidencias/{id}/revisao` sobre o documento ligado | `em_analise` → `atendido` |

Entradas novas: `Decision.exames` (lista de `{exame, explicacao}`, até 10) e
`DocumentInput.pedido_id` (opcional).

**Rota**: `GET /solicitacoes/{sid}/exames-pedidos` devolve `pedidos` (mais recente
primeiro, com `pedido_id`, `exame`, `explicacao`, `situacao`, `responsavel`, `data_hora`)
e `pendentes` (contagem para o widget). A permissão usa o `paciente_id` do pedido ou,
sem pedidos, o da fila ativa.

## Decisões

| Decisão | Alternativas consideradas | Motivo |
|---|---|---|
| Um pedido por exame | Um pedido com lista | Cada exame tem sua situação e seu documento. |
| Situação avançada pelas operações existentes | Endpoint para mudar situação | Ninguém altera o pedido à mão; o estado acompanha os fatos. |
| Sem reabrir a proposta | Reabrir automaticamente | O tribunal exige evidência aprovada; o médico cria nova proposta. |

## Riscos

- Quando a extração automática (spec 001) existir, `em_analise` e `atendido` passam a seguir o estado da extração: revisar este plano.
