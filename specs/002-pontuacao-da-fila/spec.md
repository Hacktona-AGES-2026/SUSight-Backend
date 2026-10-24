# Spec: Pontuação da fila

Issue: Hacktona-AGES-2026/SUSight#6
Status: rascunho

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
   - **Tempo de espera:** dias em fila.
   - **Deterioração durante a espera:** sinais de piora nos eventos clínicos (PS, internação, progressão em imagem, reavaliação com piora, relato de piora).
   - **Questão socioeconômica:** distância até o hospital (maior distância, maior prejuízo).
2. Um valor ausente num critério não é tratado como zero. O sistema usa a regra definida para valores ausentes (questão em aberto) e marca a solicitação como tendo dado incompleto.

### Informação de preferência

3. A importância de cada critério é definida por **swing weighting baseado em literatura** (SWALIS e outras referências registradas no `DECISOES.md`). O resultado não é um número exato por critério, e sim restrições: faixas de peso (por exemplo, "dor entre 15% e 30%") e relações de ordem entre pesos (por exemplo, "deterioração pesa mais que distância").
4. Além do swing, o sistema recebe de **10 a 20 comparações de referência** entre pacientes do dataset ("o paciente A deve vir antes do B"), também justificadas pela literatura, como um caso compatível com a classe SWALIS A1 contra um caso compatível com a classe D.
5. Cada restrição e cada comparação de referência fica registrada com a fonte que a sustenta.
6. Se as restrições forem contraditórias entre si (nenhuma ponderação satisfaz todas), o sistema informa quais restrições estão em conflito e não gera a fila até que elas sejam corrigidas.

### Ordenação robusta

7. O sistema considera todas as funções de valor aditivas compatíveis com as restrições e as comparações de referência.
8. Para cada par de solicitações próximas na fila, o sistema determina:
   - **ordem necessária:** A fica à frente de B em todas as ponderações compatíveis;
   - **ordem possível:** A fica à frente de B em pelo menos uma ponderação compatível.
9. Quando a ordem entre A e B é possível nos dois sentidos, o par é marcado como **incerto**. Pares incertos são os candidatos a irem ao tribunal de IAs.
10. O sistema escolhe uma **função de valor representativa** entre as compatíveis para produzir uma ordem completa (necessária para o CSV), respeitando todas as ordens necessárias.

### Travas de equidade (aplicadas por cima da ordem)

11. **Regra de ouro:** nenhum paciente com CID iniciado por `C` (normalizado, sem depender da flag) fica abaixo de um paciente sem urgência clínica. A definição de "sem urgência clínica" é no mínimo tão rigorosa quanto a do `verificar_fila_priorizada.py`.
12. **Limite de elevação por reavaliação:** uma reavaliação não pode subir o paciente mais do que o limite definido de uma vez.
13. **Não ultrapassar quem tem prioridade maior e mais espera:** um paciente não passa à frente de outro que tenha, ao mesmo tempo, pontuação de prioridade maior e mais dias de espera.
14. Nenhum peso consegue compensar uma violação das travas: elas valem sempre, por cima da pontuação.

### Saída

15. A fila ordenada sai no formato do entregável (`solicitacao_id`, `posicao`, `justificativa`).
16. A justificativa de cada solicitação, em português simples e sem alarme, cita os critérios que mais pesaram, se a posição em relação aos vizinhos é necessária ou incerta, e qual trava foi aplicada, se houver.

## Critérios de aceite

- [ ] Todos os sete critérios são calculados para cada solicitação ativa, com escala em que "mais" significa "mais prejudicado".
- [ ] Valores ausentes seguem a regra definida e a solicitação fica marcada como tendo dado incompleto.
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

- A prioridade manual da regulação (`alta`, `media`, `baixa`) entra como critério, como desempate ou fica de fora por ser ruidosa?
- Regra para valores ausentes: pior caso, valor neutro ou mediana da especialidade?
- O tempo de espera entra em dias absolutos ou relativo ao prazo máximo da classe SWALIS estimada do paciente?
- Qual o valor do limite de elevação por reavaliação?
- Até que distância na fila os pares são comparados para a ordem necessária (por exemplo, 20 posições)?
- Qual critério escolhe a função de valor representativa (por exemplo, a que mais separa as comparações de referência)?
- Quais referências da literatura sustentam as faixas de peso, além do SWALIS?
