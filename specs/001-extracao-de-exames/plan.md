# Plano: Extração de dados de exames e laudos (dados e persistência)

Spec: ./spec.md
Status: em revisão

## Abordagem

Camada de dados abaixo, seguida de leitura, mascaramento, provedor e rotas.

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

### Ajuste na implementação (2026-10-24)

- As evidências de cada campo ficam em JSON no próprio `extraction_fields` (`evidencias`: lista de `trecho` e `pagina`). A tabela `evidence` continua só com as evidências do tribunal, que têm outro formato (tipo e resultado clínico); misturar quebraria as garantias do tribunal.
- O arquivo fica em `document_files` (`document_id`, `conteudo`, `expires`), apagado junto do documento.
- `documents.body` guarda `origem`, e `extractions` (`document_id`, `situacao`, `avisos`, `updated_at`, `expires`) guarda a situação da leitura: `pendente` | `revisao_manual` | `extraido`.

## Leitura, mascaramento e provedor

1. `POST /documentos/arquivo` recebe `solicitacao_id`, `tipo_mime`, `conteudo_base64`, `termo_versao`, `aceite_termo: true`, `sintetico: true` e `pedido_id` opcional. Recusa (422, sem gravar nada) sem aceite ou com versão do termo diferente da vigente, arquivo vazio, bytes que não correspondem ao formato, mais de 10 MiB, PDF com mais de 10 páginas, PDF protegido ou ilegível e formatos fora de PDF, JPEG e PNG. Aceito, registra o documento pelo fluxo existente (trilha, notificações e pedido), o arquivo e o aceite.
2. `POST /documentos/{id}/extracao`: PDF com texto é lido por página com `pypdf`; imagem ou PDF sem texto vai para `revisao_manual`, sem chamar o extrator. O texto é mascarado (CNS, CPF e linhas rotuladas `Nome`/`Paciente`) e verificado; se sobrar sequência de 11 ou mais dígitos ou rótulo sem máscara, nada é enviado e a situação é `revisao_manual`. Sem provedor configurado, `pendente` com aviso.
3. A saída do extrator passa por validação própria antes de gravar: os sete campos sempre existem; campo ausente fica `null`; valor sem trecho que exista no texto mascarado da página citada vira `null` com revisão; confiança só `alta`, `media`, `baixa` ou `null`, e `baixa` vira `null` com revisão; situação diferente de `presente` vira `null` com revisão, preservando as evidências; ASA só I a VI; limitação só nenhuma, leve, moderada ou grave; data só `AAAA-MM-DD` válida; tipo só os previstos; dor preserva intensidade, escala e descrição. Campos extras, como tempo de espera, são ignorados.
4. `GET /documentos/{id}/extracao` devolve situação, avisos e os sete campos com a última revisão. `POST /documentos/{id}/campos/{campo}/revisao` (profissional) aprova, corrige (exige `valor_corrigido`) ou rejeita, com justificativa; aprovar valor `null` é recusado. Nada disso altera a fila.

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
