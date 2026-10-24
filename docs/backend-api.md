# API e tribunal

Executar a factory `susight.api:create_app` com um worker. Configurar
`SUSIGHT_API_TOKEN` (mínimo 16 caracteres) e `SUSIGHT_DATABASE`. O token é um controle
compartilhado da demo local; não implementa login gov.br, CRM ou identidade médica
verificada. Cada decisão registra o nome informado pelo profissional.

| Método/rota | Comportamento |
|---|---|
| `GET /health` | Estado do serviço, sem autenticação. |
| `GET /fila` | Versão e pacientes da fila vigente. |
| `PUT /fila` | Importa fila válida com `versao_esperada`; primeira importação usa 0. |
| `POST /propostas` | Cria proposta ligada à versão da fila, com posição e evidências estruturadas. |
| `POST /propostas/{id}/tribunal` | Solicita análise/reprocessamento; trava determinística pode barrar sem LLM. |
| `GET /propostas/{id}/parecer` | Situação, tentativas, aviso e parecer persistido. |
| `POST /propostas/{id}/decisao` | Aprova, rejeita com motivo ou pede informações; grava auditoria. |

As rotas clínicas exigem header Bearer. OpenAPI em `/docs` documenta os schemas.
Para importar `fila.json` da pontuação, selecionar por paciente apenas os campos do
schema `QueuePatient`: `solicitacao_id`, `cid`, `dias_em_fila`, `pontuacao`,
`oncologico`, `sem_urgencia`, `sem_urgencia_verificador` e `posicao`. Não enviar
critérios ou outras chaves nessa importação: o schema rejeita campos extras.

Exemplo de criação de proposta (com fila vigente na versão 1):

```json
{
  "solicitacao_id": "SOL-EXEMPLO",
  "posicao_proposta": 18,
  "versao_fila": 1,
  "ordenacao_incerta": true,
  "evidencias_conflitantes": false,
  "evidencias": [
    {"evidencia_id": "EVT-EXEMPLO", "tipo": "biopsia", "resultado": "positivo", "data": "2026-10-01"}
  ]
}
```

Na demo, a aplicação chamadora autenticada fornece o indicador de incerteza e as
evidências; não há upload de laudo, extração de documentos nem consulta automática
do tribunal aos arquivos tratados. Esses fluxos pertencem a outras issues, ainda
sem spec. Atualizar a classificação clínica de um paciente exige importar uma nova
versão válida da fila antes de propor reposicionamento.

## Gemini e segurança das decisões

Configurar `GEMINI_API_KEY` e `GEMINI_MODEL` conforme a conta disponível. Modelo/cota
não são presumidos. O adaptador usa `google-genai` com saída JSON validada por
Pydantic, tempo limite de 30 segundos e três chamadas paralelas. Não usa ferramentas
nem execução de comandos do modelo; o "terminal" das fotos não foi definido como
parte desta spec e não é implementado como execução arbitrária.

O contexto contém pseudônimo, CID, espera, pontuação, posições e códigos estruturados
de evidências. Nome, CNS, município e textos livres não são enviados. Isso limita os
dados compartilhados e não é uma declaração de anonimização clínica completa.
Respostas têm validação de papel, referências, posição e um filtro lexical básico;
a ausência de diagnóstico/alarme ainda exige conferência humana do conteúdo.

Falhas persistem em SQLite: backoff de 5 segundos a 300 segundos; na terceira falha,
aviso `tribunal_indisponivel`. Sem chave ou modelo, o mesmo fluxo registra a falha,
sem gerar parecer fictício. Ao reiniciar o processo único, propostas interrompidas
são recolocadas na fila. Não executar vários workers ou instâncias no mesmo banco.

Parecer é consultivo. A maioria define recomendação; três votos diferentes pedem
ajuste; divergências ficam registradas. Relato isolado não sustenta voto favorável
do agente de Evidências. Sugestões de ajuste passam novamente pelas travas.

Aprovação médica revalida versão e travas e aplica mudança em transação junto à
auditoria. Discordar de recomendação negativa exige justificativa. Mudança da versão
invalida a proposta: criar nova proposta para análise. Rejeição registra o motivo;
a reavaliação automática após rejeição pertence à issue #9, fora das specs implementadas.

Referência do provedor: https://ai.google.dev/gemini-api/docs/generate-content/structured-output
