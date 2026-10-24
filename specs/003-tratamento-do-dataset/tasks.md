# Tarefas: Tratamento do dataset

Plano: ./plan.md

Cada tarefa corresponde a um commit atômico com suas verificações. Executar após aprovação do plano. Caminhos de código são propostos; se o setup da equipe introduzir estrutura equivalente, ajustar o plano antes de implementar.

- [ ] 1. Criar pacote Python e testes: `pyproject.toml`, `src/susight/__init__.py`, `src/susight/dataset/__init__.py`, `tests/dataset/test_package.py`. Validar importação e registrar pytest como dependência de desenvolvimento.
- [ ] 2. Implementar leitura e proveniência: `src/susight/dataset/io.py`, `tests/dataset/test_io.py`. Ler os três CSVs e referências, preservar arquivo/linha e valores originais, calcular hashes e recusar sobreposição de entrada/saída.
- [ ] 3. Validar contratos de entrada: `src/susight/dataset/validation.py`, `tests/dataset/test_validation.py`. Distinguir erro estrutural de pendência por registro; cobrir IDs conflitantes, colunas ausentes e medidas inválidas.
- [ ] 4. Normalizar categorias, CID e datas: `src/susight/dataset/normalization.py`, `tests/dataset/test_normalization.py`. Preservar originais, usar catálogo e referência fixa, testar equivalências e espera inválida.
- [ ] 5. Definir regras versionadas e extrair indícios: `src/susight/dataset/rules.json`, `src/susight/dataset/evidence.py`, `tests/dataset/test_evidence.py`. Guardar fonte/trecho, distinguir negação, incerteza, relato e evidência documentada; testar frases negativas para exclusão.
- [ ] 6. Consolidar solicitações compatíveis: `src/susight/dataset/consolidation.py`, `tests/dataset/test_consolidation.py`. Produzir aliases e canônica estável; testar contexto desconhecido, lateralidade, episódio distinto e conflitos de medidas.
- [ ] 7. Tratar eventos: `src/susight/dataset/events.py`, `tests/dataset/test_events.py`. Deduplicar antes de redirecionar aliases, preservar IDs, conferir paciente e separar órfãos, histórico e futuros.
- [ ] 8. Determinar atividade e pendências: `src/susight/dataset/activity.py`, `tests/dataset/test_activity.py`. Reunir evidências dos aliases, aplicar saídas explícitas e testar contradição, retomada, faltas e contatos sem resposta.
- [ ] 9. Preparar medidas com imputação rastreável: `src/susight/dataset/imputation.py`, `tests/dataset/test_imputation.py`. Calcular população fixa, medianas por especialidade e convenção ordinal; testar ausência total e prevenção de imputação em cascata.
- [ ] 10. Gerar relatórios e contratos de saída: `src/susight/dataset/reporting.py`, `tests/dataset/test_reporting.py`. Emitir os sete arquivos do plano, reconciliar cobertura e eventos e impedir publicação sobre destino existente.
- [ ] 11. Orquestrar pipeline e CLI: `src/susight/dataset/pipeline.py`, `src/susight/dataset/__main__.py`, `tests/dataset/test_pipeline.py`. Garantir saída de erro estrutural, publicação apenas ao concluir e reprodução substantiva entre execuções.
- [ ] 12. Documentar execução e conferir dataset fornecido: `docs/dataset-treatment.md`, `.gitignore`, `tests/dataset/test_integration.py`. Ignorar saídas geradas, usar fixtures sintéticas nos testes e registrar contagens e hashes da execução local de aceitação, sem depender do caminho pessoal nos testes automatizados.

## Conclusão

- [ ] Conferir os 17 critérios de aceite da spec e registrar resultados no PR da implementação.
- [ ] Revisar `DECISOES.md` e todas as exclusões/consolidações da execução de aceitação.
- [ ] Verificar que a spec 002 consegue consumir medidas, evidências, imputações e pendências do contrato publicado.
