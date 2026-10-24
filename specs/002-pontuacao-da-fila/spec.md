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
2. Um valor ausente num critério não é tratado como zero. Ele recebe a mediana desse critério entre as solicitações da mesma especialidade, e a solicitação fica marcada como "dado incompleto". Quando um par incerto envolve um valor imputado, isso é informado ao tribunal.
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
10. Quando a ordem entre A e B é possível nos dois sentidos, o par é marcado como **incerto**. Pares incertos são os candidatos a irem ao tribunal de IAs.
11. O sistema escolhe uma **função de valor representativa** entre as compatíveis para produzir uma ordem completa (necessária para o CSV), respeitando todas as ordens necessárias. O critério de escolha é definido no plano.

### Travas de equidade (aplicadas por cima da ordem)

12. **Regra de ouro:** nenhum paciente com CID iniciado por `C` (normalizado, sem depender da flag) fica abaixo de um paciente sem urgência clínica. A definição de "sem urgência clínica" é no mínimo tão rigorosa quanto a do `verificar_fila_priorizada.py`.
13. **Limite de elevação por reavaliação:** depois da fila inicial, uma reavaliação não sobe o paciente mais do que 10% do tamanho da fila ativa de uma vez (arredondado para baixo). Subidas maiores exigem nova reavaliação ou passam pelo tribunal. A regra de ouro prevalece sobre este limite: se ela exigir uma subida maior, por exemplo depois de uma biópsia positiva, a subida acontece.
14. **Não ultrapassar quem tem prioridade maior e mais espera:** um paciente não passa à frente de outro que tenha, ao mesmo tempo, pontuação de prioridade maior e mais dias de espera.
15. Nenhum peso consegue compensar uma violação das travas: elas valem sempre, por cima da pontuação.

### Saída

16. A fila ordenada sai no formato do entregável (`solicitacao_id`, `posicao`, `justificativa`).
17. A justificativa de cada solicitação, em português simples e sem alarme, cita os critérios que mais pesaram, se a posição em relação aos vizinhos é necessária ou incerta, e qual trava foi aplicada, se houver.

## Critérios de aceite

- [ ] Todos os sete critérios são calculados para cada solicitação ativa, com escala em que "mais" significa "mais prejudicado".
- [ ] Valores ausentes recebem a mediana da especialidade e a solicitação fica marcada como "dado incompleto".
- [ ] A prioridade manual da regulação não altera a ordem: trocar seu valor mantém a mesma fila.
- [ ] O tempo de espera é calculado como fração do prazo SWALIS da classe estimada, e a regra de estimativa da classe está registrada.
- [ ] Uma reavaliação nunca sobe um paciente mais de 10% da fila ativa, exceto quando a regra de ouro exige.
- [ ] As restrições do swing weighting e as comparações de referência estão registradas com a fonte de cada uma.
- [ ] As comparações de referência são respeitadas pela ordem final.
- [ ] Restrições contraditórias geram uma mensagem que aponta o conflito, e nenhuma fila é gerada.
- [ ] Cada par de vizinhos é classificado como ordem necessária ou incerto.
- [ ] A ordem final respeita todas as ordens necessárias.
- [ ] O arquivo gerado passa no `verificar_fila_priorizada.py` sem erros (formato e regra de ouro).
- [ ] Nenhum paciente ultrapassa outro com pontuação de prioridade maior e mais dias de espera.
- [ ] Toda linha tem justificativa legível em português do Brasil, sem diagnóstico.
- [ ] Rodar duas vezes com os mesmos dados e as mesmas restrições produz a mesma fila.

## Fora do escopo

- Tratamento do dataset: limpeza, deduplicação e extração de sinais do texto livre (issue #5). Esta spec recebe os dados já tratados.
- O debate dos pares incertos (tribunal, spec 001). Esta spec só marca quais pares são incertos.
- Elicitação de pesos com médicos ou com a regulação: as preferências vêm da literatura.
- Interface para editar pesos e comparações.
- Preparo pré-operatório (HbA1c, avaliação pré-anestésica, exames pré-op), que o desafio declara não avaliado.

## Questões em aberto

Nenhuma. A janela de proximidade dos pares e o critério de escolha da função de valor representativa são decisões do plano.
