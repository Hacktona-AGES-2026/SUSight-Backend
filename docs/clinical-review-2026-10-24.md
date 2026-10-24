# Revisão clínica e de regulação — 2026-10-24

Status: requisitos em revisão; implementação pendente.

Origem: anotações de conversa clínica transmitidas pelo usuário. Não constituem
assinatura, confirmação de CRM ou aprovação formal das profissionais mencionadas.
As referências públicas abaixo sustentam apenas as afirmações identificadas;
não validam numericamente o modelo do protótipo.

## Decisão confirmada pelo usuário

**Tempo de espera não tem relevância para priorizar.** Remover dias em fila e razão
SWALIS da pontuação, das preferências ROR, de desempates e de travas de movimento.
Conservar datas para acompanhamento, rastreabilidade e validade de evidências.
Deterioração clínica observada continua distinta do tempo decorrido: mudar a data
de entrada não cria piora clínica. Empates usam identificação estável.

A implementação atual ainda usa espera. As specs 002 e do tribunal foram revistas;
planos, tarefas e código anteriores precisam ser adaptados antes da nova aceitação.
Não reutilizar os swings demonstrativos antigos como se fossem pesos clínicos.

## Insumos relatados e tratamento proposto

| Insumo da conversa | Encaminhamento para a próxima revisão |
|---|---|
| CID e fatores de risco têm maior importância | Identificar diagnóstico registrado, gravidade, fatores de risco e evidência separadamente; elicitar relações e faixas de swing com responsáveis clínicos. Não inventar percentuais. |
| Câncer → cardiovascular → traumas; condições M mais ao final | Registrar como hipótese relatada. Não ordenar todos os casos apenas pela letra do CID; faltam protocolo por condição, gravidade, exceções e comparações concretas aprovadas. Preservar a regra oncológica específica do desafio. |
| Mortalidade × morbidade | Distinguir risco documentado à vida, progressão e perda funcional; não atribuir a um indivíduo taxas populacionais nem produzir prognóstico automático. |
| Idade tem menor importância | Não introduzir peso isolado de idade; a idade não é critério independente no modelo atual. Contextualização clínica depende de evidência e protocolo. |
| Parecer Telessaúde como apoio especializado | Guardar parecer, origem, data, protocolo aplicável e revisão profissional. Não conceder bônus fixo por existir parecer nem assumir que equivale a um exame. |
| ASA com porte do procedimento | Analisar conjuntamente para contextualizar risco e necessidade de revisão. ASA maior não implica automaticamente maior urgência; rever essa premissa da spec 002 antes de uso clínico. |
| Questionar se a pessoa precisa permanecer na fila | Ampliar Contestação com BRAN e encaminhar dúvida de indicação ao médico. Sem exclusão automática e sem interpretar falta de documento como cirurgia desnecessária. |
| Termo no upload | Incluir informação prévia, aceite explícito e versão auditável do termo; texto final e finalidade devem ser aprovados pelos responsáveis do produto antes da implementação. |

## Regulação: o que foi confirmado

- GERCON atende à regulação de consultas e exames; GERINT contempla internações,
  inclusive acompanhamento de filas de cirurgias eletivas. São fluxos relacionados,
  sem presumir que um pedido de consulta seja indicação cirúrgica aprovada.
- Os protocolos do RegulaSUS/TelessaúdeRS apoiam qualificação dos encaminhamentos e
  identificação de casos que precisam de especialista e de maior prioridade.
  As fontes consultadas não demonstram um bônus numérico universal por parecer.
- A SES/RS denomina sua central hospitalar CRH. A sigla anotada como “CERH” precisa
  ser confirmada no contexto da conversa; não criar integração baseada na sigla.
- CID, especialidade, gravidade, idade, sexo, comorbidades e fatores de risco foram
  relatados como informações do encaminhamento. Não se confirmou aqui o esquema
  completo dos campos da versão local do GERCON nem contrato de integração.

## ASA × porte: análise necessária

`procedimentos.csv` contém `porte`, `risco_cirurgico`, `duracao_media_min` e
`necessita_uti`. A próxima análise deve vincular solicitações por procedimento,
mostrar contagens e proporções de ASA por porte e especialidade, ausências e tamanho
dos grupos. Separar ASA observado de imputado e evitar contar duplicatas como casos
independentes. Tabela de contingência é uma primeira saída mais interpretável do
que um coeficiente isolado sobre rótulos ordinais.

Associação no dataset sintético não demonstra causalidade, benefício de operar antes
ou peso de prioridade. Porte não preenche ASA ausente. A ASA descreve estado físico;
o tipo de cirurgia e outros fatores também participam da avaliação perioperatória.
A conversão desses dados em preferência permanece pendente de validação clínica.

## BRAN e Contestação

Referência encontrada: **Benefits, Risks, Alternatives, Nothing**, usado em decisão
compartilhada. Aplicação proposta ao caso:

1. Benefícios: qual benefício esperado está documentado para este procedimento?
2. Riscos: quais riscos do procedimento e de adiar estão documentados?
3. Alternativas: existem alternativas registradas ou informação a solicitar ao médico?
4. Não realizar: quais consequências de não realizar ou de adiar foram documentadas?

Cada resposta distingue evidência, ausência e conflito. O agente não prescreve
alternativas, não determina desnecessidade e não cancela a solicitação. Permanecem
três agentes e convocação para casos incertos/conflitantes. Revisão sistemática da
indicação de toda a fila exigiria escopo próprio. BRAN não define pesos de ROR.

## Termo no upload: conteúdo proposto

Antes de enviar, informar finalidade do documento, campos procurados, acesso pelos
profissionais autorizados, prazo de guarda aplicável, uso ou ausência de serviço
externo e que a extração apenas propõe informações sujeitas à revisão profissional.
Explicar que o envio não garante alteração de posição e não substitui atendimento.
Oferecer leitura do termo e aceite sem seleção prévia; registrar versão, identidade,
data e hora junto ao envio. Sem aceite, não processar o upload; oferecer caminho
para orientação sobre envio pelos canais assistenciais existentes.

Não embutir autorização genérica para qualquer uso de IA. O aceite não autoriza
uso clínico de um protótipo nem define sozinho a base legal do tratamento. O MVP
continua exclusivamente sintético. O texto final, a finalidade do termo e o fluxo
alternativo precisam ser definidos pelo produto. Upload de arquivo e tela de aceite
não estão implementados neste backend; hoje há registro de metadados de documento.

## Aceitação da próxima implementação

- Alterar apenas espera/data de entrada, sem alterar evidência clínica ou validade,
  mantém pontuação, relações, posições, desempates e decisões das travas.
- Nenhum peso, restrição ou comparação usa antiguidade como preferência oculta.
- Novas faixas de swing e pares de referência têm fonte e responsável; premissas
  demonstrativas permanecem identificadas e não recebem atribuição clínica falsa.
- Executar novamente o dataset completo e o verificador original, sem alterar suas
  regras para acomodar o modelo; divergências são registradas explicitamente.
- BRAN com informação ausente gera revisão, sem exclusão, diagnóstico ou prescrição.
- O aceite do termo é específico à versão e precede o envio/processamento; nenhuma
  evidência é promovida a dado aprovado apenas porque houve aceite do termo.

## Referências consultadas

- [SES/RS — Protocolos de encaminhamento](https://saude.rs.gov.br/protocolos-de-encaminhamento): finalidade do RegulaSUS e qualificação das filas.
- [Porto Alegre — Sistemas e soluções digitais](https://prefeitura.poa.br/sms/sistemas-e-solucoes-digitais): escopos GERCON e GERINT.
- [RS — Central de Regulação Hospitalar](https://www.rs.gov.br/carta-de-servicos/servicos?servico=2383): denominação CRH e atuação hospitalar.
- [Ministério da Saúde — Regulação do acesso](https://www.gov.br/saude/pt-br/composicao/saes/drac/regulacao-do-acesso): protocolos, encaminhamento e classificação de risco.
- [ASA — Classificação de estado físico](https://doi.org/10.1097/ao9.0000000000000002): estado físico e avaliação de risco em conjunto com outros fatores.
- [NHS Scotland — BRAN](https://www.rightdecisions.scot.nhs.uk/realistic-medicine-national-toolkit-for-professionals/quick-access-to-patient-care-resources/bran-helping-patients-ask-the-right-questions/): perguntas para pacientes e profissionais na decisão compartilhada.
