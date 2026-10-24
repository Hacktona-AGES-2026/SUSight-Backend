# Spec: Tratamento do dataset

Issue: Hacktona-AGES-2026/SUSight#5
Status: em revisão

## Contexto

A priorização precisa receber solicitações ativas e evidências consistentes, preservando a origem dos dados. O dataset sintético do desafio contém solicitações e eventos repetidos, campos ausentes, flags manuais conflitantes e informações relevantes em texto livre.

Esta feature prepara os dados para a pontuação da fila (spec 002, issue #6). Cada transformação deve ser verificável: o sistema conserva os registros originais, explica consolidações e exclusões e distingue informação observada, indício e valor imputado.

## Comportamento esperado

### Entrada e referência temporal

1. O sistema recebe `fila_cirurgica.csv`, `eventos_clinicos.csv` e `procedimentos.csv`, acompanhados do README e do dicionário do desafio. Registra a identificação e a versão dos arquivos usados, sem alterar os originais.
2. A data de referência do dataset é **2026-10-23**. O sistema não usa a data de execução para atualizar silenciosamente a espera ou os recortes de eventos. Datas de entrada e saída usam `AAAA-MM-DD`.
3. O sistema valida colunas obrigatórias, identificadores, datas, domínios e relações entre os arquivos. Arquivo ilegível, coluna estrutural obrigatória ausente ou identificador primário conflitante impedem a publicação de uma nova versão tratada, com indicação do problema. Ausência de medida clínica não é erro estrutural.
4. Problemas isolados, como medida fora do domínio, procedimento desconhecido ou data inválida, ficam registrados por solicitação. O registro não desaparece da cobertura; permanece pendente quando o problema impede seu uso na pontuação.

### Normalização sem perda do original

5. O sistema preserva os valores originais e produz valores normalizados para comparação:
   - CID em maiúsculas, sem ponto e sem espaços de formatação: `K40.9` e `K409` são equivalentes. Ausência ou formato inválido ficam sinalizados.
   - Prioridade manual em `alta`, `media` ou `baixa`; valores vazios continuam ausentes. Ela não é entrada da pontuação.
   - Campos categóricos com espaços, caixa e acentuação tratados conforme os domínios do dicionário, sem inventar equivalências clínicas.
   - Município com grafia padronizada para variantes inequívocas de caixa, espaços e acentuação; nomes ambíguos ficam para revisão.
   - Procedimento e especialidade associados pelo `procedimento_id` ao catálogo. Divergências com o texto redundante da fila ficam registradas.
6. Nome semelhante nunca basta para reunir pacientes. Os vínculos usam os identificadores fornecidos pelo dataset.
7. O sistema recalcula `dias_em_fila` pela diferença entre a referência e a data de entrada válida, registrando qualquer divergência com o valor recebido. Datas futuras não produzem espera negativa utilizável; geram pendência.

### Solicitações repetidas

8. Solicitações do mesmo paciente e procedimento são candidatas a consolidação. A consolidação automática exige CID normalizado equivalente e contexto compatível. Evidência de lateralidades, episódios ou indicações distintos, ou contradição que impeça confirmar a equivalência, mantém as solicitações separadas e sinalizadas para revisão. Mesmo paciente com procedimentos diferentes não é duplicata.
9. Em um grupo compatível, a solicitação canônica é a de entrada mais antiga; em empate, o menor `solicitacao_id` em ordem lexical. Sua data de entrada preserva o início da espera. O sistema guarda os identificadores originais como aliases e reúne as evidências sem substituir fatos conflitantes por uma escolha silenciosa.
10. Toda solicitação consolidada aponta para a canônica. Ela deixa de contar como item independente, mas continua rastreável no relatório de cobertura. Identificadores canônicos pertencem à fila original, permitindo a validação posterior do entregável.
11. Uma biópsia positiva ou outro indício relevante em uma duplicata permanece visível na solicitação canônica. Divergências clínicas entre duplicatas são explicitadas, sem fazer média de medidas nem transferir automaticamente um diagnóstico.

### Eventos e evidências

12. O sistema associa cada evento à sua solicitação e confere o `paciente_id`. Após consolidação, eventos dos aliases continuam ligados à canônica, com a origem preservada.
13. Eventos equivalentes em todos os campos de conteúdo, diferindo apenas no `evento_id`, contam como uma ocorrência, com todos os identificadores de origem guardados. Eventos com data, resultado ou conteúdo diferente permanecem distintos.
14. Evento com solicitação ausente da fila fica separado como órfão. Divergência entre paciente do evento e da solicitação gera pendência e impede sua incorporação automática. O sistema não transfere eventos só porque o paciente tem outra solicitação ativa.
15. Eventos anteriores à entrada na fila são preservados como histórico, pois podem documentar a indicação cirúrgica. Não contam como deterioração durante a espera. Eventos posteriores à referência ficam sinalizados e fora dos indicadores dessa versão.
16. O sistema preserva tipo, resultado, data e origem dos eventos e distingue evidência clínica documentada de relato. Organiza PS, internações, progressão em imagem, reavaliações e contatos para que a pontuação possa aplicar suas regras e janelas temporais.

### Flags e texto livre

17. O indicador derivado `oncologico_por_cid` usa exclusivamente o CID principal normalizado iniciado por `C`. A flag manual é preservada para comparação; CID ausente ou inválido produz estado desconhecido, e não `nao`.
18. Biópsia positiva em solicitação com CID não `C*` gera sinal de divergência para revisão e mantém sua evidência. O tratamento não troca o CID nem infere um diagnóstico novo.
19. O sistema extrai indícios do texto livre por regras determinísticas, guardando campo ou evento de origem, trecho encontrado e regra aplicada. Trata negação e incerteza explicitamente; expressão ambígua não se torna fato confirmado. Os textos originais permanecem disponíveis para revisão.
20. Comorbidades estruturadas e menções textuais são organizadas com suas fontes e sem contagem repetida de sinônimos conhecidos. Quantidade, gravidade e contribuição para a pontuação são definidas na spec 002. Não se diagnostica diabetes a partir de HbA1c nem se preenche uma comorbidade só pela ausência de informação.
21. As flags manuais de diabetes e piora são mantidas ao lado das evidências concordantes ou discordantes. Relato de piora continua identificado como relato e não substitui exame. Não haver evento não prova ausência de piora.
22. O sistema disponibiliza os sinais necessários à regra de ouro e à identificação conservadora de casos sem urgência clínica do verificador oficial. Valores ausentes, imputação e conflitos permanecem identificáveis; imputação não comprova ausência de urgência.

### Fila ativa e exclusões

23. Uma solicitação sai da fila ativa quando há registro explícito, aplicável àquela solicitação e sem contradição, de desistência ou cirurgia já realizada em outro serviço. O registro pode estar em evento ou texto livre, sempre com a evidência preservada. Intenção de operar, frase negada ou menção incerta não confirma cirurgia realizada.
24. Registros contraditórios, inclusive indício posterior de retomada da solicitação, geram revisão e mantêm o caso ativo sinalizado. Uma anotação de saída não encerra automaticamente outros procedimentos do paciente.
25. Falta a consulta, contato sem resposta, cadastro incompleto e preparo pré-operatório pendente não excluem automaticamente uma solicitação.
26. O sistema registra, para cada solicitação original, um estado explicável: ativa, consolidada, excluída ou pendente por impedimento de uso. Um caso ativo pode ter aviso de revisão; avisos não equivalem a exclusão. A saída discrimina casos ativos utilizáveis e casos pendentes, sem apresentar uma fila parcial como cobertura completa.

### Valores ausentes e interface com a pontuação

27. O sistema mantém as medidas observadas separadas dos valores preparados para a pontuação. Dor, ASA, limitação e distância ausentes ou inválidos recebem, na representação para pontuação, a mediana dos valores observados válidos da mesma especialidade, conforme a spec 002. As regras de representação de medianas em escalas ordinais devem preservar o domínio e ser documentadas no plano.
28. A população de referência da mediana considera apenas solicitações canônicas ativas, sem usar valores já imputados. Registra critério, especialidade, valor aplicado e população de referência. Se a especialidade não possui valores válidos, o caso fica pendente para revisão, sem inventar um valor substituto.
29. Texto vazio, CID ausente e ausência de eventos não recebem mediana. A imputação de medidas não muda o diagnóstico, os fatos usados em exclusões nem a classificação oncológica pelo CID.
30. A saída disponibiliza as medidas, evidências, ausências, imputações e conflitos necessários aos sete critérios da spec 002. A estimativa da classe SWALIS, a razão espera/prazo, a escala de deterioração, os pesos e a ROR pertencem à pontuação; esta feature não os decide.

### Saída e auditoria

31. A equipe recebe os dados tratados, os vínculos entre registros originais e canônicos, os eventos preservados e um relatório de qualidade e cobertura. O relatório informa quantidades de entrada e saída, consolidações, exclusões, órfãos, imputações e pendências.
32. As regras aplicadas e os motivos das exclusões ficam registrados em `DECISOES.md`, acompanhados dos identificadores e referências das evidências necessárias para auditar cada decisão. Categorias de cobertura são reconciliáveis com todas as solicitações originais.
33. A mesma entrada, data de referência e versão de regras produzem os mesmos registros tratados e decisões. Horário de execução pode variar nos metadados sem alterar o resultado substantivo.

## Critérios de aceite

- [ ] Os arquivos brutos permanecem inalterados, e a versão da entrada e das regras é identificável.
- [ ] A referência é `2026-10-23`; executar em outra data não altera os dias de espera.
- [ ] `K40.9` e `K409` normalizam para o mesmo CID; CID inválido é sinalizado, sem diagnóstico inferido.
- [ ] Toda solicitação original possui estado e motivo; a cobertura reconcilia entrada, ativas, consolidadas, excluídas e pendentes.
- [ ] Duplicatas compatíveis preservam a solicitação mais antiga e os eventos de todos os aliases; contextos conflitantes permanecem separados para revisão.
- [ ] Procedimentos diferentes do mesmo paciente não são consolidados.
- [ ] Eventos repetidos contam uma vez e preservam todos os IDs; órfãos e conflitos de paciente são reportados.
- [ ] Evento anterior à entrada é mantido como histórico e não contado como piora durante a espera; evento futuro não alimenta indicadores.
- [ ] CID `C*` define o indicador oncológico independentemente da flag; biópsia positiva com CID não `C*` gera divergência rastreável.
- [ ] Cada indício extraído de texto possui fonte, trecho e regra; negação e incerteza não viram confirmação.
- [ ] Desistência ou cirurgia realizada explícitas e sem contradição justificam exclusão; casos ambíguos continuam ativos para revisão.
- [ ] Falta, contato sem resposta e preparo pendente não causam exclusão automática.
- [ ] Imputações usam apenas valores observados válidos da especialidade entre canônicas ativas, são marcadas e não apagam a ausência original.
- [ ] Especialidade sem valores observados válidos gera pendência explicada para o critério, sem imputação arbitrária.
- [ ] A saída mantém dados e fontes necessários aos sete critérios da pontuação, sem atribuir pesos ou estimar diagnóstico.
- [ ] Erro estrutural impede publicar uma versão tratada incompleta como válida e identifica a causa.
- [ ] Mesmas entradas e regras geram os mesmos resultados substantivos.

## Fora do escopo

- Swing weighting, ROR, definição de escalas clínicas, pesos e estimativa da classe SWALIS (issue #6).
- Tribunal de IAs, extração com LLM ou análise de exames enviados pelo app.
- Alteração de CID, diagnóstico novo ou validação clínica automática de indícios.
- Exportação da fila ordenada em `fila_priorizada.csv`: é etapa posterior à pontuação. O tratamento prepara seus IDs e justificativas de cobertura.
- Decidir aptidão cirúrgica por HbA1c ou preparo pré-operatório; os campos são preservados como informação opcional.
- Aplicação de mudanças na fila operacional ou decisão médica de priorização.

## Questões em aberto

Nenhuma decisão de comportamento pendente. O plano deve detalhar os formatos de saída, as regras versionadas de compatibilidade e extração textual e a representação das medianas ordinais, de acordo com os comportamentos acima.
