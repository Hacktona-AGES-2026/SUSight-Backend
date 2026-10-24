# Spec: Extração de dados de exames e laudos

Issue: [Hacktona-AGES-2026/SUSight#7 — [Backend] [IA] Pipeline de análise de exame e laudo](https://github.com/Hacktona-AGES-2026/SUSight/issues/7)
Status: em revisão

Recomendações de escopo do MVP adotadas por solicitação do usuário em 2026-10-24. A implementação e a aceitação permanecem sujeitas à revisão prevista no SDD.

## Contexto

Pacientes e médicos enviam exames e laudos em PDF ou imagem para documentar a situação do paciente enquanto ele aguarda cirurgia eletiva. Esses documentos possuem estruturas, títulos, tabelas e formas de escrita diferentes. A equipe precisa transformar as informações presentes em dados estruturados e verificáveis, sem exigir um modelo único de documento.

A extração alimenta uma proposta para a pontuação da fila. Ela não calcula prioridade, não produz diagnóstico e não altera a fila. Cada valor precisa ser sustentado pelo documento, com sua confiança de extração identificada e as dúvidas encaminhadas ao médico.

Os documentos contêm dados de saúde. A coleta deve se limitar ao necessário para a finalidade, e nome e CNS devem ser mascarados antes de qualquer envio a serviço externo, inclusive para leitura do documento.

O MVP é demonstrado e testado com documentos inteiramente sintéticos, sem dados de pacientes reais. Essa condição vale também para os envios a serviços externos e não é substituída pelo simples mascaramento de identificadores.

Embora a issue também mencione tempo de espera e deterioração, nesta feature esses dados são obtidos da fila e de seu histórico, e não extraídos do documento.

## Comportamento esperado

1. O paciente ou o médico envia um único documento digitado por envio, em PDF, JPEG ou PNG, vinculado à solicitação cirúrgica correspondente. PDFs podem conter texto selecionável ou páginas digitalizadas. O limite é de 10 MiB por arquivo e 10 páginas por PDF; cada imagem corresponde a uma página. O sistema registra a origem do envio e a referência do documento, coletando apenas os dados necessários para associar e revisar a extração.
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

### Decisões recomendadas para o MVP

- **Leitura e manuscritos:** a leitura inicial e o mascaramento ocorrem no ambiente do projeto. Conteúdo manuscrito não é extraído automaticamente: gera aviso para revisão ou reenvio digitado. Em documento misto, os campos dependentes do manuscrito retornam `null` com revisão; partes digitadas legíveis podem produzir propostas. A ferramenta de leitura será especificada no plano, sem dependência de layout fixo.
- **Serviço externo:** pode ser utilizado para a demonstração com conteúdo exclusivamente sintético, minimizado e mascarado, após conferência dos termos aplicáveis pelo responsável de Backend. Nome comercial, modelo e ferramenta de leitura pertencem ao plano. Ausência de serviço disponível mantém a extração pendente, com aviso; não gera resposta simulada apresentada como leitura real. Não há autorização de uso clínico real nesta spec.
- **Entradas e limites:** aceitar PDF, JPEG e PNG que correspondam efetivamente ao formato declarado; rejeitar arquivo vazio, corrompido, protegido por senha, acima de 10 MiB ou com mais de 10 páginas. Solicitar novo envio em formato aceito para HEIC, arquivos de escritório e outros formatos. Não aceitar pacote de vários arquivos ou mistura de documentos independentes no mesmo envio; orientar a separação dos documentos.
- **Confiança:** usar `alta`, `media` e `baixa` como categorias de qualidade da extração, sem porcentagens ou interpretação probabilística. `alta` exige texto legível, evidência direta e ausência de conflito. `media` admite proposta sustentada por evidência, mas com dificuldade de leitura ou associação que demande revisão. `baixa` indica suporte insuficiente: o valor final fica `null` e exige revisão. Campo ausente tem confiança `null` e situação `ausente`, sem evidência inventada. Ambiguidade, manuscrito, ilegibilidade e contradição exigem revisão independentemente da confiança declarada. Todas as propostas precisam de aprovação profissional antes de uso como dados aprovados, inclusive as de confiança alta.
- **Representação comum:** manter, por campo, valor proposto, situação, confiança, necessidade de revisão e evidências. Situações: `presente`, `ausente`, `incerto`, `ilegivel` ou `conflitante`. Evidências preservam trecho, página e localização. A ausência não é confundida com negação explícita ou lista vazia confirmada.
- **Limitação funcional:** admitir `nenhuma`, `leve`, `moderada` e `grave` somente se essa classificação estiver explicitamente registrada. Descrição livre sem categoria não é convertida automaticamente: conservar o trecho e encaminhar a categorização ao médico, com valor normalizado `null`.
- **ASA:** aceitar classes I a VI quando explicitamente registradas, preservando a notação de origem e eventual indicação de emergência. Classes fora do domínio atualmente usado pela pontuação são encaminhadas à revisão de compatibilidade; não são reduzidas nem descartadas silenciosamente. Documento sem ASA retorna `null`.
- **Dor:** representar intensidade, escala e descrição conforme registradas. EVA 0–10 só é identificada como tal quando a escala estiver explícita; não converter outras escalas nem atribuir intensidade numérica a expressões como "dor forte". O médico pode revisar a informação antes de sua compatibilização com a pontuação.
- **Questões socioeconômicas:** usar lista de fatos explicitamente registrados sobre deslocamento ou acesso ao atendimento. Distância só é numérica quando declarada com unidade. Não deduzir renda, vulnerabilidade ou distância a partir do município; não coletar endereço completo ou renda detalhada nesta extração. Fatos sem correspondência no critério atual de pontuação permanecem informativos para revisão.
- **Comorbidades:** usar lista de condições afirmadas no documento, cada uma com sua evidência e confiança. Guardar negações, hipóteses e antecedentes familiares como observações distintas, sem incluí-los como comorbidades confirmadas. Não criar código de diagnóstico nem condição a partir de resultado laboratorial isolado.
- **Tipo e data:** tipos possíveis são exame laboratorial, exame de imagem, laudo, avaliação pré-anestésica e outro tipo explicitamente identificado; se não houver suporte, retornar `null`. Normalizar data completa e inequívoca para `AAAA-MM-DD`, preservando o trecho original. Data incompleta ou ambígua retorna `null` para o valor normalizado e exige revisão; não inferir ano nem substituir pela data do envio.
- **Conjunto de teste:** preparar 40 documentos sintéticos com gabarito de valores, trechos e revisão esperada: 20 legíveis, organizados em dez pares com informações equivalentes e layouts diferentes; dez com ausências, negações, conflitos, manuscritos ou problemas de legibilidade; e dez casos de entrada inválida, formato não aceito ou limite excedido. O responsável de Backend mantém o conjunto e uma segunda pessoa da equipe confere o gabarito contra o texto. A aceitação exige todos os valores não nulos sustentados, todos os campos ausentes como `null` e todos os casos obrigatórios de revisão sinalizados; não se aceita uma média de acurácia que esconda valores inventados. Validação clínica é uma etapa separada de qualquer uso real.
- **Acesso e guarda:** o paciente acessa apenas seus próprios documentos e os profissionais autorizados apenas os casos necessários ao trabalho. No ambiente de demonstração, arquivos enviados e seus derivados, evidências e decisões são eliminados em até sete dias do envio, ou antes por solicitação do responsável. Não registrar conteúdo de documento, nome, CNS ou credenciais em registros operacionais compartilhados. A política do conjunto sintético de teste versionado é distinta e não envolve dados reais. Esse prazo é uma escolha do MVP sintético, não uma política de guarda de prontuários reais.
- **Comprovação do mascaramento:** antes de cada envio externo, conferir todas as páginas e todo o texto que serão enviados; nenhum nome, CNS ou outro identificador direto desnecessário pode permanecer visível. Testes incluem identificadores repetidos em cabeçalho, rodapé e corpo e verificam o conteúdo efetivamente encaminhado. Qualquer falha impede o envio. Não encaminhar documento real a serviço externo apenas por ter passado por esse controle.

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
- [ ] JPEG, PNG e PDF digitados ou digitalizados, de até 10 MiB e dez páginas, são aceitos; arquivo vazio, protegido, incompatível ou acima dos limites é rejeitado com orientação compreensível. Mais de um documento independente no envio exige separação.
- [ ] Conteúdo manuscrito gera aviso para revisão ou reenvio; nenhum campo dependente dele é preenchido automaticamente.
- [ ] Confiança usa somente `alta`, `media`, `baixa` ou `null` para ausente. Confiança baixa retorna valor `null` e revisão; confiança alta não dispensa aprovação profissional.
- [ ] Nenhuma descrição livre de limitação, escala de dor ou classe ASA incompatível é convertida silenciosamente para o domínio da pontuação.
- [ ] O conjunto sintético de 40 documentos contempla os casos e os gabaritos definidos; os requisitos de evidência, ausência e revisão são conferidos individualmente.
- [ ] Testes do conteúdo efetivamente enviado externamente confirmam ausência dos identificadores sintéticos originais em todas as ocorrências e nenhuma saída externa em caso de falha de mascaramento.
- [ ] O teste de autorização impede acesso a documento de outro paciente ou fora da permissão profissional; arquivos e derivados da demonstração expiram juntos em até sete dias do envio.

## Fora do escopo

- Cálculo de pontuação, definição de pesos, ordenação ou reposicionamento da fila.
- Cálculo de tempo de espera e deterioração durante a espera, obtidos da fila e de seu histórico.
- Tribunal de IAs, debate de propostas e resolução automática de conflitos clínicos.
- Telas, componentes visuais e implementação das interfaces de upload e revisão.
- Diagnóstico, prescrição, classificação ASA inferida ou validação clínica autônoma do conteúdo.
- Preenchimento por valores padrão, imputação de campos ausentes ou conversão não aprovada de escalas clínicas.
- Decisão de tecnologia de leitura, provedor de IA ou integração com serviço externo.
- Extração automática de manuscritos, conversão de HEIC e processamento de múltiplos documentos independentes no mesmo envio.
- Uso com pacientes ou documentos reais e definição de política de guarda de prontuários reais.

## Questões em aberto

Nenhuma decisão de escopo do MVP pendente. As oito questões foram substituídas pelas recomendações explícitas acima. Ferramentas de leitura, modelo e provedor permanecem decisões do futuro plano, conforme o escopo desta entrega; nenhum deles foi escolhido nesta spec.

A preparação do conjunto de teste, a conferência dos termos de eventual serviço externo e a verificação de acesso, mascaramento e expiração continuam sendo condições de aceitação a executar. A definição de um padrão recomendado não comprova que esses controles já estejam implementados ou testados.

## Referências de compatibilidade

- [Declaração da ASA sobre a classificação de estado físico](https://doi.org/10.1097/ao9.0000000000000002): referência para preservar a notação que conste no documento, sem transformar essa classificação em prioridade cirúrgica ou inferi-la automaticamente.
- [Termos adicionais da API Gemini](https://ai.google.dev/gemini-api/terms): exemplo de termos que precisam ser conferidos antes de selecionar um fornecedor. A oferta gratuita não autoriza envio de informações sensíveis; os termos também restringem uso clínico. A referência não escolhe o provedor desta feature nem autoriza uso com pacientes reais.
