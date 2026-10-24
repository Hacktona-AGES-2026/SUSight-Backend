# SUSight Backend

Tratamento rastreável do dataset, pontuação com Robust Ordinal Regression e tribunal
consultivo (agente a favor, agente contra, agente imparcial e juiz). A aplicação só altera a fila após decisão médica explícita.

## Entrega do desafio

- [DECISOES.md](DECISOES.md): abordagem, usuário, motivos, o que ficou de fora de propósito e pendências.
- [fila_priorizada.csv](fila_priorizada.csv): a fila ordenada (`solicitacao_id`, `posicao`, `justificativa`), gerada pela `dev` e aprovada pelo verificador oficial. Parametrização demonstrativa, sem validação clínica.

## Rodar a demonstração do zero (máquina limpa)

O sistema tem três repositórios: este backend, o [web do médico](https://github.com/Hacktona-AGES-2026/SUSight-Web) e o [app do paciente](https://github.com/Hacktona-AGES-2026/SUSight) (pasta `app/`). O `dataset.zip` do desafio fica fora do repositório.

1. **Backend e fila oficial** (Python 3.11+ e [uv](https://docs.astral.sh/uv/)):

```sh
uv sync --locked --no-editable --extra dev
export PYTHONPATH=src            # usa o código desta pasta, não a cópia instalada
uv run --no-sync python -m susight.dataset --input-dir /caminho/dataset --output-dir /tmp/tratado
uv run --no-sync python -m susight.scoring --input-dir /tmp/tratado \
  --preferences examples/preferences-demo.json --output-dir /tmp/pontuado     # ~2 min
uv run --no-sync python tools/import_dataset_queue.py --queue /tmp/pontuado/fila.json \
  --database data/dataset.sqlite3 --treated /tmp/tratado \
  --procedures /caminho/dataset/procedimentos.csv --events /caminho/dataset/eventos_clinicos.csv \
  --model /tmp/pontuado/funcao_representativa.json
```

2. **Chave do Gemini**, em um `.env` ignorado pelo git (sem ela o documento fica só "recebido" e nada é reavaliado):

```sh
GEMINI_API_KEY=<sua chave>
GEMINI_MODEL=gemini-3.5-flash-lite
SUSIGHT_DATABASE=data/dataset.sqlite3
SUSIGHT_API_TOKEN=<16+ caracteres>
```

3. **Subir a API** (`--host 0.0.0.0` só para o celular alcançá-la na mesma rede Wi-Fi):

```sh
uv run --no-sync --env-file .env uvicorn susight.api:create_app --factory --host 0.0.0.0 --port 8000 --workers 1
```

4. **Web do médico**: no repositório `SUSight-Web`, `pnpm install` e `NEXT_PUBLIC_DATA_SOURCE=api BACKEND_URL=http://127.0.0.1:8000 pnpm dev` (http://localhost:3000).
5. **App do paciente**: no repositório `SUSight`, `cd app && npm install && EXPO_PUBLIC_API_URL=http://<IP do computador>:8000 npx expo start`.

Contas da importação: médico `medico-demo` / `demo1234`; paciente do app, CPF `529.982.247-25` e código `123456` (Pedro Freitas Medeiros, posição 794). Para ver a subida de posição, envie pelo app o laudo fictício [`docs/demo/laudo-pedro-freitas-medeiros.pdf`](docs/demo/laudo-pedro-freitas-medeiros.pdf): em segundos a proposta aparece em **Revisões** no web, com os votos do tribunal e o juiz. A fila só muda quando o médico aprova. O banco expira em 7 dias; para repetir a demonstração, apague `data/dataset.sqlite3` e importe de novo.

Para uma fila pequena e sintética, sem dataset: `uv run --no-sync python tools/seed_demo.py --database data/demo.sqlite3` (propostas pré-prontas, com um tribunal falso **só para demonstração local**).

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
A hierarquia rígida (grupo protegido antes do sem urgência e, dentro dele, classe
SWALIS A1 → D) é aplicada antes da ROR; a base inteira gerou 925 posições e
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
