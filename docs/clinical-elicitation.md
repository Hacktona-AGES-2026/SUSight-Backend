# Roteiro de validação dos critérios e preferências

Status: preparado para revisão humana; respostas clínicas ainda não obtidas.
Modelo técnico: `priorizacao-sem-espera-v1`, exclusivamente sintético.

## Material disponível

- Relatório ASA × porte: gerado por `python -m susight.scoring.analysis`.
- `examples/preferences-demo.json`: seis escalas e dez comparações sintéticas,
  com origem explícita. Esses pares servem para discutir o comportamento do modelo;
  não são preferências assinadas por profissionais.
- `docs/clinical-review-2026-10-24.md`: origem e limites das anotações.

## Decisões a registrar antes de alterar os critérios clínicos

| Decisão | Pergunta para os responsáveis | Registro necessário |
|---|---|---|
| CID e gravidade | Qual protocolo por condição/especialidade define risco de adiar? Quais exceções impedem um ranking por capítulo? | Regra, versão, fonte, casos e contraexemplos. |
| Fatores de risco | Quais fatos documentados mudam a prioridade e quais apenas o planejamento perioperatório? | Lista e escala, evidência exigida, ausência/negação/suspeita e revisão. |
| ASA × porte | ASA participa da urgência, do risco perioperatório ou apenas da indicação de revisão? Como porte altera essa interpretação? | Decisão explícita; não presumir que ASA maior exige operar antes. |
| Sobreposição | O mesmo fato está sendo contado em ASA, comorbidades, CID e deterioração? | Mapeamento dos fatos e justificativa de eventual participação em vários critérios. |
| Parecer especializado | Qual conteúdo e protocolo sustentam a prioridade, além da existência do parecer? | Fonte, data, evidência e revisão; sem bônus fixo. |

## Sessão de swing e comparações

1. Conferir as escalas mínima/máxima propostas e se a amplitude representa o cenário
   que os responsáveis querem comparar. Não usar a frequência do dataset como peso.
2. Comparar a passagem do pior para o melhor nível de cada critério na perspectiva
   da necessidade de prioridade. Registrar relações de importância e faixas aceitas,
   com justificativa e responsável; não converter uma ordem verbal em percentuais.
3. Revisar os dez pares da configuração demonstrativa e acrescentar casos de troca
   entre critérios, incluindo pacientes da mesma especialidade quando pertinente.
   Obter 10–20 comparações aprovadas com motivo e evidência, sem usar espera.
4. Executar viabilidade. Se houver conflito, apresentar seus IDs para os responsáveis;
   não modificar uma preferência humana sem registro de revisão.
5. Versionar a configuração aprovada e distinguir seu alcance (protótipo sintético
   ou outra finalidade formalmente definida). Assinatura de configuração não equivale
   à validação do produto inteiro nem autoriza envio de dados reais a serviço externo.

## Ficha de decisão

- Critério/protocolo e versão:
- Decisão e alternativas consideradas:
- Evidência/fonte:
- Escala, direção, amplitude e exceções:
- Ausência de informação e condição de revisão:
- Relação com outros critérios e prevenção de dupla contagem:
- Pares de referência e faixas de swing, quando aplicáveis:
- Responsável pela decisão e data:
- Situação: pendente / aprovada para demonstração / requer revisão:

Os campos estão intencionalmente em aberto. Não atribuir assinatura, CRM ou aprovação
às profissionais mencionadas pelo usuário sem manifestação correspondente.
