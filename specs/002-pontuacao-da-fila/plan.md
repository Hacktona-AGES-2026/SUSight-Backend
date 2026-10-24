# Plano: Pontuação da fila

Spec: ./spec.md
Status: aprovado para implementação pelo usuário em 2026-10-24

## Abordagem

Usar funções marginais aditivas lineares por partes, com nós de utilidade normalizados
em 0, 0.5 e 1 para cada critério. Incrementos não negativos somam 1; a soma dos dois
incrementos de cada critério é seu peso de swing. Faixas de peso, ordens entre pesos
e 10–20 comparações holísticas com fonte são restrições lineares. Os limites das
escalas são explícitos na configuração e não mudam ao inserir pacientes.

SciPy/HiGHS verifica viabilidade. Em inconsistência, reduzir o conjunto conflitante
por eliminação de restrições, reportando seus IDs. Erros numéricos não são tratados
como inviabilidade. A função representativa maximiza a distância mínima aos limites
não estruturais; desempates seguem dias de espera e ID. Cada par da janela
configurável (padrão 1, incluindo todos os vizinhos) recebe mínimos e máximos da
diferença de valor. Necessidade fraca, empate necessário e reversibilidade estrita
são distintos: empate não é marcado como incerteza só por permitir ambas as ordens.

Travas da regra de ouro e dominância por prioridade/espera geram precedências para
ordenação topológica estável. Precedência que contraria uma preferência necessária
é conflito explícito: não publicar fila contraditória. Registrar relações calculadas;
pares fora da janela não são apresentados como certificados. Ao aplicar travas,
recalcular vizinhos finais. A função representativa pertence ao conjunto compatível.

SWALIS: classificação determinística versionada baseada nas descrições do arquivo
adaptado fornecido no desafio; conflitos/dados ausentes geram revisão. Valores de
comorbidade e deterioração são aproximações técnicas documentadas, não escalas
clinicamente validadas. As sete escalas e as fontes das restrições são obrigatórias.
Nenhum peso de literatura ou decisão clínica é fabricado pelo sistema. A configuração
exemplo é identificada como demonstrativa e não como elicitação validada.

## Dados e interfaces

CLI recebe dados tratados e JSON de preferências; publica CSV, relações de pares,
função representativa e DECISOES.md em diretório novo, apenas após validação.
Dados pendentes não são omitidos silenciosamente. IDs e cobertura são preservados.

## Decisões

- Solver: SciPy/HiGHS, funções aditivas lineares por partes.
- Tolerância numérica explícita: 1e-7; margem de preferência configurada positiva.
- Limite de elevação: floor(10% da fila ativa); prevalência da regra de ouro.
- Nenhuma chamada de IA para fila inicial; pares incertos são candidatos ao tribunal.

## Verificação

Viabilidade, conflito mínimo, representatividade, reversibilidade versus empate,
monotonicidade, travas, exportação reproduzível e verificador oficial no dataset.

Referência técnica: https://docs.scipy.org/doc/scipy/reference/optimize.linprog-highs.html

## Complemento autorizado em 2026-10-24

Aplicar ordenação lexicográfica por grupo protegido/sem urgência antes da utilidade. A ROR compartilha as faixas e escalas, mas só recebe comparações holísticas dentro de grupo; comparações entre grupos são verificadas como precedência. O código e as travas usam a mesma função de grupo. Relações entre grupos têm origem hierárquica, sem extremos de utilidade. Preferências de exemplo incluem escores de swing demonstrativos e faixas reproduzíveis, sem atribuir números à literatura. Executar a base inteira e o verificador oficial. Validação clínica continua externa ao teste técnico.
