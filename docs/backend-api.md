# API, acesso e evidências da demonstração

Executar `susight.api:create_app` com um worker. O ambiente aceita apenas dados
sintéticos; os papéis locais não implementam identidade gov.br/CRM verificada.

## Identidades e permissões

```sh
uv run --no-sync python -m susight.provision --directory data/identidades --patient PAC-EXEMPLO
```

O comando cria `access.json` com hashes dos tokens e três arquivos `.token`, todos
privados ao proprietário. Não imprime os valores dos tokens. Configurar
`SUSIGHT_ACCESS_FILE=data/identidades/access.json`; não versionar esse diretório.
O operador provisiona os vínculos de paciente na configuração local; a API não aceita
papel ou escopo declarado pelo cliente.

- Administrador: importação da fila e manutenção dos casos sintéticos.
- Médico: acesso, revisão e decisão apenas nos pacientes atribuídos.
- Paciente: consulta de seus próprios registros e registro de fonte/evidência proposta;
  não pode aprovar evidência, obter debate interno nem decidir posição.

`SUSIGHT_API_TOKEN` continua como acesso administrativo de bootstrap para compatibilidade,
sem representar login de paciente. Com `SUSIGHT_ACCESS_FILE`, o token compartilhado
não é usado. Rotas usam `Authorization: Bearer <token individual>`; `/health` é pública.
Decisões e revisões gravam a identidade autenticada, não o nome declarado no corpo.

## Rotas

| Método/rota | Uso |
|---|---|
| `GET /fila` | Versão e registros permitidos ao usuário. |
| `PUT /fila` | Importação administrativa, controle de versão e autoria. |
| `POST /documentos` | Registro da fonte sintética por hash, solicitação, formato, tamanho e páginas. |
| `GET /documentos/{id}` | Metadados da fonte, sujeitos à permissão e validade. |
| `POST /evidencias` | Valor proposto, trecho, campo, página, confiança e referência à fonte. |
| `GET /evidencias/{id}` | Evidência e histórico da revisão permitidos ao caso. |
| `POST /evidencias/{id}/revisao` | Aprovação/rejeição pelo profissional autorizado, com justificativa. |
| `POST /propostas` | Cria proposta usando somente IDs de evidências aprovadas no servidor. |
| `POST /propostas/{id}/tribunal` | Análise ou reprocessamento de proposta válida. |
| `GET /propostas/{id}/parecer` | Parecer interno para profissional do caso. |
| `POST /propostas/{id}/decisao` | Aprovação, rejeição com motivo ou pedido de informações. |
| `POST /propostas/{id}/cancelar` | Encerra trabalho pendente com justificativa auditável. |
| `GET /solicitacoes/{id}/historico` | Trilha de eventos da solicitação, do mais recente ao mais antigo (spec 004). |
| `GET /solicitacoes/{id}/exames-pedidos` | Exames pedidos pelo médico, com situação e contagem de pendentes (spec 006). |
| `POST /solicitacoes/{id}/contestacao` | Contesta a posição com motivo; a solicitação fica em reavaliação (spec 008). |
| `POST /solicitacoes/{id}/contestacao/conclusao` | Conclui a reavaliação mantendo a posição, com justificativa (spec 008). |
| `GET /fila/exportacao.csv` | CSV `solicitacao_id,posicao,justificativa` da fila vigente; registra o export (spec 008). |

`pedir_informacoes` exige `exames` (até 10, cada um com `exame` e `explicacao` opcional);
as demais decisões recusam o campo. `POST /documentos` aceita `pedido_id` para ligar o
envio a um pedido `pendente` da mesma solicitação. A situação do pedido avança sozinha:
`recebido` no envio, `em_analise` na primeira evidência e `atendido` na revisão dela.

OpenAPI em `/docs` contém campos e limites. Importar a fila selecionando de `fila.json`
os campos de `QueuePatient`, incluindo `paciente_id` e `politica: "priorizacao-sem-espera-v1"`; não enviar critérios ou outros
campos extras. A ausência de `paciente_id` não concede visibilidade a usuários com
escopo por paciente. Hierarquia e posições consecutivas são verificadas na importação.

Exemplo do corpo para criar proposta após revisar as evidências:

```json
{
  "solicitacao_id": "SOL-EXEMPLO",
  "posicao_proposta": 18,
  "versao_fila": 1,
  "ordenacao_incerta": true,
  "evidencias_conflitantes": false,
  "evidencias_ids": ["EVT-EXEMPLO"]
}
```

A API rejeita conteúdo de evidência embutido nessa operação. Busca no registro
aprovado tipo, resultado e data; confere o vínculo com a solicitação, a aprovação e
validade. Campo null ou de baixa confiança não pode ser aprovado diretamente;
corrigir exige novo registro, preservando a proposta e a revisão originais.

O registro documental desta etapa é de **proveniência**, não upload/OCR: o hash é
informado pelo sistema que detém o arquivo. O profissional precisa conferir o trecho
contra a fonte. A API não afirma que verificou automaticamente os bytes ou o texto
original, e não implementa a extração automática descrita na feature separada.
A integração impede usar proposta documental ainda não aprovada como dado confirmado.

## Validade e retenção

A trilha de histórico (tabela `events`) é a exceção: não expira, guarda só tipo,
texto fixo, responsável, motivo e data e hora, e nunca conteúdo de documento, nome ou
CNS. A permissão de leitura usa o vínculo do evento com o paciente.

Registros expiram em até sete dias. Proposta e decisão herdam o menor prazo entre
fila e evidências; um reprocessamento não renova a validade. Registros expirados são
removidos junto às dependências; não são publicados pareceres de referência expirada.
Cancelamento durante chamada também impede que o retorno reative a proposta.

Limpeza do banco ocorre nas operações e em manutenção periódica do processo.
`SUSIGHT_ARTIFACT_ROOT=outputs` permite limpar diretórios gerados da demonstração;
fora do serviço, executar `python -m susight.cleanup --root outputs`. Apenas diretórios
marcados com manifesto válido são alvos; fontes CSV originais, diretórios sem marcação
e alvos de links simbólicos são preservados. Saídas têm diretório 0700 e arquivos 0600.
A remoção física depende de executar o serviço ou a rotina de manutenção; manter essa
rotina ativa é requisito operacional. Backups externos precisam de política própria.

Migração de bancos legados sem instante de criação confiável expira conservadoramente
os dados antigos e exige nova importação; o contador de versão não é reutilizado.
SQLite usa `secure_delete`, mas isso não é promessa de apagamento forense do dispositivo.
Não executar múltiplos workers sobre o mesmo banco.

## Tribunal sem mudança no provedor

O cliente existente continua configurável por `GEMINI_API_KEY`/`GEMINI_MODEL`, sem
presumir modelo ou cota. Nesta entrega não foi feito teste real nem chamada externa.
Testes usam transporte/cliente substituído apenas no ambiente de testes.

Cada chamada tem limite de 30 segundos. Falhas mantêm a proposta retida, com espera
de cinco a 300 segundos; a terceira falha exibe indisponibilidade. Identidade de agente,
posição e referências são conferidas; apoio ou ajuste sem citar evidência é inválido.
O contexto externo contém somente pseudônimos e códigos aprovados, sem os trechos
originais, valores livres, nome ou CNS. A validação lexical não é revisão clínica.

O médico pode discordar do parecer mediante justificativa, respeitando as travas.
Somente sua decisão explícita e transacional muda a fila. Mudança de versão exige
nova análise. Reavaliação automática após rejeição continua fora desta feature.

## Migração da política de prioridade

Cada item importado exige a versão `priorizacao-sem-espera-v1`. O banco registra
a política da fila; bancos anteriores recebem a marca `legado`, sem converter
pontuações antigas. A leitura não oferece essa fila como vigente; regenerar e
reimportar com a versão esperada do contador, que não é reiniciado.

Reimportação marca propostas pendentes e prontas como `desatualizada`; pareceres
anteriores permanecem para auditoria. O retorno de uma análise em andamento não
reativa a proposta. Aplicar uma decisão exige fila/política vigente, além das
verificações existentes. Nenhuma trava ou contexto externo usa dias de espera.

BRAN permanece planejado no complemento da spec do tribunal; não foi implementado
nem testado com um provedor real. O termo antes do upload tem [plano e minuta](upload-term-plan.md);
registro de metadados não implementa aceite nem recebimento de arquivo.
