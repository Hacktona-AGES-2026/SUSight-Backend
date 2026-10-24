# Plano: Tratamento do dataset

Spec: ./spec.md
Status: aprovado para implementação pelo usuário em 2026-10-24

## Abordagem

Pipeline Python executável por linha de comando, independente da API e do tribunal. Usar biblioteca padrão para CSV, JSON, datas, hashes e estatísticas; pytest nos testes. O volume atual não exige um banco nem processamento distribuído.

Comando proposto, após instalação do pacote: `python -m susight.dataset --input-dir /caminho/dataset --output-dir /caminho/tratado`. A referência padrão é `2026-10-23`; uma referência diferente deve ser explícita e registrada. Diretórios de entrada e saída não podem se sobrepor.

Etapas, nesta ordem:

1. Ler os três CSVs como UTF-8, tolerando BOM; preservar células originais como texto e identificar arquivo e linha. Registrar SHA-256 dos arquivos e versão das regras. README e dicionário são referências obrigatórias de proveniência.
2. Validar estrutura, unicidade dos IDs e tipos. Repetição de ID com conteúdo idêntico pode ser reduzida com proveniência; conteúdo conflitante é erro estrutural. Uma execução inválida gera diagnóstico e código de saída diferente de zero, sem publicar dados utilizáveis.
3. Normalizar categorias e CIDs, associar catálogo, validar domínios e recalcular espera. CID sintaticamente válido não significa validação de diagnóstico. Manter original, normalizado e problemas por campo.
4. Extrair indícios dos textos de solicitações e eventos, com regras versionadas, antes de avaliar compatibilidade e exclusões. Guardar trechos e posições no texto original.
5. Detectar grupos de possíveis duplicatas e produzir o mapa original → canônica, usando as regras conservadoras abaixo.
6. Deduplicar eventos pelo conteúdo completo, exceto ID, antes de redirecionar aliases. Validar paciente, separar órfãos e classificar histórico, durante a espera e futuro. Eventos distintos nas fontes não são fundidos apenas porque agora apontam à mesma canônica.
7. Reunir evidências e aplicar exclusões explícitas. Calcular estados de cobertura e pendências, sem inferir retomada apenas pela existência de um exame posterior.
8. Calcular medianas a partir de um conjunto fixo de canônicas ativas com medidas observadas válidas e sem impedimentos de uso. Aplicar imputações em uma segunda passagem, sem recalcular a população. Manter seus IDs no registro da imputação.
9. Gerar dados, relatório e `DECISOES.md`; reconciliar solicitações e eventos. Escrever em diretório temporário irmão e publicar por renomeação para destino novo. Não sobrescrever uma versão existente silenciosamente.

## Dados e interfaces

Arquivos propostos, todos ordenados por identificadores para reprodução:

| Saída | Conteúdo principal |
|---|---|
| `solicitacoes.jsonl` | Uma canônica por linha: IDs, aliases, valores originais e normalizados, medidas para pontuação, estado, avisos, evidências e imputações. Inclui excluídas e pendentes, distinguíveis pelo estado. |
| `eventos.jsonl` | Evento tratado, IDs de origem, solicitação original e canônica, paciente, data, tipo, resultado, valor, descrição, origem, elegibilidade temporal e situação do vínculo. Inclui órfãos identificados. |
| `cobertura.csv` | Uma linha por solicitação original: `solicitacao_id`, `solicitacao_canonica_id`, `estado`, `motivo`, `evidencias_ids`. |
| `evidencias.jsonl` | `evidencia_id`, IDs relacionados, arquivo, linha, campo, trecho, início/fim, regra, versão, polaridade e natureza: clínica documentada, relato ou indício textual. |
| `qualidade.json` | Contagens reconciliadas, falhas por tipo, revisão, exclusões, consolidações, órfãos e imputações. |
| `manifesto.json` | Referência, hashes de entrada e regras, versões de formato e aplicação, data/hora UTC da execução e hashes das saídas. |
| `DECISOES.md` | Regras utilizadas e tabela de consolidações/exclusões com IDs e evidências; limites do tratamento. |

JSON usa `null` para desconhecido, booleanos para fatos derivados válidos e listas para proveniência. Campos originais vazios continuam `""`. Datas são `AAAA-MM-DD`; metadados de execução usam ISO 8601 em UTC. CSV usa vírgula e UTF-8. `evidencias_ids` é uma lista JSON dentro da célula CSV.

IDs derivados são hashes estáveis do conteúdo e da origem, sem horário da execução. O manifesto não inclui seu próprio hash. Horário e hash do manifesto ficam fora da comparação de reprodução substantiva.

### Compatibilidade de duplicatas

- Exigir mesmo paciente, procedimento e CID principal normalizado válido. Avaliar todas as solicitações do grupo entre si; compatibilidade por encadeamento não basta.
- Normalizar apenas formatação para comparar descrições. Lateralidades ou episódios explicitamente diferentes, ou indícios de nova indicação após encerramento, impedem consolidação. Bilateralidade não é assumida equivalente a uma lateralidade isolada.
- Contexto insuficiente ou não reconhecido para confirmar equivalência mantém o grupo separado para revisão. Ausência de um termo de conflito não comprova compatibilidade.
- Regras positivas de equivalência devem ser enumeradas em `rules.json` e cobertas por exemplos; não criar uma heurística clínica genérica.
- Selecionar canônica por `(data_entrada_fila, solicitacao_id)`. Data inválida impede consolidação automática. Preservar valores de todas as fontes; diferenças em medidas não viram média nem seleção automática do maior valor. Se a medida necessária não puder ser resolvida, sinalizar pendência para pontuação, sem tratá-la como simples ausência.
- Estado `consolidada` pertence ao alias; a canônica tem seu próprio estado. A soma de ativas, consolidadas, excluídas e pendentes deve ser igual ao número de solicitações originais únicas.

### Texto, exclusões e sinais clínicos

- Regras descrevem conceito, expressões, contexto, negações e marcadores de incerteza. Uma correspondência textual é um indício; não é um diagnóstico. Negação ambígua gera revisão.
- Reconhecer variantes inequívocas de termos já documentados no dataset, preservando o trecho original. Expandir abreviações só por dicionário explícito; termos desconhecidos permanecem disponíveis no texto.
- Desistência e cirurgia em outro serviço precisam de afirmação inequívoca, vínculo com a solicitação e ausência de contradição. Futuro, desejo, hipótese e negação impedem exclusão automática. Evidência futura à referência não decide exclusão dessa versão.
- Um conflito entre registros sobre encerramento mantém a canônica ativa com revisão. Impedimentos independentes de uso podem colocá-la pendente. O motivo registra essa distinção.
- Manter `oncologico_por_cid` separado de biópsia positiva e de flags. Não reescrever CID. Guardar sinais usados pelo verificador oficial com a origem; a pontuação decide a trava e a classificação final de urgência.

### Medianas e valores ausentes

- ASA e limitação são ordinais: ordenar valores observados e usar o elemento central; em população par, usar o central superior. Esta é uma mediana ordinal que preserva o domínio e precisa ficar identificada como convenção de imputação.
- Dor, também inteira no dicionário, usa a mesma convenção. Distância usa mediana aritmética, podendo resultar em decimal. Nunca arredondar um dado observado para torná-lo válido.
- Limitação usa a ordem `nenhuma < leve < moderada < grave`. A representação original continua textual.
- Não havendo população válida na especialidade, não recorrer à mediana global. Registrar a medida ausente e a pendência.
- Nenhuma imputação altera fatos clínicos, fundamenta exclusão ou comprova que um caso é sem urgência.

## Decisões

| Decisão | Alternativas consideradas | Motivo |
|---|---|---|
| Python com biblioteca padrão | pandas, banco de dados | Volume pequeno, tipos e ausências explícitos e execução independente do setup da API. |
| JSONL para dados e CSV para cobertura | Um CSV largo | JSONL preserva listas de evidências, aliases, valores originais e campos nulos sem achatar relações. |
| Consolidação conservadora | Agrupar automaticamente por paciente/procedimento | Evita confundir episódios, lateralidades e indicações distintas. |
| Mediana ordinal superior | Média dos dois centrais, arredondamento implícito | Mantém categorias válidas e torna a convenção reproduzível. |
| Erro estrutural bloqueia publicação | Publicar linhas restantes | Evita apresentar uma versão parcial como tratamento completo. |
| Dados externos e saídas fora do controle de versão | Copiar o Downloads para o repositório | A CLI recebe caminhos portáveis; fixtures pequenas e sintéticas entram nos testes. |

## Verificação

Testes por regra com fixtures sintéticas: consolidação positiva e negativa, aliases com evidência clínica, lateralidades/episódios, eventos órfãos e divergência de paciente, duplicatas de eventos, datas anteriores e futuras, texto negado/incerto, exclusões e retomadas contraditórias, flag versus CID, medianas ordinais e ausência total na especialidade.

Teste de integração com a pasta fornecida: confirmar 941 solicitações, 1.505 eventos e 23 procedimentos na entrada, reconciliar todas as saídas e conferir que a entrada conserva seus hashes. Os 22 grupos candidatos, 6 eventos repetidos e 9 órfãos são referências de diagnóstico; não metas de exclusão ou consolidação. Rodar duas vezes em destinos diferentes e comparar conteúdo substantivo e IDs.

O verificador oficial exige a fila já ordenada e será executado depois da pontuação. Nesta etapa, verificar que IDs canônicos pertencem à entrada e que toda ausência futura no CSV será explicável pela cobertura.

## Riscos

- Texto livre pode conter negação ou referência a outro episódio: regras conservadoras, exemplos negativos e revisão dos casos não reconhecidos.
- Imputação pode esconder incerteza: manter original, população e valor aplicado separados e sinalizar incompletude à pontuação.
- Consolidação pode mover evidências para outro contexto: exigir compatibilidade de todo o grupo, preservar aliases e não transferir entre procedimentos.
- Mudança de contrato afeta a spec 002: versionar formatos e documentar as medidas disponibilizadas, mantendo SWALIS e ROR na etapa seguinte.

## Dependências e aprovação

Spec aprovada pelo usuário em 2026-10-24. Plano e convenção de mediana ordinal autorizados no pedido de implementação de todas as specs. Não depende de LLM, FastAPI ou definição de pesos.

## Organização executada

Passos implementados em `dataset/core.py` (leitura, validação, normalização, texto e consolidação), `dataset/pipeline.py` (eventos, atividade, imputação e publicação) e `dataset/__main__.py` (CLI). Evidências da execução e limites em `../../docs/backend-validation.md`.

## Complemento autorizado em 2026-10-24

Implementar identidades com permissões por paciente, registro documental com evidência e revisão auditável, retenção máxima de sete dias e bloqueio de tentativas quando referências perderem validade. Tokens de acesso são individuais e carregados da configuração local; decisões usam identidade autenticada. A integração documental registra fonte/trecho/valor e aprovação, sem implementar OCR nem chamar Gemini nesta etapa. Dados aprovados são comparados ao registro do servidor; o cliente não pode declarar aprovação por conta própria. Limpeza abrange conteúdo dependente, relatórios e arquivos gerados em diretórios registrados, preservando originais. Testes usam relógio injetado. Atualizar documentação e verificar todos os critérios técnicos; revisão clínica não é fabricada.
