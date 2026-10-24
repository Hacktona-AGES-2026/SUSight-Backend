# Validação técnica — 2026-10-24

Escopo: tratamento, pontuação, permissões, retenção e integração da proveniência
com o tribunal. Não houve chamada real a Gemini nem alteração do adaptador do provedor.
Upload/OCR e extração automática continuam na feature documental separada.

## Limite após a revisão de requisitos

Os resultados abaixo correspondem ao modelo anterior à orientação clínica recebida em 2026-10-24. Esse modelo inclui espera na pontuação, no desempate e em travas. Os 62 testes e o CSV aceito não comprovam atendimento ao novo requisito de remover a espera. A revisão está em [registro clínico](clinical-review-2026-10-24.md) e requer adaptação e nova aceitação.

## Evidências executadas

- **62 testes automatizados passaram** localmente; análise e formatação Ruff aprovadas.
- Testes cobrem permissões por papel/paciente, referências adulteradas ou não aprovadas,
  revisão auditável, cancelamento, expiração durante análise, migração de banco antigo,
  limpeza segura de arquivos e geração de tokens individuais sem exposição dos valores.
- Integração sintética de teste passa no verificador oficial original do desafio.
- `tools/acceptance.py` executou a **base inteira** sem LLM e o verificador retornou
  **OK — regra de ouro respeitada e formato válido**, código de saída 0.
- Três execuções de aceitação geraram o mesmo CSV, relações, função representativa e
  decisões. A última execução conferiu a origem de cada uma das 16 exclusões.
- Os hashes de todos os arquivos originais permaneceram intactos.

| Medida | Resultado |
|---|---:|
| Solicitações originais | 941 |
| Eventos originais | 1.505 |
| Procedimentos | 23 |
| Solicitações ativas / posições no CSV | 925 |
| Exclusões com fonte conferida | 16 |
| Consolidações automáticas | 0 |
| Grupos candidatos a duplicata | 22 (44 solicitações) |
| Eventos repetidos / órfãos | 6 / 9 |
| Imputações | 103 |
| Chamadas de IA na aceitação | 0 |

O aviso do verificador sobre as 16 ausências é esperado e explicado no `DECISOES.md`.
Cada exclusão aponta para afirmação textual inequívoca ou evento de encerramento na
espera atual. Encerramento histórico não encerra automaticamente a nova entrada.
Essa é uma conferência técnica de documentos sintéticos, não uma assinatura médica.
Os 22 grupos de possível duplicidade permanecem ativos e sinalizados porque a
equivalência positiva não foi comprovada; não são uma meta de exclusão.

## Conflito de modelagem resolvido tecnicamente

Na versão anterior, a utilidade aditiva podia exigir que um caso sem urgência
precedesse um oncológico. Não se tentou corrigir a contradição alterando pesos até
passar no verificador. A spec e o plano foram atualizados para aplicar uma hierarquia
rígida antes da ROR: grupo protegido antes de sem urgência.

A comparação por pesos é feita dentro do grupo. Entre grupos, a relação publicada
tem origem `hierarquia_regra_de_ouro`, sem extremos de utilidade. Comparações de
referência contrárias à hierarquia e restrições inviáveis continuam sendo rejeitadas.
Há regressão automatizada para o caso em que a utilidade isolada favorece o caso calmo.

A configuração demonstrativa registra swings 100/90/80/70/60/40/20, faixas normalizadas
de 75%–125% e dez pares dominantes dentro dos grupos. Esses números são hipóteses
explícitas de protótipo, não pesos atribuídos a SWALIS/WCWL/CPAC ou validados por médico.

## Permissões, evidência e expiração

- Identidades locais individuais, configuradas fora da API; pacientes e médicos veem
  apenas os casos atribuídos. Administrador faz importação com autoria registrada.
- Proposta usa IDs; o servidor busca a evidência aprovada, confere caso e validade e
  rejeita conteúdo divergente, inexistente ou ainda não aprovado. A fonte tem hash,
  formato, tamanho e página; a revisão guarda identidade, data e justificativa.
- Fonte, evidência, fila, proposta e decisão têm validade limitada. Propostas herdam
  o menor prazo entre suas dependências; tentativas não renovam o prazo.
- Expiração ou cancelamento durante uma chamada impede publicação/reativação pelo retorno.
- Limpeza apaga conteúdo e dependências; arquivos gerados têm permissões 0700/0600 e
  só são removidos quando o manifesto os identifica como saída temporária expirada.
- Fontes imutáveis e alvos de links simbólicos são preservados. Manter manutenção
  ativa é requisito operacional; não se promete apagamento forense ou de backups externos.

## Como reproduzir

```sh
uv sync --locked --no-editable --extra dev
uv run --no-sync pytest -q
uv run --no-sync python tools/acceptance.py \
  --dataset /caminho/dataset --output-root outputs/aceitacao-nova
```

A saída inclui `pontuado/fila_priorizada.csv`, `DECISOES.md`, preferências, relações,
`aceitacao.json` com as fontes das exclusões e os 44 candidatos mantidos para revisão.
O diretório de saída precisa ser novo. Os relatórios gerados não são versionados.

## Pendências humanas e escopo excluído

- Validar clinicamente escalas de SWALIS, comorbidades, deterioração e preferências
  de swing antes de qualquer uso real. A aceitação aqui é técnica e sintética.
- O responsável da equipe ainda precisa dar aceite às exclusões e aos casos ambíguos;
  não se fabrica essa aprovação como resultado de um teste automatizado.
- O teste real do Gemini foi explicitamente excluído desta solicitação e não foi executado.
- O hash do documento é registrado pelo sistema que possui o arquivo. Este fluxo não
  comprova sozinho os bytes originais nem implementa upload, OCR ou leitura de laudos.
- Papéis locais não comprovam identidade gov.br/CRM. O serviço usa um único worker.

Advertências de depreciação das dependências Starlette/httpx e Google GenAI em Python
3.14 não impediram os testes; CI usa Python 3.12. Aprovar o PR não equivale à validação
clínica dos parâmetros ou dos textos produzidos por um provedor.
