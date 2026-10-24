# Pontuação robusta da fila

`python -m susight.scoring --input-dir TRATADO --preferences CONFIG.json --output-dir NOVO`.

A configuração exige sete escalas fixas (`minimo`, `maximo`, `fonte`), sete faixas de
peso (`minimo`, `maximo`, `fonte`) e 10–20 comparações únicas (`antes`, `depois`,
`fonte`). `ordem_pesos` permite relações estritas (`maior`, `menor`, `fonte`).
`margem` define a diferença mínima de uma preferência estrita; `janela` define os
pares finais avaliados (1 = todos os vizinhos). `versao` identifica a parametrização;
`demonstrativa` deve identificar testes sem validação clínica.

Critérios: limitação, ASA, dor, comorbidades, espera/prazo SWALIS, deterioração e
distância. As aproximações atuais de SWALIS, comorbidades e deterioração constam
no `DECISOES.md` gerado e exigem revisão. Literatura não é convertida automaticamente
em percentuais. A configuração não comprova que uma fonte realmente sustenta o peso;
a equipe precisa revisar as fontes informadas.

## Solver

Cada critério tem função marginal linear por partes, com nós em 0, 0.5 e 1. Os 14
incrementos não negativos somam 1; a soma dos incrementos de cada critério é seu
peso de swing. Faixas e comparações definem um conjunto de funções compatíveis.
HiGHS resolve a viabilidade e os extremos da diferença de valor entre pacientes.
A função representativa maximiza a menor folga normalizada às restrições.

Necessidade e possibilidade são relações fracas (>=). Só há incerteza reversível
quando existem diferenças estritamente positivas e negativas. Um empate necessário
não é chamado de incerteza. Valores além dos limites são saturados e a configuração
precisa escolher limites coerentes com o swing comparado.

As travas geram precedências e uma ordenação topológica estável. Se contradizem
uma ordem necessária, uma comparação de referência ou outra trava, a publicação
falha explicitamente. Nenhum arquivo parcial é apresentado como fila válida.
Classificações da janela não certificam pares que não foram calculados.

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
