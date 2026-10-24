# Decisões do SUSight (Desafio 1 · Priorização Inteligente da Fila Cirúrgica)

Backend do SUSight. Toda a demonstração usa o dataset sintético do desafio (data de referência 23/10/2026). A parametrização do modelo é **demonstrativa e não tem validação clínica**; a justificativa de cada linha do CSV diz isso.

## Qual abordagem

**A IA só propõe; o médico decide.** Em vez de fixar um peso por critério (escolha arbitrária difícil de defender), o backend combina quatro ideias:

1. **Hierarquia rígida antes de qualquer peso.** Quem tem câncer (CID `C*`) ou não é classificado como sem urgência vem antes de quem não tem urgência clínica. Dentro desse grupo, a classe **SWALIS** (A1, A2, B, C, D) ordena em camadas. A regra de ouro do desafio é uma precedência, não uma competição entre pesos: nenhum oncológico pode ficar abaixo de um paciente sem urgência, qualquer que seja o peso.
2. **Swing weighting + ROR (Robust Ordinal Regression).** Dentro de cada classe, a importância dos seis critérios (limitação funcional, ASA, dor, comorbidades, deterioração e distância) vem de faixas de peso, não de números exatos. A ROR considera **todas** as ponderações compatíveis e separa a ordem **necessária** (vale em todas) da **incerta** (depende dos pesos). Na demonstração, a curva de cada critério é linear, a ordem dos pesos segue a dos swings e as faixas são de ±10%.
3. **Tribunal de IAs só nos casos incertos.** Quatro papéis analisam uma proposta de mudança: um agente defende **subir** o paciente (evidências), outro defende **descer ou manter** (contestação), um terceiro é **imparcial** (equidade) e o **juiz** lê os três votos e dá o parecer final. O médico recebe o debate inteiro junto com a proposta. O tribunal é consultivo, nunca altera a fila sozinho, e nunca responde com texto simulado: sem provedor configurado ele registra indisponibilidade. Se o médico **rejeita**, o motivo volta ao tribunal, que analisa de novo (até 3 rodadas).
4. **Reavaliação a cada documento.** Quando o paciente envia um exame ou laudo, o sistema o lê (OCR com Gemini) e extrai os critérios com a frase do documento como evidência: CID, deterioração durante a espera, porte, limitação funcional, ASA, dor e comorbidades. Com eles, recalcula a pontuação **só desse paciente**, com a mesma função de valor que ordenou a fila, e o encaixa pela hierarquia (classe antes de pontuação). Se a posição melhora, a proposta é criada sozinha e o tribunal a analisa. O **médico aprova apenas o resultado final**, não cada evidência: as evidências lidas pelo sistema aparecem marcadas como tal, e os critérios novos só passam a valer para o paciente depois dessa aprovação. O médico também pode rejeitar com motivo ou pedir informações (exames). Toda decisão fica registrada com nome, data e hora e entra no histórico.

## Para quem

O **regulador / médico revisor** é o usuário principal. A fila é **uma só e todos os médicos a veem inteira**: não existe lista por médico. Ele recebe a lista de propostas, vê as evidências, o parecer do tribunal e o histórico, e decide. O **paciente** acompanha a própria posição, o histórico e os exames pedidos, e envia exames pelo app; ele não relata sintomas, porque relato não substitui exame. O paciente só enxerga o próprio caso.

## Por que essa escolha

- A prioridade manual da regulação é ruidosa e raramente revisada (o próprio desafio avisa). Aqui ela só aparece na justificativa; **não entra na ordenação**.
- Explicabilidade: cada linha do CSV diz os critérios que mais pesaram, se a posição é necessária ou incerta e qual trava foi aplicada.
- Segurança: a regra de ouro vale em qualquer parametrização, e nenhuma mudança de fila acontece sem decisão de um profissional.

## Exemplo concreto: quem mudou de posição e por quê

**`SOL-2026-00719`** · neoplasia maligna da pele (C44.3) · prioridade manual **Baixa** · 82 dias na fila · dor 1, limitação leve, ASA 3, deterioração documentada 3. Observação do registro: relato de piora importante, perda de peso e dor.

- **Antes**, pela ordem de referência (prioridade manual e depois mais dias em fila, uma aproximação da fila de hoje): posição **905** de 925.
- **Agora**: posição **44**. Motivos: o CID oncológico entra no grupo protegido, a classe SWALIS é **A1**, e dentro da classe pesam ASA, limitação e a deterioração documentada.
- Entre os 34 oncológicos com prioridade manual Baixa, a mediana foi de **785 para 86,5**. Entre todos os 177 oncológicos, de **283 para 143**.

## O que o modelo **não** usa, de propósito

- **Tempo de espera e data de entrada**: nem como peso, nem como desempate, nem em travas. Quem espera mais não ganha preferência por isso; o desempate final é pelo identificador da solicitação. A espera fica só como informação administrativa. Foi uma decisão do usuário, e há teste de invariância.
- **Prioridade manual da regulação** e as flags do dataset (`flag_oncologico` etc.), que o desafio descreve como defeituosas: o oncológico é definido pelo **CID**, não pela flag.
- **Idade** como critério isolado, **preparo pré-operatório** e agenda (fora do escopo do desafio).
- **Diagnóstico ou conclusão clínica pela IA**: o sistema não diagnostica nem substitui urgência (orienta UPA ou SAMU 192).
- **Nas telas**, de propósito: login por gov.br e envio de código por SMS (entra-se com CPF e código de acesso), Face ID, câmera e biblioteca de fotos no envio (só arquivo PDF, JPG ou PNG), e o status "em análise" dos exames (só pendente ou recebido).

## Tratamento dos defeitos dos dados

Entrada: 941 solicitações, 1.505 eventos e 23 procedimentos. O tratamento mantém os arquivos originais intactos e registra cada decisão.

- **16 solicitações excluídas** da fila (desistência ou cirurgia em outro serviço, por texto de observação), todas listadas com o motivo no `DECISOES.md` gerado pela pipeline. **Nenhuma tem CID oncológico.** Duas delas têm só texto de familiar ("operou pelo convênio") e três dizem "não deseja mais operar no momento, melhorou com remédio": **pedem confirmação de quem conhece a regulação** antes de uso real.
- **Duplicatas:** 44 candidatas ficam ativas e marcadas para revisão, porque a equivalência positiva não foi comprovada. Eventos duplicados exatos (6) são unificados; 9 eventos órfãos ficam separados.
- **Flags que não batem**: 44 de oncológico, 30 de diabético e 76 de piora clínica divergem do diagnóstico ou dos eventos; o CID e os eventos prevalecem.
- **Valores ausentes ou inválidos** (ASA 26, dor 38, limitação 20, distância 20) recebem a mediana da especialidade, ficam marcados como "dado incompleto" (103 imputações) e nunca provam ausência de urgência.
- **Biópsia positiva com CID divergente** (23): gera revisão clínica; o sistema não reescreve o diagnóstico.

## Exemplo da demonstração ao vivo

**Pedro Freitas Medeiros** (`PAC-00152`, `SOL-2023-00002`) · hérnia inguinal (K40.9) · posição **794** de 925, classe D. No dataset ele tem dor 0 e limitação leve. O laudo fictício `docs/demo/laudo-pedro-freitas-medeiros.pdf` descreve piora: dor 8, limitação grave, dois encarceramentos, deterioração moderada, porte médio, ASA III, hipertensão e diabetes.

Enviado pelo app, o laudo foi lido pelo Gemini em cerca de 4 s; a pontuação recalculada passou a classe D para **B** e a posição ideal para cerca de 246. A trava de **10% por reavaliação** limitou a proposta, e o juiz votou "ajustar": o médico recebeu a proposta **774** (de 794) com os quatro votos e as evidências. Em cerca de 13 s o documento virou proposta pronta. Nada muda na fila antes da aprovação.

## Resultado

`fila_priorizada.csv` (nesta pasta): 925 posições, de 1 a 925, sem repetição, com justificativa em todas. Gerado pela `dev` (commit `3ec2864`) a partir de `fila_cirurgica.csv` com SHA-256 `fadce426…f11b2`.

- **Verificador oficial**: OK (regra de ouro respeitada e formato válido). Mediana dos oncológicos: posição 143; 100% estão no primeiro terço; 100% dos pacientes sem urgência estão no último terço.
- **Incerteza**: dos 924 pares vizinhos, 612 ainda são incertos; a 50 posições de distância nenhum par é incerto.
- **Testes**: 170 testes, Ruff e formatação passando.

Para reproduzir: `uv sync --locked --no-editable --extra dev` e `uv run --no-sync python tools/acceptance.py --dataset <pasta do dataset> --output-root <pasta nova>`; detalhes no [README](README.md).

## O que ficou pendente (não escondido)

- **Validação clínica** de pesos, forma linear, limiares da classe SWALIS (dor 7 e 4) e relação ASA × porte. Hoje tudo é hipótese técnica de demonstração. Os mapeamentos usados na reavaliação (por exemplo, deterioração moderada = 3, cardiopatia = 2 pontos) também são aproximações.
- **Ordem de importância dos critérios definida pela equipe** (CID, deterioração na espera, comorbidades, porte, ASA, limitação funcional, dor e questões socioeconômicas): CID e porte já são lidos pelo OCR e chegam ao tribunal, mas **ainda não entram na pontuação**, que continua com os seis critérios acima. Aplicá-la exige reordenar os pesos e recalcular os 925.
- **A reavaliação por documento é uma aproximação** do recálculo completo da ROR (que leva minutos para a fila inteira): aplica a função de valor ao paciente e o encaixa pela hierarquia. O limite de elevação (~10% da fila) pode reduzir a subida proposta.
- **Aceite das exclusões** pelo responsável (acima).
- **Extração com IA**: roda com o Gemini real (`gemini-3.5-flash-lite`) sobre PDF com texto, mas foi validada com poucos laudos fictícios, não com o conjunto de 40 documentos com gabarito. Imagens e PDF escaneado vão para revisão manual.
- **Evidências lidas pelo OCR entram aprovadas pelo sistema**, sem conferência individual do médico (decisão da equipe para a demonstração). A exigência de documento sintético foi removida do envio; só o mascaramento de nome e CNS protege o texto enviado ao Gemini. Antes de qualquer uso real é preciso revisão de LGPD e do termo de envio (hoje uma minuta).
- **Dependência do provedor**: leitura e tribunal precisam de `GEMINI_API_KEY` e `GEMINI_MODEL`. Sem eles, o documento fica só como recebido e nada é reavaliado.
- **Prioridade validada pela regulação**, a análise de benefício, risco e alternativas (BRAN) e o parecer especializado ainda não existem como funcionalidade.
- **Nome, município e procedimento** vêm do dataset e ficam visíveis só a quem já vê a fila; o app do paciente mostra apenas o que o backend sabe (sem nome nem cidade).
