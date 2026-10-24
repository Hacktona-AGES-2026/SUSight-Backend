# SUSight Backend

Tratamento rastreável do dataset, pontuação com Robust Ordinal Regression e tribunal
consultivo de três agentes. A aplicação só altera a fila após decisão médica explícita.

## Executar

Python 3.11+ e [uv](https://docs.astral.sh/uv/).

```sh
uv sync --locked --no-editable --extra dev
uv run --no-sync pytest -q
uv run --no-sync ruff check src tests
```

Tratar o dataset externo, mantendo os originais intactos:

```sh
uv run --no-sync python -m susight.dataset \
  --input-dir /caminho/dataset --output-dir /caminho/tratado
```

Pontuar com faixas de pesos, escalas e 10–20 comparações documentadas:

```sh
uv run --no-sync python -m susight.scoring \
  --input-dir /caminho/tratado \
  --preferences /caminho/preferencias.json --output-dir /caminho/pontuado
uv run --no-sync python tools/verificar_fila_priorizada.py \
  /caminho/pontuado/fila_priorizada.csv --dataset /caminho/dataset
```

A configuração em `examples/preferences-demo.json` usa IDs do dataset sintético
fornecido e premissas **demonstrativas**. Não representa pesos extraídos de literatura
nem elicitação validada. No dataset completo ela revela um conflito com a regra de
ouro, documentado em [validação](docs/backend-validation.md); a exportação é bloqueada.

Para a API, copiar `.env.example` para `.env`, configurar token e, para chamadas reais,
`GEMINI_API_KEY` e `GEMINI_MODEL`:

```sh
uv run --no-sync --env-file .env uvicorn susight.api:create_app \
  --factory --host 127.0.0.1 --port 8000 --workers 1
```

Contratos em `/docs`. Rotas clínicas exigem `Authorization: Bearer <token>`.
O processamento em segundo plano e a recuperação de propostas usam SQLite e um
único processo da API. Sem provedor configurado, o tribunal registra indisponibilidade
 e tenta novamente; nunca substitui o parecer por resposta simulada.

## Fluxo

1. Tratar o dataset e revisar pendências/exclusões em `DECISOES.md`.
2. Definir e validar as preferências; gerar a fila apenas se as restrições forem compatíveis.
3. Importar a fila válida pela API; criar propostas de casos incertos ou conflitantes.
4. Consultar o parecer; o médico decide, e o servidor revalida versão e travas antes de aplicar.

Detalhes: [tratamento](docs/dataset-treatment.md), [pontuação](docs/queue-scoring.md),
[API e tribunal](docs/backend-api.md), [validação e pendências](docs/backend-validation.md).

## Desenvolvimento orientado a especificações

Specs em `specs/001-tribunal-de-ias`, `specs/002-pontuacao-da-fila` e
`specs/003-tratamento-do-dataset`. Princípios em `specs/constitution.md` e fluxo em
`docs/sdd/MANUAL.md`. Commits atômicos; PRs para `dev`; merge exige revisão humana.
