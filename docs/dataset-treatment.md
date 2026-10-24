# Tratamento do dataset

CLI: `python -m susight.dataset --input-dir ENTRADA --output-dir SAIDA`.
A referência padrão é 2026-10-23; `--reference AAAA-MM-DD` permite outra referência
explícita, registrada no manifesto. A saída deve ser nova e não pode conter nem
estar dentro da entrada.

## Arquivos

- `solicitacoes.jsonl`: canônicas, originais, medidas observadas/preparadas, aliases,
  avisos, pendências, eventos e imputações com população de referência.
- `eventos.jsonl`: todos os eventos únicos, inclusive órfãos e inválidos, identificados.
- `evidencias.jsonl`: fontes, trechos, posições no original, regras e polaridade.
- `cobertura.csv`: cada solicitação original, estado, motivo e canônica.
- `qualidade.json`: reconciliação e contagens.
- `manifesto.json`: hashes das entradas/saídas, regras e instante de execução UTC.
- `DECISOES.md`: regras e exclusões/consolidações com referências de evidências.

CIDs são normalizados para comparação, sem alteração do diagnóstico original. CID
secundário já registrado pode documentar comorbidade por mapeamento explícito.
Menções em texto são indícios; negação e incerteza permanecem identificadas. A
extração usa padrões conservadores, não compreensão clínica completa de linguagem.

Duplicatas exigem mesmo paciente, procedimento, CID, medidas e contexto clínico
reconhecido com textos normalizados iguais. Episódios ou contextos diferentes ficam
separados com aviso. Essa estratégia pode deixar duplicatas verdadeiras para revisão.
Eventos equivalentes são deduplicados antes de redirecionar aliases; preservam todos
os IDs. Eventos anteriores à entrada são histórico; posteriores à referência não
alimentam fatos derivados da versão.

Exclusões exigem desistência/cirurgia realizada inequívoca sem contradição. Contato
sem resposta e falta nunca excluem automaticamente. Exclusões são propostas de
preparação do dataset sintético, sem alteração de uma fila operacional.

Medianas por especialidade usam apenas observações válidas de canônicas ativas,
sem imputação em cascata. ASA, dor e limitação usam o elemento central superior;
distância usa mediana aritmética. Sem população válida, fica pendência.

## Organização do código

`dataset/core.py` reúne leitura, validação, normalização, extração e consolidação.
`dataset/pipeline.py` integra eventos, atividade, imputações e publicação dos
relatórios. `rules.json` versiona padrões; `__main__.py` expõe a CLI. São os passos
do plano agrupados em módulos, sem dependência da API nem de LLM.
