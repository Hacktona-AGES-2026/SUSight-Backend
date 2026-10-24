> Revisão pendente em 2026-10-24: este documento descreve a implementação anterior. A spec revisada remove espera da pontuação, dos desempates e das travas. Adaptar este documento e revalidar preferências antes de implementar; ver `../../docs/clinical-review-2026-10-24.md`.

# Tarefas: Pontuação da fila

Plano: ./plan.md

- [x] Criar contrato de preferências, escalas e fontes.
- [x] Preparar critérios e SWALIS com evidências e revisão.
- [x] Implementar funções marginais, viabilidade e conflito de restrições.
- [x] Implementar função representativa e relações necessária/possível/incerta.
- [x] Aplicar precedências rígidas e exportar CSV reproduzível.
- [x] Testar solver, equidade, empates e verificador oficial na integração sintética.

- [x] Resolver o conflito técnico por hierarquia explícita antes da ROR, com regressão de dominância e distinção da origem da relação.
- [ ] Obter validação clínica das escalas e preferências; os escores são demonstrativos.
- [x] Exportar a base completa da demonstração (925 posições) e executar o verificador oficial com resultado OK.
- [x] Repetir a execução e conferir CSV, relações, função e decisões reproduzíveis.
- [x] Publicar origem dos swings, faixas, comparação por grupo e prazo de expiração sem atribuição bibliográfica indevida.
