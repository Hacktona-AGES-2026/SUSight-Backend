# Plano: Lista e detalhe de propostas para revisão médica

Spec: ./spec.md
Status: implementado

## Abordagem

Duas rotas de leitura sobre o que o `Store` já guarda: propostas, parecer, evidências
aprovadas, decisões, fila vigente e a trilha de eventos (spec 004). Nenhuma tabela nova.
A única mudança de escrita é a importação da fila aceitar três campos opcionais que
a pontuação já produz no `fila.json`.

A implementação sai empilhada sobre os PRs das specs 004 a 001 (#13 a #18), porque usa
a trilha de eventos, a fixture `history_api` e a autenticação por sessão.

## Dados e interfaces

**`QueuePatient`** (importação da fila) ganha, todos opcionais:

- `criterios`: objeto com as chaves `limitacao`, `asa`, `dor`, `comorbidades`, `deterioracao` e `distancia` (números); chave desconhecida é recusada.
- `swalis`: `A1` | `A2` | `B` | `C` | `D`.
- `prioridade_regulacao`: texto até 20 caracteres, só informativo.

**`GET /propostas?situacao=...`** (profissional; repetir `situacao` para várias; padrão `pronta_para_medico`):

```json
{
  "total": 1,
  "propostas": [
    {
      "proposta_id": "…",
      "solicitacao_id": "20",
      "situacao": "pronta_para_medico",
      "posicao_atual": 20,
      "posicao_proposta": 18,
      "recomendacao": "aprovar",
      "ordenacao_incerta": true,
      "evidencias_conflitantes": false,
      "criada_em": "2027-01-15T08:00:00+00:00"
    }
  ]
}
```

**`GET /propostas/{id}`** (profissional do caso): os campos do item, mais `swalis`,
`prioridade_regulacao`, `criterios`, `evidencias` (`evidencia_id`, `tipo`, `resultado`,
`data`, `trecho`, `pagina`, `revisor`, `revisado_em`), `parecer` (o mesmo objeto de
`/parecer`: `manifestacoes`, `recomendacao`, `divergencias`, `travas`, `posicao`),
`historico` (eventos da spec 004) e `decisao` (`acao`, `motivo`, `responsavel`,
`data_hora`, ou `null`).

**`Store`**:

- `list_proposals(statuses, patients)`: propostas não expiradas com situação em `statuses`, ordenadas por `created_at`; `posicao_atual` vem da fila vigente; o vínculo com o paciente vem da fila ou, se a solicitação saiu dela, da trilha de eventos; `patients=None` para o admin.
- `proposal_detail(pid)`: proposta não expirada, evidências citadas no corpo (registro em `evidence` com o documento), última decisão em `decisions` e `history(sid)`.

## Decisões

| Decisão | Alternativas consideradas | Motivo |
|---|---|---|
| Ler do que já existe, sem tabela nova | Tabela de resumo de propostas | Nada a sincronizar; a fonte continua única. |
| Critérios vindos da fila importada | Recalcular a pontuação na consulta | A pontuação é um processo à parte, com versão e auditoria; recalcular na API mudaria resultados. |
| `posicao_atual` da fila vigente | Posição gravada na criação | O médico decide sobre a fila de agora; a versão antiga já invalida a proposta. |
| Nomes dos campos em português, no padrão do backend | Contrato em inglês do web | Decisão do usuário: o web se adapta às rotas atuais. |
| Lista inteira, sem paginação | Paginação | Poucas propostas abertas na demonstração; ver questão em aberto da spec. |

## Riscos

- Com o #11 (camada SWALIS), importar `swalis` faz a validação da fila exigir a ordem por classe dentro do grupo protegido. Uma `fila.json` gerada antes do #11 seria recusada: regenerar a fila com a pontuação atual antes de importar.
- O trecho das evidências é dado sensível do documento: só sai para o profissional do caso, como já acontece em `GET /evidencias/{id}`.
- Decisões expiram com a proposta (7 dias); o histórico da spec 004 continua guardando a ação depois disso.
