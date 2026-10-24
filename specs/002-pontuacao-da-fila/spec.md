# Spec: Pontuação da fila

Issue: Hacktona-AGES-2026/SUSight#6
Status: em revisão

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
   - **ASA:** 1 < 2 < 3 < 4. ASA alto indica paciente mais frágil e sobe a prioridade.
   - **Dor:** EVA de 0 a 10.
   - **Comorbidades:** quantidade e gravidade das comorbidades registradas (colunas e texto livre tratados pela issue #5).
   - **Tempo de espera:** dias em fila divididos pelo prazo máximo da classe SWALIS estimada do paciente (A1 = 15, A2 = 21, B = 60, C = 180, D = 360 dias). Valor acima de 1 significa prazo estourado. A classe é estimada a partir do CID, da dor, da limitação e dos eventos clínicos, com a regra registrada no `DECISOES.md`.
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

8. O sistema considera todas as funções de valor aditivas compatíveis com as restrições e as comparações de referência.
9. Para cada par de solicitações próximas na fila (a janela de proximidade é definida no plano), o sistema determina:
   - **ordem necessária:** A fica à frente de B em todas as ponderações compatíveis;
   - **ordem possível:** A fica à frente de B em pelo menos uma ponderação compatível.
10. Quando há modelos compatíveis em que A supera estritamente B e outros em que B supera estritamente A, o par é marcado como **incerto**. Um empate em todos os modelos é identificado separadamente como empate necessário. Pares incertos são os candidatos a irem ao tribunal de IAs; incerteza não é um percentual de probabilidade clínica.
11. O sistema escolhe uma **função de valor representativa** entre as compatíveis para produzir uma ordem completa (necessária para o CSV), respeitando todas as ordens necessárias. O critério de escolha é definido no plano.

### Travas de equidade (aplicadas por cima da ordem)

12. **Regra de ouro:** nenhum paciente com CID iniciado por `C` (normalizado, sem depender da flag) fica abaixo de um paciente sem urgência clínica. A definição de "sem urgência clínica" é no mínimo tão rigorosa quanto a do `verificar_fila_priorizada.py`.
13. **Limite de elevação por reavaliação:** depois da fila inicial, uma reavaliação não sobe o paciente mais do que 10% do tamanho da fila ativa de uma vez (arredondado para baixo). A passagem pelo tribunal não dispensa esse limite. A regra de ouro prevalece sobre ele quando um CID `C*` validado exigir subida maior; uma biópsia positiva com CID ainda não `C*` gera revisão clínica e não reescreve o diagnóstico nem aciona silenciosamente essa exceção.
14. **Não ultrapassar quem tem prioridade maior e mais espera:** um paciente não passa à frente de outro que tenha, ao mesmo tempo, pontuação de prioridade maior e mais dias de espera.
15. Nenhum peso consegue compensar uma violação das travas: elas valem sempre, por cima da pontuação.

### Saída

16. A fila ordenada sai no formato do entregável (`solicitacao_id`, `posicao`, `justificativa`).
17. A justificativa de cada solicitação, em português simples e sem alarme, cita os critérios que mais pesaram, se a posição em relação aos vizinhos é necessária ou incerta, e qual trava foi aplicada, se houver.

### Recomendações adotadas para o MVP

- **Escopo:** executar demonstração e avaliação apenas no dataset sintético. Separar parametrização demonstrativa de preferências validadas, com indicação legível no CSV e nos relatórios. Não apresentar a fila como recomendação clínica pronta para uso real.
- **Pesos e fontes:** receber faixas e comparações explicitamente documentadas, com escala mínima/máxima de cada critério, data, versão, fonte e responsável pela interpretação. Pesos de swing dependem da amplitude dos critérios. Não atribuir percentuais a SWALIS, WCWL ou CPAC sem apoio identificado; SWALIS não é, por si só, uma tabela de pesos para estes sete critérios. Quando a fonte não sustentar um número, manter a premissa rotulada como demonstrativa para revisão, sem inventar validação bibliográfica.
- **Comportamento padrão:** calcular todas as relações entre vizinhos da fila final. Pares mais distantes só recebem classificação quando efetivamente avaliados. Usar nomes de relações e motivos de revisão; não adotar o exemplo "0,2" como limiar de incerteza sem definição e validação de uma medida correspondente.
- **Critérios clínicos:** ASA 1–4 é o domínio do dataset, não uma autorização para reduzir classes incompatíveis extraídas de documentos. Dor sem escala explícita, comorbidade não confirmada, dado ilegível e categorização funcional inferida ficam para revisão. As adaptações de SWALIS, gravidade de comorbidades e deterioração são registradas como premissas técnicas e precisam de validação antes de uso real.
- **Imputação:** no dataset, usar mediana da especialidade sobre observações válidas de canônicas ativas, sem cascata; em categorias ordinais e EVA inteira, usar o elemento central superior. Sem população válida, manter pendência. Nunca usar mediana para alterar CID, comprovar ausência de urgência ou converter um campo documental `null` em evidência observada.
- **Conflitos de modelo:** a recomendação para o MVP atual é bloquear publicação e explicar o conflito quando uma ordem necessária e uma trava rígida forem incompatíveis. Não escolher pesos oportunistas apenas para obter aprovação do verificador, omitir pacientes ou solicitar à IA que resolva a contradição. A precedência oncológica antes da comparação de utilidade é uma alternativa de evolução a ser especificada e validada; não se presume implementada nem aprovada como solução clínica.
- **Publicação e auditoria:** nenhuma fila parcial com pendências impeditivas é apresentada como completa. Guardar cobertura, versão da entrada, preferências, fontes, função representativa, relações avaliadas, travas e justificativas. A origem da incerteza deve distinguir sensibilidade aos pesos de incompletude da evidência.
- **Acesso e guarda:** limitar o relatório ao que cada envolvido está autorizado a consultar. Cópias de trabalho e saídas sintéticas geradas para a demonstração expiram em até sete dias da geração, ou antes por solicitação do responsável; a fonte original imutável do desafio e fixtures inteiramente sintéticas versionadas não são apagadas por essa regra. Não enviar nome, CNS ou texto identificável a serviço externo para pontuar a fila.

As recomendações não resolvem o conflito já observado no dataset completo nem atestam que as escalas ou preferências demonstrativas tenham validação clínica. Permanecem as pendências de aceitação registradas no PR consolidado.

## Critérios de aceite

- [ ] Todos os sete critérios são calculados para cada solicitação ativa, com escala em que "mais" significa "mais prejudicado".
- [ ] Valores ausentes recebem a mediana da especialidade e a solicitação fica marcada como "dado incompleto".
- [ ] A prioridade manual da regulação não altera a ordem: trocar seu valor mantém a mesma fila.
- [ ] O tempo de espera é calculado como fração do prazo SWALIS da classe estimada, e a regra de estimativa da classe está registrada.
- [ ] Uma reavaliação nunca sobe um paciente mais de 10% da fila ativa, exceto quando a regra de ouro exige.
- [ ] As restrições do swing weighting e as comparações de referência estão registradas com a fonte de cada uma.
- [ ] As comparações de referência são respeitadas pela ordem final.
- [ ] Restrições contraditórias geram uma mensagem que aponta o conflito, e nenhuma fila é gerada.
- [ ] Cada par de vizinhos é classificado como ordem necessária, empate necessário ou incerto por reversibilidade estrita, sem percentual de probabilidade clínica presumido.
- [ ] A ordem final respeita todas as ordens necessárias.
- [ ] O arquivo gerado passa no `verificar_fila_priorizada.py` sem erros (formato e regra de ouro).
- [ ] Nenhum paciente ultrapassa outro com pontuação de prioridade maior e mais dias de espera.
- [ ] Toda linha tem justificativa legível em português do Brasil, sem diagnóstico.
- [ ] Rodar duas vezes com os mesmos dados e as mesmas restrições produz a mesma fila.
- [ ] A ausência na extração documental continua `null` e rastreável; a imputação do dataset não é apresentada como valor documentado.
- [ ] Um conflito de ROR e regra de ouro impede a publicação e identifica os casos; votação do tribunal não libera a contradição.
- [ ] Toda premissa demonstrativa está identificada como tal; nenhuma faixa numérica aparece atribuída a uma referência sem sustentação registrada.
- [ ] O cenário de aceitação verifica autorização dos relatórios e expiração das saídas temporárias de demonstração, preservando a fonte original imutável.

## Fora do escopo

- Tratamento do dataset: limpeza, deduplicação e extração de sinais do texto livre (issue #5). Esta spec recebe os dados já tratados.
- O debate dos pares incertos (tribunal, spec 001). Esta spec só marca quais pares são incertos.
- Elicitação de pesos com médicos ou com a regulação: as preferências vêm da literatura.
- Interface para editar pesos e comparações.
- Preparo pré-operatório (HbA1c, avaliação pré-anestésica, exames pré-op), que o desafio declara não avaliado.

## Questões em aberto

Nenhuma decisão de escopo do MVP pendente. O padrão avalia todos os vizinhos; o plano detalha a escolha reprodutível da função representativa e eventual ampliação da janela. Revisão das fontes, validação das escalas e solução do conflito da base completa continuam pendências de aceitação. Recomendações de escopo não são validação dos pesos nem autorização para publicar uma fila incompatível.

## Estado da implementação

Implementação e testes incluídos no PR consolidado. Evidências e critérios de aceitação ainda pendentes estão em `../../docs/backend-validation.md`; não declarar validação clínica nem aceitação da base completa antes de resolver essas pendências.
