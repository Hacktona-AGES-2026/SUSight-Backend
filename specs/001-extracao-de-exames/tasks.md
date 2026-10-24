# Tarefas: Extração de dados de exames e laudos

Plano: ./plan.md

- [x] 1. Testes primeiro, commitados antes do código (`tests/test_extraction.py`, 22 casos vistos falhando; PDFs sintéticos gerados em `tests/pdfs.py` e extrator falso).
- [x] 2. Dependência `pypdf` e módulo `susight/extraction.py`: validação de arquivo, leitura, mascaramento e validação da saída.
- [x] 3. Tabelas `consents`, `document_files`, `extractions`, `extraction_fields` e `field_reviews`, com expiração junto do documento.
- [x] 4. Rotas de envio, extração, consulta e revisão por campo.
- [x] 5. Extrator Gemini, só para texto mascarado de documento sintético; sem configuração, `pendente`.
- [x] 6. Rodar a suíte completa, Ruff e formatação: 139 testes passando.
- [ ] 7. Conjunto de 40 documentos sintéticos com gabarito, avaliado contra o provedor real (pendente: exige chave e revisão humana).
- [ ] 8. Texto final do termo e canal assistencial alternativo, aprovados pelo produto (hoje há uma minuta).
- [ ] 9. Ligar as situações `em_analise` e `atendido` dos exames pedidos (spec 006) ao estado da extração, em vez da revisão manual de evidências.
