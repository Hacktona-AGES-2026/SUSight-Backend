# Pontuação robusta da fila

`python -m susight.scoring --input-dir TRATADO --preferences CONFIG.json --output-dir NOVO`.

A configuração exige seis escalas fixas (`minimo`, `maximo`, `fonte`), seis faixas de
peso (`minimo`, `maximo`, `fonte`) e 10–20 comparações únicas (`antes`, `depois`,
`fonte`). `ordem_pesos` permite relações estritas (`maior`, `menor`, `fonte`).
`margem` define a diferença mínima de uma preferência estrita; `janela` define os
pares finais avaliados (1 = todos os vizinhos). `versao` identifica a parametrização;
`demonstrativa` deve identificar testes sem validação clínica.

Critérios: limitação, ASA, dor, comorbidades, deterioração e
distância. As aproximações atuais de SWALIS, comorbidades e deterioração constam
no `DECISOES.md` gerado e exigem revisão. Literatura não é convertida automaticamente
em percentuais. A configuração não comprova que uma fonte realmente sustenta o peso;
a equipe precisa revisar as fontes informadas.

## Solver

Cada critério tem função marginal linear por partes, com nós em 0, 0.5 e 1. Os 12
incrementos não negativos somam 1; a soma dos incrementos de cada critério é seu
peso de swing. Faixas e comparações definem um conjunto de funções compatíveis.
HiGHS resolve a viabilidade e os extremos da diferença de valor entre pacientes.
A função representativa maximiza a menor folga normalizada às restrições.

Necessidade e possibilidade são relações fracas (>=). Só há incerteza reversível
quando existem diferenças estritamente positivas e negativas. Um empate necessário
não é chamado de incerteza. Valores além dos limites são saturados e a configuração
precisa escolher limites coerentes com o swing comparado.

A ordem é lexicográfica: o grupo protegido (CID C* e os casos que não estão no
grupo sem urgência) antecede o grupo sem urgência. As comparações de utilidade,
necessidade e possibilidade são feitas dentro do grupo. Espera não entra no peso,
desempate, trava ou escolha dos pares de referência; empate final usa ID estável. Entre grupos, a
relação tem origem `hierarquia_regra_de_ouro` e extremos aditivos null. Não se
interpreta a pontuação bruta de um grupo como prioridade superior à do outro.
Comparação de referência contrária à hierarquia é rejeitada; restrições incompatíveis
dentro dos grupos continuam bloqueando publicação. Essa convenção resolve a
contradição de modelagem da configuração anterior sem forjar pesos.
A janela final certifica apenas os pares efetivamente calculados.

`sem_urgencia` é a avaliação conservadora dos dados observados.
`sem_urgencia_verificador` é exclusivamente a condição técnica do verificador do
desafio, incluindo seus defaults para ausentes; não comprova condição clínica.
A regra de ouro protege ambos os conjuntos para conservar compatibilidade com a
avaliação oficial sem tratar imputação como evidência de ausência de urgência.

## Saída

`fila_priorizada.csv`, `fila.json`, `relacoes.json`, `funcao_representativa.json` e
`DECISOES.md`. A função e todas as preferências/fontes ficam publicadas para auditoria.
Casos incertos não convocam LLM automaticamente na geração inicial.

Referência do solver: https://docs.scipy.org/doc/scipy/reference/optimize.linprog-highs.html

## Swing demonstrativo e aceitação

`tools/acceptance.py` registra swings ilustrativos: deterioração 100,
limitação 80, dor 70, comorbidades 60, ASA 40 e distância 20. Normaliza a soma e usa
faixas de 75% a 125% de cada peso normalizado; dez pares monotonicamente dominantes
dentro do grupo verificam a integração. Essa escolha é uma hipótese de protótipo,
não uma elicitação médica nem dado atribuído a SWALIS/WCWL/CPAC. Fontes, faixas,
escalas e os pares aparecem no relatório e precisam de revisão antes de uso real.

O manifesto das saídas tem prazo máximo de sete dias e herda a validade dos dados
tratados. CSVs e relatórios são privados ao usuário local. Limpeza é feita apenas
por manifesto e não remove o dataset fonte. Registros originais ausentes continuam
identificáveis; nunca se transforma imputação em evidência documental observada.

## Política sem espera e migração

A configuração exige `politica: "priorizacao-sem-espera-v1"`. Configurações legadas
com espera são rejeitadas, inclusive quando ela aparece apenas nos swings.
As contribuições e o número de variáveis são derivados dos critérios ativos.
Dias de fila e SWALIS podem permanecer como metadados administrativos; não são
enviados ao tribunal nem usados para ordenar. Deterioração documentada é separada.

O manifesto registra política, hash das preferências, da entrada e das saídas.
Filas calculadas com política anterior precisam ser regeneradas e reimportadas;
propostas antigas não recebem aplicação automática sob a política nova.

## Análise ASA × porte

```sh
uv run --no-sync python -m susight.scoring.analysis \
  --dataset /caminho/dataset --treated /caminho/tratado \
  --output outputs/analise-nova
```

Gera `analise.json`, `RELATORIO.md` e manifesto com retenção. Tabelas usam ASA
observado, incluindo ausência e denominadores por porte/especialidade. Imputados
são contados separadamente; uma amostra de sensibilidade retira grupos suspeitos
apenas da análise. Não altera a fila nem confirma duplicidade ou relação causal.
Porte `especial` é preservado como categoria do catálogo, sem ordem numérica imposta.
O inventário abrange os conceitos das regras existentes e explicita essa limitação.

O roteiro de validação das escalas e swing está em [elicitação](clinical-elicitation.md).
A monotonicidade de ASA e sua relação com porte continuam pendências clínicas.
