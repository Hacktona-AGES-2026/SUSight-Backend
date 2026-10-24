# Plano: Extração de dados de exames e laudos (dados e persistência)

Spec: ./spec.md
Status: rascunho

## Abordagem

Este plano cobre só a camada de dados. A ferramenta de leitura, o provedor de IA e o mascaramento serão detalhados em seções próprias antes da implementação.

Mantém o SQLite (`sqlite3` da biblioteca padrão) já usado pelo Tribunal. Nada novo de infraestrutura; se outro banco for escolhido, só a camada de gravação muda. Valem as mesmas restrições atuais: um único worker por banco e `secure_delete`.

## Dados e interfaces

Tabelas novas ou alteradas. Todas expiram junto com o documento (até 7 dias do envio).

**`consents`** (novo): `id`, `document_id`, `termo_versao`, `actor`, `accepted_at`, `expires`. Sem aceite explícito, o documento não é criado nem processado.

**`documents`** (alterado): mantém `id`, `sid`, `actor`, `created_at`, `expires`. Passa a registrar `origem` (`paciente` | `medico`), `formato`, `paginas`, `situacao` (`recebido` | `ilegivel` | `rejeitado` | `extraido` | `aprovado`) e `avisos` (JSON: qualidade, manuscrito, mascaramento). O arquivo físico e seus derivados ficam sob o mesmo `expires`.

**`extraction_fields`** (novo): um registro por campo do resultado.
- `id`, `document_id`, `campo` (`limitacao_funcional` | `asa` | `dor` | `socioeconomico` | `comorbidades` | `tipo_documento` | `data_documento`)
- `valor_extraido` (JSON, `null` se ausente), `situacao` (`presente` | `ausente` | `incerto` | `ilegivel` | `conflitante`)
- `confianca` (`alta` | `media` | `baixa` | `null`), `requer_revisao`, `expires`

Os sete campos sempre existem por documento, mesmo `null`. Campos com lista (comorbidades, socioeconômico) guardam um item por entrada no JSON, cada um com sua confiança e evidência.

**`evidence`** (alterado): ganha `field_id` (liga ao campo de origem), `trecho`, `pagina` e `regiao`. Mantém `reviewer`, `reason`, `reviewed_at`. Todo valor não nulo precisa de ao menos uma evidência.

**`field_reviews`** (novo): `id`, `field_id`, `reviewer`, `acao` (`aprovar` | `corrigir` | `rejeitar`), `valor_corrigido` (JSON), `reviewed_at`. O valor extraído nunca é sobrescrito: a correção do médico fica nesta tabela, e a aprovação não altera a fila.

Migração: `CREATE TABLE IF NOT EXISTS` e `ALTER TABLE ... ADD COLUMN` com a mesma checagem de `PRAGMA table_info` já usada em `store.py`. Linhas antigas recebem `expires` conservador (0).

## Decisões

| Decisão | Alternativas consideradas | Motivo |
|---|---|---|
| Campo como linha própria, valor em JSON | Uma coluna por campo; só JSON em `documents.body` | Revisão e evidência por campo, sem esquema rígido para listas |
| Correção em `field_reviews`, valor original intacto | Sobrescrever o valor extraído | A spec exige distinguir extração de correção profissional |
| Consentimento em tabela própria | Colunas em `documents` | Aceite é anterior ao documento e deve ficar auditável |
| Manter SQLite | Postgres | Zero infraestrutura no hackathon; mesmo banco do Tribunal |

## Riscos

- Expiração parcial deixar derivados órfãos: limpar `documents`, campos, evidências, revisões e arquivos na mesma operação, com teste.
- Conteúdo de documento, nome ou CNS em log: guardar só ids e contagens nos registros operacionais.
- Classes ASA ou escalas de dor fora do domínio da pontuação: guardar o valor de origem e marcar `requer_revisao`, sem converter.
