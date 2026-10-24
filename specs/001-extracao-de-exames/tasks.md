# Tarefas: Extração de dados de exames e laudos

Plano: ./plan.md

- [ ] 1. Testes primeiro, commitados antes do código (`tests/test_extraction.py`, com PDFs sintéticos gerados no teste e extrator falso).
- [ ] 2. Dependência `pypdf` e módulo `susight/extraction.py`: validação de arquivo, leitura, mascaramento e validação da saída.
- [ ] 3. Tabelas `consents`, `document_files`, `extractions`, `extraction_fields` e `field_reviews`, com expiração junto do documento.
- [ ] 4. Rotas de envio, extração, consulta e revisão por campo.
- [ ] 5. Extrator Gemini com esquema estruturado, só para texto mascarado de documento sintético.
- [ ] 6. Rodar a suíte completa, Ruff e formatação.
- [ ] 7. Conjunto de 40 documentos sintéticos com gabarito, avaliado contra o provedor real (pendente: exige chave e revisão humana).
