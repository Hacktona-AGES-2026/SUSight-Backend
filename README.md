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

A configuração em `examples/preferences-demo.json` contém escores de swing e faixas
**demonstrativas**, sem validação clínica nem atribuição de percentuais à literatura.
A política `priorizacao-sem-espera-v1` remove espera de pesos, desempates e travas.
A hierarquia rígida é aplicada antes da ROR; a base inteira gerou 925 posições e
passou no verificador oficial. Ver [validação](docs/backend-validation.md).

Para reproduzir a aceitação técnica, sem chamadas de IA:

```sh
uv run --no-sync python tools/acceptance.py \
  --dataset /caminho/dataset --output-root outputs/aceitacao-nova
```

Para a API, criar identidades e copiar `.env.example` para `.env`:

```sh
uv run --no-sync python -m susight.provision --directory data/identidades --patient PAC-EXEMPLO
```

Os tokens individuais ficam em arquivos privados e não são impressos. Os vínculos
de paciente devem corresponder à fila importada.

Para login com senha (spec 007), criar contas de demonstração. A senha provisória
é gerada e gravada só no arquivo indicado, com permissão 0600:

```sh
uv run --no-sync python -m susight.accounts --database data/susight.sqlite3 \
  --id PAC-EXEMPLO --papel paciente --paciente PAC-EXEMPLO --senha-arquivo data/identidades/PAC-EXEMPLO.senha
```

Depois iniciar o serviço:

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
3. Importar a fila válida pela API, registrar e revisar as fontes/evidências e criar propostas usando seus IDs aprovados.
4. Consultar o parecer; o médico decide, e o servidor revalida versão e travas antes de aplicar.

Detalhes: [tratamento](docs/dataset-treatment.md), [pontuação](docs/queue-scoring.md),
[API e tribunal](docs/backend-api.md), [validação e pendências](docs/backend-validation.md).

## Desenvolvimento orientado a especificações

Specs em `specs/001-tribunal-de-ias`, `specs/002-pontuacao-da-fila` e
`specs/003-tratamento-do-dataset`. Princípios em `specs/constitution.md` e fluxo em
`docs/sdd/MANUAL.md`. Commits atômicos; PRs para `dev`; merge exige revisão humana.

Análise descritiva ASA × porte, com ASA observado e sensibilidade de duplicatas:

```sh
uv run --no-sync python -m susight.scoring.analysis \
  --dataset /caminho/dataset --treated /caminho/tratado --output outputs/analise-nova
```

Critérios e pesos clínicos permanecem para revisão conforme o
[roteiro de elicitação](docs/clinical-elicitation.md). BRAN e termo antes do upload
estão planejados nas specs vinculadas, sem nova chamada de IA nesta entrega.
