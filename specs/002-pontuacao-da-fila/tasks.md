# Tarefas: revisão clínica da pontuação da fila

Plano: ./plan.md
Status: implementação técnica autorizada em 2026-10-24; progresso abaixo

Cada tarefa de implementação vira um commit atômico. Marcar conclusão somente com
artefato ou verificação correspondente. Esta lista substitui a lista operacional
anterior; o histórico técnico está em `../../docs/backend-validation.md` e no Git.

## 1. Retirada da espera

- [x] 1.1 Registrar autorização de implementação do usuário; revisão clínica das escalas continua pendente.
- [x] 1.2 Mapear todos os usos de espera/data de entrada: pontuação, configuração, exemplos, desempates, pares, justificativas e travas; distinguir usos administrativos e temporais legítimos.
- [x] 1.3 Versionar contrato/modelo, rejeitar preferências antigas e adaptar dimensões e contribuições aos seis critérios demonstrativos restantes.
- [x] 1.4 Remover desempate e arestas por espera da ordenação, preservando relações necessárias, hierarquia e ID estável.
- [x] 1.5 Remover trava por espera do tribunal e conferir aplicação consistente antes do processamento e na decisão.
- [x] 1.6 Adaptar gerador de preferências e exemplos: sem swing de espera nem seleção de pares por antiguidade; indicar origem demonstrativa e insuficiência de pares quando existir.
- [x] 1.7 Atualizar justificativas para não apresentar espera/SWALIS como motivo de preferência.
- [x] 1.8 Verificar invariância de pontuação, relações, empates, ordem final e guardas quando só espera/data administrativa muda e os eventos/validade são preservados.

## 2. ASA × porte e dados para revisão

- [x] 2.1 Conferir junção por procedimento e relatar vínculos ausentes, divergências, cobertura e valores observados versus imputados.
- [x] 2.2 Produzir contagens e proporções ASA × porte por especialidade, com denominadores e ausências, sem tratar solicitações como pacientes independentes.
- [x] 2.3 Apresentar sensibilidade sem grupos suspeitos de duplicata; manter as solicitações na fila e explicitar que a duplicidade não foi confirmada.
- [x] 2.4 Inventariar CID, comorbidades, fatores de risco e evidências para discussão, separando afirmação, negação, suspeita e conflito.
- [x] 2.5 Entregar relatório agregado reprodutível, com limitações do dataset sintético e sem converter associação em peso.

## 3. Decisões clínicas e preferências

- [ ] 3.1 Revisar com responsáveis a relação ASA/porte/prioridade e registrar a decisão sobre a monotonicidade antiga.
- [ ] 3.2 Definir representação de CID/fatores de risco, exceções e prevenção de dupla contagem; revisar a spec antes de implementar novo critério.
- [x] 3.3 Revisar o escopo de elicitação profissional e documentar escalas, fontes e responsáveis.
- [ ] 3.4 Obter faixas de swing e 10–20 comparações justificadas sem preferência por espera; separar configuração demonstrativa da validada.
- [ ] 3.5 Conferir viabilidade e resolver conflitos com os responsáveis, sem relaxamento silencioso.

## 4. Consolidação e migração

- [ ] 4.1 Aplicar os critérios efetivamente aprovados no contrato e no solver; atualizar regressões de necessidade, empate, reversibilidade e precedência.
- [x] 4.2 Vincular saídas à versão da política/preferências e exigir reimportação versionada da nova fila.
- [x] 4.3 Impedir aplicação silenciosa de propostas antigas ou resultados em processamento de outra versão; preservar auditoria, cancelamento e retenção.

## 5. Dependências de outras specs

- [x] 5.1 Preparar plano do tribunal para Contestação com BRAN e evidência especializada, com revisão médica e sem exclusão autônoma.
- [x] 5.2 Preparar minuta e plano de termo para revisão do produto, com campos pendentes de responsável e canal alternativo; detalhar responsabilidades Backend/Web/app.

As tarefas 5.1–5.2 são planejamento das respectivas features, não implementação de
LLM, OCR ou upload. Chamadas reais a Gemini permanecem fora do escopo.

## 6. Aceitação e entrega

- [x] 6.1 Rodar regressões de invariância temporal, configuração antiga, versão da fila, hierarquia, autorização e retenção.
- [x] 6.2 Executar dataset completo e verificador oficial original; registrar contagens, exclusões, pendências e hashes observados.
- [x] 6.3 Repetir a execução e conferir reproduzibilidade do CSV, relações e função representativa.
- [x] 6.4 Atualizar exemplos e relatório de validação, distinguindo resultados técnicos de revisão clínica pendente.
- [ ] 6.5 Fazer revisão humana do resultado; atualizar o PR para `dev`, sem coautoria e sem realizar merge.

## Evidências desta execução

- Política sem espera aceita tecnicamente: 70 testes, Ruff e verificador original.
- Duas execuções completas: 925 posições; CSV, relações, função e decisões idênticos.
- Análise principal: 925 solicitações; sensibilidade: 881; 26 sem ASA observado.
- `docs/clinical-elicitation.md` prepara decisões e sessão; não registra respostas ou pesos médicos inventados.
- Etapas 3.1/3.2/3.4/3.5 dependem dos responsáveis clínicos. 4.1 refere-se ao modelo clínico posterior; a versão demonstrativa de seis critérios já funciona.
- BRAN e termo de upload têm planos; suas implementações funcionais não fazem parte das tarefas 5.1/5.2.
