# Plano: revisão clínica da pontuação da fila

Spec: ./spec.md
Issue: Hacktona-AGES-2026/SUSight#6
Status: autorizado pelo usuário para implementação técnica em 2026-10-24; decisões clínicas pendentes
Data: 2026-10-24

## Objetivo e limite desta entrega

Adaptar a pontuação à decisão de que tempo de espera não tem relevância, preparar
uma revisão verificável de CID/fatores de risco e ASA × porte e repetir a aceitação
técnica. A revisão clínica está em [registro de origem](../../docs/clinical-review-2026-10-24.md).
Este plano substitui o plano anterior; sua elaboração não aprova os pesos nem
implementa as mudanças. A retirada da espera já foi implementada; resultados estão em `../../docs/backend-validation.md`.

BRAN e termo no upload são dependências de outras specs, com entregas descritas
abaixo. Extração/OCR, escolha de LLM e chamadas reais a Gemini continuam fora desta
execução. Integrações com GERCON, GERINT ou Telessaúde não serão presumidas.

## Decisões e questões a resolver

| Tema | Situação | Consequência |
|---|---|---|
| Espera na prioridade | Decidido pelo usuário: retirar totalmente | Sem peso, desempate, dominância, trava ou seleção de pares baseada em antiguidade. |
| Datas e histórico | Preservar | Necessários para auditoria, validade e deterioração documentada; não dão preferência por tempo decorrido. |
| Modelo ROR | Preservar arquitetura existente | Atualizar o domínio de critérios e preferências; manter hierarquia explícita. |
| CID e fatores de risco | Importância relatada; representação e faixas pendentes | Preparar casos e proposta de critérios para revisão clínica, sem percentuais inventados. |
| ASA × porte | Análise descritiva primeiro | A relação não preenche ASA ausente nem vira peso automaticamente. |
| ASA maior implica maior prioridade | Premissa antiga em revisão | A manutenção num protótipo deve ser rotulada demonstrativa; adoção clínica depende de decisão explícita. |
| Sequência câncer → cardiovascular → trauma → M | Hipótese relatada | Não criar ranking universal pela letra do CID. |
| BRAN | Requisito do tribunal em revisão | Adaptar Contestação, mantendo três agentes e decisão médica. |
| Termo | Requisito documental em revisão | Definir conteúdo, versão e fluxo antes de implementar o recebimento de arquivos. |

## Etapa 1 — remover a espera de ponta a ponta

Responsável: Backend. Depende da revisão da spec e deste plano pela equipe.

1. Em `src/susight/scoring/engine.py`, retirar `espera` de `CRITERIA`, das funções
   de valor e da preparação dos critérios. Neste primeiro incremento, o contrato
   demonstrativo tem seis critérios: limitação, ASA, dor, comorbidades,
   deterioração e distância. Isso não encerra a revisão clínica desses critérios.
2. Calcular dimensões, contribuições e exportação a partir de `len(CRITERIA)`;
   retirar o intervalo fixo de 14 incrementos. Com seis critérios e dois segmentos
   por critério, o modelo demonstrativo passa a ter 12 incrementos.
3. Remover desempate por dias e arestas de dominância condicionadas a espera em
   `order_queue`. Usar hierarquia, utilidade representativa, relações necessárias
   e ID estável. Não substituir dias por data de entrada, posição antiga ou índice
   de entrada como preferência implícita.
4. Retirar a trava `prioridade_maior_e_mais_espera` de
   `src/susight/tribunal/guards.py`. Preservar regra oncológica, hierarquia e limite
   de elevação. Conferir importação, proposta, processamento e decisão para usar
   as mesmas regras revisadas.
5. Atualizar `tools/acceptance.py`: remover swing de espera, limites posicionais
   dependentes dos sete critérios e escolha de pares por diferença de espera.
   Selecionar pares sintéticos por dominância estrita em critérios ativos dentro
   do mesmo grupo, com IDs únicos e ordem determinística. Se não houver dez pares,
   registrar a insuficiência; não fabricar referências.
6. Reescrever justificativas para distinguir contexto administrativo de motivos
   de prioridade. SWALIS, se mantido para acompanhamento, não alimenta a utilidade,
   o desempate, as travas ou as comparações de referência.

Saída: algoritmo e travas sem preferência temporal, regressões passando e
configuração demonstrativa nova, identificada como tal. Não exigir validação de
pesos clínicos para testar que a espera deixou de influenciar o modelo.

## Etapa 2 — analisar ASA × porte e cobertura dos fatores de risco

Responsável: Backend; interpretação posterior pelos responsáveis clínicos.
Pode ocorrer em paralelo à etapa 1 após revisão do plano.

- Vincular solicitações tratadas a `procedimentos.csv` por `procedimento_id` e
  conferir correspondência de especialidade, porte e cobertura. Não alterar fontes.
- Produzir tabelas de contagem e proporções de ASA por porte e especialidade, com
  denominadores, ausências, valores incompatíveis e procedimentos sem vínculo.
  Usar ASA observado na análise principal; imputados aparecem separadamente.
- Unidade principal: solicitação ativa canônica. Como ainda existem grupos de
  duplicidade não resolvidos, não chamá-las de pacientes independentes. Apresentar
  análise de sensibilidade sem os grupos suspeitos, sem excluí-los da fila.
- Inventariar CID principal/secundário, comorbidades, fatores de risco e eventos:
  origem, confirmação, negação, suspeita, conflito e ausência. Separar fator de
  risco de diagnóstico confirmado e evitar dupla contagem do mesmo fato.
- Guardar relatório agregado em português, sem nomes/CNS, e artefatos temporários
  sob a política de retenção existente. Contagens não sustentam causalidade.

Saída: relatório descritivo reprodutível e conjunto de casos sintéticos para
elicitação. Não produzir peso de prioridade a partir de uma correlação isolada.

## Etapa 3 — fechar os critérios e recalibrar preferências

Responsáveis: equipe clínica para interpretação; Backend para formalização.
Depende da etapa 2. Alterações de comportamento voltam primeiro à spec.

1. Revisar a premissa de monotonicidade da ASA e a função do porte. Decidir se
   entram na prioridade, na contextualização de risco ou na revisão de indicação.
   Até essa decisão, não apresentar a escala antiga como clinicamente validada.
2. Definir como representar gravidade associada ao CID e fatores de risco sem
   usar somente capítulo do CID, sem inferir diagnóstico e sem contar o mesmo
   risco novamente em comorbidades, ASA e deterioração.
3. Definir limites das escalas e suas fontes antes do swing. Registrar exceções,
   dados ausentes e quando exigir revisão. Sem fonte suficiente, registrar pendência.
4. Elicitar faixas/relações de peso e 10–20 comparações de referência com motivo,
   fonte, data, versão e responsável. Confirmar que a escolha dos pares não usa
   antiguidade. Não converter uma ordem verbal em percentuais automaticamente.
5. Conferir viabilidade das restrições. Conflitos retornam para revisão com IDs;
   não afrouxar regras silenciosamente para conseguir uma fila.

Saída: spec e preferências revisadas. Preferências demonstrativas permanecem
separadas das validadas. Só renormalizar pesos antigos não satisfaz esta etapa.
A exclusão antiga de elicitação com profissionais na spec deve ser revista quando
a equipe autorizar essa etapa; este plano não presume essa autorização clínica.

## Etapa 4 — consolidar modelo e compatibilidade

Responsável: Backend. Depende das decisões da etapa 3 para o modelo clínico;
a versão sintética de seis critérios pode ser verificada antes.

- Preservar funções marginais aditivas lineares por partes com nós 0, 0.5 e 1,
  incrementos não negativos e soma 1, escalas fixas e fontes explícitas.
- Preservar SciPy/HiGHS, tolerância explícita de 1e-7, viabilidade, identificação
  de conflitos e função representativa por máxima folga mínima. Distinguir falha
  numérica, inviabilidade e empate necessário de reversibilidade estrita.
- Comparar ROR dentro dos grupos; entre grupos, registrar precedência rígida com
  extremos de utilidade nulos. Reavaliar todos os vizinhos da ordem final.
- Versionar o modelo e o contrato de preferências; rejeitar configurações antigas
  com `espera` com orientação clara. Não converter nem reaproveitar silenciosamente
  uma fila ou proposta calculada com o modelo anterior.
- Reimportação da fila revisada exige versão esperada e autoria. Propostas antigas
  devem ser encerradas ou reavaliadas explicitamente; resultados em processamento
  não podem aplicar posições de uma versão anterior. Preservar auditoria e expiração.

Saída: CLI, relatórios e API coerentes com a versão da política aplicada.

## Etapa 5 — entregas vinculadas: BRAN e termo

Estas entregas não impedem a retirada da espera nem a análise descritiva. Cada
feature recebe plano e tarefas próprios após revisão da respectiva spec.

| Entrega | Spec / responsável | Condição de conclusão |
|---|---|---|
| Contestação com BRAN | Tribunal / Backend | Quatro dimensões distinguem evidência, ausência e conflito; dúvida de indicação gera revisão médica, sem cancelamento automático. Testes de contrato podem usar provedor de teste; não comprovam qualidade clínica de LLM real. |
| Parecer especializado | Tribunal e pontuação / Backend + clínica | Origem, protocolo, data e aprovação profissional rastreáveis; sem bônus fixo por parecer. Exige revisão do contrato antes de aceitar esse tipo de evidência. |
| Termo de upload | Extração / produto + Backend + Web/app | Texto e canal alternativo definidos, aceite explícito antes do recebimento, registro de versão/identidade/data e proibição de processamento sem aceite. |

O termo depende do fluxo real de upload, ainda ausente; registro de metadados não
comprova recebimento de bytes nem aceite anterior. Esta etapa não autoriza implementar
OCR, escolher provedor ou realizar chamadas a Gemini.

## Etapa 6 — aceitação e entrega

1. Testar invariância temporal em pontuação, relações ROR, empates, ordem de entrada
   embaralhada e guardas de reavaliação, mantendo evidências e validade constantes.
   Alterar data de entrada num pipeline bruto pode mudar classificação temporal dos
   eventos: esse efeito deve ser testado separadamente, não confundido com peso.
2. Testar rejeição da configuração antiga e invalidade de propostas da fila anterior.
   Preservar regressões de hierarquia, oncologia, limites, autorização e retenção.
3. Executar a base sintética completa com configuração nova, cobertura explícita,
   fonte original intacta e verificador oficial inalterado. Os resultados anteriores
   de 925 posições e 16 exclusões são referência histórica, não resultado garantido.
4. Repetir a execução: CSV, relações e função devem ser reproduzíveis. Manifestos
   registram modelo, preferências, fontes, geração, validade e hashes dos artefatos.
5. Atualizar `docs/backend-validation.md`, exemplos e resumo do PR com resultados
   realmente observados e pendências humanas. Commits atômicos, PR para `dev`, sem
   coautoria e sem merge automático ou realizado pelo agente.

## Riscos e mitigação

| Risco | Mitigação |
|---|---|
| Espera continuar em pares, desempates ou travas | Inventário de usos e regressões por mutação isolada da espera. |
| Remover datas e perder validade/histórico | Separar metadados temporais de preferências de prioridade. |
| ASA/porte virar regra clínica sem aprovação | Análise descritiva e revisão explícita antes de alterar escala/peso. |
| Dupla contagem de risco | Inventário de fatos e justificativa de cada critério. |
| Reutilizar parecer ou CSV antigo | Versão de política e de fila, reimportação e reavaliação explícitas. |
| Confundir testes sintéticos com validação clínica | Relatórios e aceites técnicos e clínicos separados. |

## Primeiro incremento recomendado

Executar a etapa 1 com regressões e a etapa 2 descritiva. Em seguida, usar os casos
para fechar a etapa 3 antes de declarar uma nova parametrização clínica concluída.
