# Spec: Pontuação da fila

Issue: Hacktona-AGES-2026/SUSight#6
Status: em revisão

Revisão de requisitos em 2026-10-24: espera removida por orientação explícita do usuário. Retirada da espera implementada e aceita tecnicamente no dataset sintético; demais decisões clínicas continuam pendentes; ver [revisão clínica](../../docs/clinical-review-2026-10-24.md).

## Contexto

A fila precisa ser ordenada pelo quanto cada paciente é prejudicado por esperar, de forma justa e explicável. Hoje a prioridade manual da regulação é ruidosa e raramente revisada.

Em vez de fixar um único conjunto de pesos (que seria uma escolha arbitrária difícil de defender), a pontuação usa:

- **Swing weighting** para transformar o que a literatura diz sobre a importância de cada critério em faixas e relações de peso.
- **Robust Ordinal Regression (ROR)** para considerar todas as ponderações compatíveis com essas faixas e com comparações de referência entre pacientes, e separar o que é ordem robusta do que é ordem incerta.

O tribunal de IAs (spec 001) passa a ser usado nos casos incertos, onde a ordem entre dois pacientes depende dos pesos escolhidos.

## Comportamento esperado

### Critérios

1. Cada solicitação ativa é avaliada nos critérios abaixo, todos com escala em que "mais" significa "mais prejudicado por esperar":
   - **Limitação funcional:** nenhuma < leve < moderada < grave.
   - **ASA:** a escala demonstrativa atual usa 1 < 2 < 3 < 4. Essa direção não comprova maior urgência cirúrgica; a relação entre ASA, porte e prioridade está em revisão clínica e deve ser decidida antes de uso real.
   - **Dor:** EVA de 0 a 10.
   - **Comorbidades:** quantidade e gravidade das comorbidades registradas (colunas e texto livre tratados pela issue #5).
   - **Tempo de espera não é critério:** dias em fila, data de entrada e fração do prazo SWALIS não alteram peso, ordenação, desempate ou travas. Permanecem disponíveis para acompanhamento administrativo. Deterioração clínica documentada é distinta do simples decurso do tempo.
   - **Deterioração durante a espera:** sinais de piora nos eventos clínicos (PS, internação, progressão em imagem, reavaliação com piora, relato de piora).
   - **Questão socioeconômica:** distância até o hospital (maior distância, maior prejuízo).
2. No tratamento do dataset de referência, um valor ausente num critério não é tratado como zero. Ele recebe a mediana desse critério entre as solicitações da mesma especialidade, e a solicitação fica marcada como "dado incompleto". Quando um par incerto envolve um valor imputado, isso é informado ao tribunal. Essa convenção não preenche campos ausentes da extração documental: eles permanecem `null`, como definido em `specs/001-extracao-de-exames/spec.md` (PR #7), até revisão ou tratamento específico aprovado.
3. A prioridade manual da regulação (`alta`, `media`, `baixa`) não entra na pontuação, porque o desafio a declara ruidosa e frequentemente errada. Ela aparece na justificativa e como contexto para o tribunal.

### Informação de preferência

4. A importância de cada critério é definida por **swing weighting baseado em literatura**: SWALIS (o modelo de referência do desafio), as ferramentas de prioridade do Western Canada Waiting List Project e os Clinical Priority Assessment Criteria (CPAC) da Nova Zelândia. As fontes usadas para cada restrição ficam registradas no `DECISOES.md`. O resultado não é um número exato por critério, e sim restrições: faixas de peso (por exemplo, "dor entre 15% e 30%") e relações de ordem entre pesos (por exemplo, "deterioração pesa mais que distância").
5. Além do swing, o sistema recebe de **10 a 20 comparações de referência** entre pacientes do dataset ("o paciente A deve vir antes do B"), também justificadas pela literatura, como um caso compatível com a classe SWALIS A1 contra um caso compatível com a classe D.
6. Cada restrição e cada comparação de referência fica registrada com a fonte que a sustenta.
7. Se as restrições forem contraditórias entre si (nenhuma ponderação satisfaz todas), o sistema informa quais restrições estão em conflito e não gera a fila até que elas sejam corrigidas.

### Ordenação robusta

8. A ordenação é hierárquica em dois níveis. Primeiro, o grupo protegido (CID C* ou não classificado como sem urgência) antecede o grupo sem urgência clínica ou assim identificado pelo verificador. Segundo, dentro do grupo protegido, a **classe SWALIS** (A1, A2, B, C, D, nessa ordem) é uma camada de precedência: toda solicitação de uma classe antecede as das classes seguintes. A classe é derivada só de dados clínicos (CID, biópsia positiva, dor, limitação e piora durante a espera); dias em fila, data de entrada e razão de prazo não participam. Essas precedências são rígidas e não dependem dos pesos. Dentro de cada classe, o sistema considera todas as funções de valor aditivas compatíveis com as restrições. Comparações entre grupos são verificadas contra a hierarquia; não são usadas para ajustar os pesos. Uma comparação que contrarie a hierarquia é rejeitada explicitamente.
9. Para cada par de solicitações próximas na fila (a janela de proximidade é definida no plano), o sistema determina:
   - **ordem necessária:** A fica à frente de B em todas as ponderações compatíveis;
   - **ordem possível:** A fica à frente de B em pelo menos uma ponderação compatível.
10. Quando há modelos compatíveis em que A supera estritamente B e outros em que B supera estritamente A, o par é marcado como **incerto**. Um empate em todos os modelos é identificado separadamente como empate necessário. Pares incertos são os candidatos a irem ao tribunal de IAs; incerteza não é um percentual de probabilidade clínica.
11. O sistema escolhe uma **função de valor representativa** entre as compatíveis para produzir uma ordem completa (necessária para o CSV), respeitando as ordens necessárias dentro de cada grupo e a precedência rígida entre grupos. O critério de escolha é definido no plano.

### Travas de equidade (aplicadas por cima da ordem)

12. **Regra de ouro:** nenhum paciente com CID iniciado por `C` (normalizado, sem depender da flag) fica abaixo de um paciente sem urgência clínica. A definição de "sem urgência clínica" é no mínimo tão rigorosa quanto a do `verificar_fila_priorizada.py`.
13. **Limite de elevação por reavaliação:** depois da fila inicial, uma reavaliação não sobe o paciente mais do que 10% do tamanho da fila ativa de uma vez (arredondado para baixo). A passagem pelo tribunal não dispensa esse limite. A regra de ouro prevalece sobre ele quando um CID `C*` validado exigir subida maior; uma biópsia positiva com CID ainda não `C*` gera revisão clínica e não reescreve o diagnóstico nem aciona silenciosamente essa exceção.
14. **Retirada da trava dependente de espera:** a regra anterior de prioridade maior combinada com mais dias de espera foi retirada. A ordenação respeita a hierarquia, as relações necessárias da ROR e o limite de elevação, sem utilizar antiguidade para dar preferência.
15. Nenhum peso compensa a precedência rígida. Entre grupos e entre classes SWALIS do grupo protegido prevalece a hierarquia. Como a regra de ouro leva todo CID `C*` a A1 ou A2, a camada SWALIS nunca coloca um oncológico depois de um paciente sem urgência. Empates remanescentes usam identificação estável da solicitação, sem data de entrada ou dias de espera. A justificativa distingue precedência rígida de comparação ROR.

### Saída

16. A fila ordenada sai no formato do entregável (`solicitacao_id`, `posicao`, `justificativa`).
17. A justificativa de cada solicitação, em português simples e sem alarme, cita os critérios que mais pesaram, se a posição em relação aos vizinhos é necessária ou incerta, e qual trava foi aplicada, se houver.

### Recomendações adotadas para o MVP

- **Escopo:** executar demonstração e avaliação apenas no dataset sintético. Separar parametrização demonstrativa de preferências validadas, com indicação legível no CSV e nos relatórios. Não apresentar a fila como recomendação clínica pronta para uso real.
- **Pesos e fontes:** receber faixas e comparações explicitamente documentadas, com escala mínima/máxima de cada critério, data, versão, fonte e responsável pela interpretação. Pesos de swing dependem da amplitude dos critérios. Não atribuir percentuais a SWALIS, WCWL ou CPAC sem apoio identificado; SWALIS não é, por si só, uma tabela de pesos para os critérios ativos. Quando a fonte não sustentar um número, manter a premissa rotulada como demonstrativa para revisão, sem inventar validação bibliográfica.
- **Comportamento padrão:** calcular todas as relações entre vizinhos da fila final. Pares mais distantes só recebem classificação quando efetivamente avaliados. Usar nomes de relações e motivos de revisão; não adotar o exemplo "0,2" como limiar de incerteza sem definição e validação de uma medida correspondente.
- **Critérios clínicos:** ASA 1–4 é o domínio do dataset, não uma autorização para reduzir classes incompatíveis extraídas de documentos. Dor sem escala explícita, comorbidade não confirmada, dado ilegível e categorização funcional inferida ficam para revisão. As adaptações de SWALIS, gravidade de comorbidades e deterioração são registradas como premissas técnicas e precisam de validação antes de uso real.
- **Imputação:** no dataset, usar mediana da especialidade sobre observações válidas de canônicas ativas, sem cascata; em categorias ordinais e EVA inteira, usar o elemento central superior. Sem população válida, manter pendência. Nunca usar mediana para alterar CID, comprovar ausência de urgência ou converter um campo documental `null` em evidência observada.
- **Conflitos de modelo:** a regra de ouro é representada na hierarquia antes da ROR, não como competição entre pesos. Entre grupos, a relação é uma precedência rígida, com extremos de utilidade não aplicáveis; não é apresentada como conclusão aditiva. Restrições incompatíveis dentro dos grupos ou comparações contrárias à hierarquia continuam bloqueando publicação. Esta é uma convenção técnica da demonstração sintética, não validação clínica das escalas.
- **Publicação e auditoria:** nenhuma fila parcial com pendências impeditivas é apresentada como completa. Guardar cobertura, versão da entrada, preferências, fontes, função representativa, relações avaliadas, travas e justificativas. A origem da incerteza deve distinguir sensibilidade aos pesos de incompletude da evidência.
- **Acesso e guarda:** limitar o relatório ao que cada envolvido está autorizado a consultar. Cópias de trabalho e saídas sintéticas geradas para a demonstração expiram em até sete dias da geração, ou antes por solicitação do responsável; a fonte original imutável do desafio e fixtures inteiramente sintéticas versionadas não são apagadas por essa regra. Não enviar nome, CNS ou texto identificável a serviço externo para pontuar a fila.

A hierarquia resolve a contradição técnica identificada entre precedência e utilidade aditiva. A aceitação requer regressão no dataset completo e verificador oficial; as escalas e preferências demonstrativas continuam explicitamente sem validação clínica.

## Critérios de aceite

- [ ] Os seis critérios restantes são representados para cada solicitação ativa, com premissas de escala identificadas e pendências clínicas explícitas.
- [ ] Valores ausentes recebem a mediana da especialidade e a solicitação fica marcada como "dado incompleto".
- [ ] A prioridade manual da regulação não altera a ordem: trocar seu valor mantém a mesma fila.
- [ ] Alterar somente dias de espera, data de entrada ou razão de prazo SWALIS, preservando os eventos clínicos e sua validade, mantém pontuação, relações ROR, posições e decisões das travas, inclusive em empates.
- [ ] Uma reavaliação nunca sobe um paciente mais de 10% da fila ativa, exceto quando a regra de ouro exige.
- [ ] As restrições do swing weighting e as comparações de referência estão registradas com a fonte de cada uma.
- [ ] As comparações de referência são respeitadas pela ordem final.
- [ ] Restrições contraditórias geram uma mensagem que aponta o conflito, e nenhuma fila é gerada.
- [ ] Cada par de vizinhos é classificado como ordem necessária, empate necessário ou incerto por reversibilidade estrita, sem percentual de probabilidade clínica presumido.
- [ ] A ordem final respeita a hierarquia e as ordens necessárias dentro dos grupos; diferenças numéricas de ROR entre grupos não são apresentadas como prioridade superior.
- [ ] O arquivo gerado passa no `verificar_fila_priorizada.py` sem erros (formato e regra de ouro).
- [ ] Nenhuma trava de prioridade utiliza espera; entre grupos prevalece a precedência rígida e dentro deles são respeitadas as relações necessárias da ROR.
- [ ] No grupo protegido, nenhuma solicitação de classe SWALIS posterior (por exemplo B) fica à frente de uma de classe anterior (por exemplo A2), qualquer que seja a utilidade aditiva.
- [ ] Alterar a classe SWALIS por dados clínicos muda a posição; alterar só dias de espera, data de entrada ou razão de prazo não muda a classe nem a fila.
- [ ] Uma comparação de referência que contrarie a precedência entre classes SWALIS é rejeitada, como as que contrariam a hierarquia entre grupos.
- [ ] O relatório de aceitação informa a distribuição dos oncológicos por faixa de posição e por classe SWALIS.
- [ ] Toda linha tem justificativa legível em português do Brasil, sem diagnóstico.
- [ ] Rodar duas vezes com os mesmos dados e as mesmas restrições produz a mesma fila.
- [ ] A ausência na extração documental continua `null` e rastreável; a imputação do dataset não é apresentada como valor documentado.
- [ ] O par de regressão oncológico/sem urgência respeita a hierarquia mesmo quando a utilidade aditiva isolada favorece o segundo; uma comparação de referência contrária à hierarquia é rejeitada.
- [ ] Toda premissa demonstrativa está identificada como tal; nenhuma faixa numérica aparece atribuída a uma referência sem sustentação registrada.
- [ ] O cenário de aceitação verifica autorização dos relatórios e expiração das saídas temporárias de demonstração, preservando a fonte original imutável.

## Fora do escopo

- Tratamento do dataset: limpeza, deduplicação e extração de sinais do texto livre (issue #5). Esta spec recebe os dados já tratados.
- O debate dos pares incertos (tribunal, spec 001). Esta spec só marca quais pares são incertos.
- Validação clínica automática: o sistema não substitui os responsáveis por validar escalas e preferências. A elicitação profissional foi incluída no planejamento autorizado; resultados e aprovação permanecem pendentes.
- Interface para editar pesos e comparações.
- Preparo pré-operatório (HbA1c, avaliação pré-anestésica, exames pré-op), que o desafio declara não avaliado.

## Questões em aberto

Decisão de 2026-10-24: a classe SWALIS passa a ordenar o grupo protegido como camada de precedência. Motivo: o CID `C*` não é critério aditivo, e oncológicos com dor e limitação baixas (101 de 177 no dataset) ficavam na metade inferior apesar de classe A1 ou A2. A adaptação das classes continua sendo premissa técnica, sem validação clínica; os limiares de dor (7 e 4) e a regra de A1 e A2 precisam de revisão por quem conhece a regulação.

A exclusão da espera está decidida: sem peso e sem desempate. Permanecem abertas a representação explícita de CID/fatores de risco, a relação ASA × porte e a elicitação das novas faixas de swing. A ordem relatada câncer → cardiovascular → trauma e a menor prioridade atribuída a condições M não são uma regra universal validada. Ver a revisão clínica vinculada acima. Não renormalizar automaticamente os pesos demonstrativos antigos e apresentá-los como preferências médicas.

## Estado da implementação

A política `priorizacao-sem-espera-v1` remove espera de critérios, desempates, pares, travas e contexto externo. A aceitação completa e a repetição do CSV foram executadas; 70 testes passaram. ASA × porte e inventário agregado estão implementados. Novos critérios/pesos clínicos permanecem pendentes; BRAN e termo de upload têm planos vinculados, sem implementação funcional nesta etapa. Ver `../../docs/backend-validation.md`.
