# Validação da implementação — 2026-10-24

Escopo: specs 001 (tribunal), 002 (pontuação) e 003 (tratamento). Outras issues,
como upload/OCR, autenticação gov.br e notificações, não têm spec nesta implementação.

## Verificações executadas

- 45 testes automatizados passaram localmente em Python 3.14.7.
- Ruff: análise e formatação aprovadas em `src` e `tests`.
- Integração sintética: entrada CSV → tratamento → ROR → exportação → verificador
  original do desafio (`RESULTADO: OK`). A fixture inclui CID C*.
- Adaptador Gemini exercitado com o SDK instalado e transporte HTTP interceptado
  em teste, verificando JSON/schema. Nenhuma chamada real nem cota foi usada.
- API testada com autenticação, versões de fila, parecer persistido e aprovação
  médica auditável; testes cobrem negação consultiva, timeout, retorno inválido,
  ausência de comprovação, rechecagem das travas e recuperação após reinício.
- Pacote instalado sem modo editável e CLI do tratamento executada na base fornecida.
- Tratamento repetido em dois destinos: sete arquivos por execução; os seis arquivos
  substantivos foram idênticos byte a byte. Manifestos diferem no instante de execução.
  Hashes das entradas preservados e cobertura reconciliada para as 941 solicitações.

Duas advertências de depreciação vêm de dependências (Google GenAI em Python 3.14 e
integração Starlette/httpx); não são falhas dos testes. CI proposto usa Python 3.12.

## Dataset fornecido

| Medida | Resultado |
|---|---:|
| Solicitações originais | 941 |
| Eventos originais | 1.505 |
| Procedimentos | 23 |
| Ativas | 925 |
| Excluídas com evidência | 16 |
| Consolidadas automaticamente | 0 |
| Solicitações em grupos de possível duplicidade | 44 (22 grupos) |
| Eventos únicos | 1.499 |
| Eventos repetidos | 6 |
| Eventos órfãos | 9 |
| Imputações | 103 |

A consolidação conservadora não encontrou grupos que cumprissem todas as condições
positivas de equivalência. Os 22 grupos continuam explicitamente marcados para
revisão. Todas as 16 exclusões têm referências de evidência; precisam de revisão da
equipe antes de uso como entregável final. Os dados são sintéticos segundo o README.

## Bloqueio de modelagem encontrado

A configuração `examples/preferences-demo.json` é demonstrativa: faixas amplas,
escalas técnicas e dez comparações por dominância. Não se atribui à literatura
qualquer percentual ainda não sustentado e revisado.

Na base completa, ela produz uma precedência necessária contrária à regra de ouro.
Na execução final, o primeiro conflito reportado foi:

`Trava contradiz ordem necessaria: SOL-2026-00602 antes de SOL-2024-00056`.

Outro exemplo verificado explica o problema estrutural: SOL-2026-00683 tem CID C504,
90 dias de espera, ASA 1, dor 2, limitação leve e distância 7 km. SOL-2022-00020 tem
CID N40, 1.550 dias, ASA 2, dor 2, mesma limitação e distância 71 km. Mesmo a espera
relativa é ligeiramente maior no segundo (1550/360 > 90/21). Com pesos positivos e
funções monotônicas, os sete critérios não permitem justificar o primeiro acima do
segundo, embora a regra de ouro exija isso.

Não é uma falha de tempo limite do solver. É uma incompatibilidade entre a família
de modelos e as regras rígidas. Alterar percentuais positivos isoladamente não resolve
a dominância desse exemplo. O exportador bloqueou e não publicou uma fila parcial.
**Não foi gerado nem aprovado um CSV da base completa nesta parametrização.**

A equipe precisa decidir como a prioridade oncológica entra na relação de preferência
(por exemplo, precedência lexicográfica antes de aplicar ROR dentro dos grupos), e
atualizar a spec antes dessa mudança de comportamento. Os testes preservam a detecção
de conflitos e distinguem empate necessário de reversibilidade estrita.

## Aceitação ainda pendente

- Definir e revisar preferências reais de swing, fontes e comparações holísticas.
- Resolver o conflito entre ROR aditiva e regras de prioridade antes de exportar a base completa.
- Validar clinicamente as adaptações técnicas de SWALIS, comorbidades e deterioração.
- Configurar chave/modelo Gemini e realizar um caso real com revisão humana dos três textos.
- Executar o verificador oficial na fila completa aprovada após resolver a parametrização.

A implementação está em revisão. Aprovar este PR não equivale a validar clinicamente
os parâmetros ou as saídas do provedor.
