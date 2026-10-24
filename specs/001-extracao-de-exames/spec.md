# Spec: Extração de dados de exames e laudos

Issue: [Hacktona-AGES-2026/SUSight#7 — [Backend] [IA] Pipeline de análise de exame e laudo](https://github.com/Hacktona-AGES-2026/SUSight/issues/7)
Status: rascunho

## Contexto

Pacientes e médicos enviam exames e laudos em PDF ou imagem para documentar a situação do paciente enquanto ele aguarda cirurgia eletiva. Esses documentos possuem estruturas, títulos, tabelas e formas de escrita diferentes. A equipe precisa transformar as informações presentes em dados estruturados e verificáveis, sem exigir um modelo único de documento.

A extração alimenta uma proposta para a pontuação da fila. Ela não calcula prioridade, não produz diagnóstico e não altera a fila. Cada valor precisa ser sustentado pelo documento, com sua confiança de extração identificada e as dúvidas encaminhadas ao médico.

Os documentos contêm dados de saúde. A coleta deve se limitar ao necessário para a finalidade, e nome e CNS devem ser mascarados antes de qualquer envio a serviço externo, inclusive para leitura do documento.

Embora a issue também mencione tempo de espera e deterioração, nesta feature esses dados são obtidos da fila e de seu histórico, e não extraídos do documento.

## Comportamento esperado

1. O paciente ou o médico envia um exame ou laudo em PDF ou imagem, vinculado à solicitação cirúrgica correspondente. O sistema registra a origem do envio e a referência do documento, coletando apenas os dados necessários para associar e revisar a extração.
2. O sistema verifica se o arquivo pode ser lido. Documento corrompido, protegido de modo que impeça a leitura ou incompatível com os formatos aceitos gera aviso compreensível, sem apresentar uma extração inexistente como concluída.
3. Para uma imagem desfocada, cortada, escura ou de outra forma insuficiente para a leitura, o sistema avisa que a qualidade prejudica a extração e solicita reenvio legível. Informações ilegíveis não são preenchidas por suposição. Se apenas parte do documento for legível, o resultado identifica a limitação e os campos afetados para revisão.
4. Antes de enviar qualquer conteúdo a serviço externo, o sistema mascara nome e CNS no próprio conteúdo que será enviado, incluindo páginas, imagens e trechos de texto. Os identificadores não podem continuar legíveis em outra parte desse conteúdo. Se não for possível assegurar o mascaramento, o documento não é enviado externamente e a limitação fica indicada para revisão.
5. O sistema procura as informações pelo conteúdo do documento, independentemente da posição dos campos ou do layout. Documentos com os mesmos dados em estruturas diferentes produzem o mesmo esquema de campos.
6. O resultado sempre apresenta os sete campos abaixo, mesmo quando algum deles estiver ausente:

   | Campo | Informação procurada |
   |---|---|
   | Limitação funcional | Limitação ou impacto funcional explicitamente descrito no documento. |
   | ASA | Classificação ASA registrada no documento. Não inferir a classificação a partir de doenças, idade ou outros resultados. |
   | Dor | Intensidade, escala e descrição de dor que constem no documento, preservando a escala informada quando houver. |
   | Questões socioeconômicas | Informações explicitamente registradas e necessárias à análise, como dificuldade de deslocamento ou de acesso ao atendimento. |
   | Comorbidades | Condições expressamente registradas, distinguindo afirmação de negação, suspeita ou antecedente familiar. |
   | Tipo de documento | Tipo identificado no próprio conteúdo, quando houver informação suficiente para reconhecê-lo. |
   | Data do documento | Data de emissão ou realização explicitamente identificada como pertencente ao documento. Não substituir pela data do envio. |

7. Cada campo apresenta seu valor proposto, a situação da leitura, o nível de confiança da extração e as evidências correspondentes. Para cada valor não nulo, a evidência contém o trecho que o sustenta e uma referência que permita encontrá-lo no documento, como a página e a região correspondente. Se um campo contiver vários valores, cada um tem sua própria evidência e confiança.
8. Campo não encontrado retorna `null`, identificado como ausente, sem valor padrão, imputação ou evidência inventada. Não mencionar uma comorbidade não equivale a afirmar que ela não existe. A ausência de ASA não autoriza estimá-lo.
9. Quando o conteúdo for incerto, ilegível, negado, hipotético ou contraditório, o sistema explicita a situação e marca o campo para revisão do médico. Uma leitura que não permita sustentar o valor retorna `null`; o resultado conserva os trechos legíveis relevantes e a localização da dúvida, quando disponíveis, sem completar palavras ou números por suposição. Conteúdo claramente negado não é apresentado como condição presente.
10. O nível de confiança descreve a confiabilidade da leitura e da associação entre valor e evidência. Ele não representa certeza clínica, probabilidade de doença nem autorização para alterar a fila. A confiança não substitui a marcação de revisão diante de ambiguidade ou contradição.
11. Se houver datas ou valores conflitantes, o sistema mantém as evidências de cada alternativa e a pendência de revisão, sem escolher silenciosamente uma delas. A data de outro evento citado no texto não é tomada como data do documento sem sustentação explícita.
12. Tempo de espera e deterioração durante a espera não integram os campos extraídos. Se o documento mencionar tempo ou piora, a extração não substitui nem recalcula os valores correspondentes da fila e de seu histórico.
13. O sistema disponibiliza os dados estruturados como proposta, com as evidências, as ausências, os avisos de qualidade e os campos que precisam de revisão. Nenhum valor extraído é incorporado como dado aprovado nem altera a fila automaticamente.
14. O profissional responsável pode conferir as evidências, corrigir ou rejeitar os valores e aprovar os dados propostos. A decisão registra o responsável, a data e a hora, preservando a distinção entre o valor extraído e eventual correção profissional. A aprovação dos dados não implica aplicação automática de uma mudança na fila.
15. O sistema mantém o acesso aos documentos e às evidências restrito a quem precisa revisá-los. Nome e CNS não reaparecem nos trechos enviados externamente ou em registros compartilhados da extração. Avisos e resultados usam português do Brasil, com linguagem simples e sem alarme.

## Critérios de aceite

- [ ] Um PDF e uma imagem legíveis, enviados pelo paciente ou pelo médico, podem ser associados à solicitação e gerar uma proposta de extração.
- [ ] Dois documentos de layouts distintos que expressem as mesmas informações preenchem o mesmo esquema de sete campos, sem exigir posição fixa dos conteúdos.
- [ ] O resultado sempre contém limitação funcional, ASA, dor, questões socioeconômicas, comorbidades, tipo e data do documento, inclusive quando seus valores forem `null`.
- [ ] Um campo ausente retorna `null`, com indicação de ausência, sem receber zero, mediana, classificação presumida ou outro valor inventado.
- [ ] Todo valor não nulo, inclusive tipo e data do documento, tem trecho de evidência localizável e nível de confiança; listas de valores preservam essas informações por item.
- [ ] Um ASA não registrado não é inferido a partir de comorbidades ou outros resultados, e a ausência de menção a comorbidades não gera afirmação de que o paciente não as possui.
- [ ] Uma intensidade de dor registrada em escala diferente preserva a escala de origem, sem conversão silenciosa para outra escala.
- [ ] Informação negada ou hipotética não é apresentada como condição confirmada. Valor que não possa ser sustentado retorna `null` e é marcado para revisão.
- [ ] Campo ilegível, leitura incerta ou informação contraditória gera marcação de revisão médica e mantém as evidências legíveis disponíveis, sem escolha silenciosa de uma alternativa.
- [ ] Uma imagem de má qualidade gera aviso de qualidade e solicitação de reenvio; trechos ilegíveis não recebem valores supostos.
- [ ] Quando há várias datas, a extração não usa a data do envio nem outra data citada sem evidência de que seja a data do documento; ambiguidade gera revisão.
- [ ] Menções a espera ou piora no documento não preenchem nem sobrescrevem tempo de espera ou deterioração calculados a partir da fila e de seu histórico.
- [ ] A inspeção de todo conteúdo encaminhado a um serviço externo confirma que nome e CNS estão mascarados, inclusive nas páginas, imagens e evidências. Se o mascaramento não puder ser assegurado, nenhum conteúdo é enviado externamente.
- [ ] A proposta distingue valor extraído, confiança, evidência, aviso e revisão pendente, sem apresentar confiança como certeza clínica.
- [ ] Concluir a extração, mesmo com confiança elevada, não modifica os dados aprovados nem a posição na fila. Uma mudança de fila continua dependendo de aprovação profissional específica.
- [ ] A revisão registra responsável, data e hora e distingue uma correção profissional do valor originalmente proposto pela extração.
- [ ] Acesso aos documentos e evidências é restrito aos envolvidos autorizados; resultados e avisos são apresentados em português do Brasil, sem diagnóstico e sem linguagem alarmante.
- [ ] Um arquivo que não possa ser lido gera aviso explícito, sem retornar campos preenchidos como se a extração tivesse sido realizada.

## Fora do escopo

- Cálculo de pontuação, definição de pesos, ordenação ou reposicionamento da fila.
- Cálculo de tempo de espera e deterioração durante a espera, obtidos da fila e de seu histórico.
- Tribunal de IAs, debate de propostas e resolução automática de conflitos clínicos.
- Telas, componentes visuais e implementação das interfaces de upload e revisão.
- Diagnóstico, prescrição, classificação ASA inferida ou validação clínica autônoma do conteúdo.
- Preenchimento por valores padrão, imputação de campos ausentes ou conversão não aprovada de escalas clínicas.
- Decisão de tecnologia de leitura, provedor de IA ou integração com serviço externo.

## Questões em aberto

- **Tecnologia de leitura:** qual abordagem permite ler PDFs com texto, documentos digitalizados e imagens de layouts variados, inclusive quando parte do conteúdo for manuscrita?
- **Serviço de IA permitido:** quais serviços podem receber os dados minimizados e mascarados, sob quais condições de tratamento, acesso, retenção e uso, ou a leitura precisa ocorrer integralmente no ambiente do projeto?
- **Formato de entrada:** quais variantes de PDF e extensões de imagem serão aceitas? Como serão tratados arquivos protegidos, várias páginas, vários documentos no mesmo envio e conteúdo manuscrito?
- **Limites:** qual o tamanho máximo por arquivo, o número máximo de páginas e a quantidade de arquivos por envio?
- **Documentos de teste:** qual conjunto sintético ou devidamente desidentificado representará os layouts, tipos de documento, imagens de má qualidade, ausências, negações e contradições? Quem validará os valores e trechos esperados?
- **Confiança e revisão:** qual escala de confiança será adotada e quais condições adicionais exigirão revisão? Como verificar a confiança contra o conjunto de documentos de teste, sem tratá-la como certeza clínica?
- **Representação dos campos:** quais categorias, unidades e listas compõem o esquema final de limitação funcional, dor, questões socioeconômicas, comorbidades e tipo de documento? Quais normalizações de valores explicitamente presentes serão permitidas sem inferência clínica?
- **Privacidade e guarda:** qual política define o acesso e o prazo de retenção dos documentos, evidências e resultados? Como comprovar o mascaramento antes de qualquer processamento externo, inclusive da leitura inicial?
