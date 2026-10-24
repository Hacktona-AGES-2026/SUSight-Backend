# Decisões do SUSight (Desafio 1 · Priorização Inteligente da Fila Cirúrgica)

Backend do SUSight. Toda a demonstração usa o dataset sintético do desafio (data de referência 23/10/2026). A parametrização do modelo é **demonstrativa e não tem validação clínica**; a justificativa de cada linha do CSV diz isso.

## Qual abordagem

**A IA só propõe; o médico decide.** Em vez de fixar um peso por critério (escolha arbitrária difícil de defender), o backend combina quatro ideias:

1. **Hierarquia rígida antes de qualquer peso.** Quem tem câncer (CID `C*`) ou não é classificado como sem urgência vem antes de quem não tem urgência clínica. Dentro desse grupo, a classe **SWALIS** (A1, A2, B, C, D) ordena em camadas. A regra de ouro do desafio é uma precedência, não uma competição entre pesos: nenhum oncológico pode ficar abaixo de um paciente sem urgência, qualquer que seja o peso.
2. **Swing weighting + ROR (Robust Ordinal Regression).** Dentro de cada classe, a importância dos seis critérios (limitação funcional, ASA, dor, comorbidades, deterioração e distância) vem de faixas de peso, não de números exatos. A ROR considera **todas** as ponderações compatíveis e separa a ordem **necessária** (vale em todas) da **incerta** (depende dos pesos). Na demonstração, a curva de cada critério é linear, a ordem dos pesos segue a dos swings e as faixas são de ±10%.
3. **Tribunal de IAs só nos casos incertos.** Três agentes (evidências, contestação, equidade) debatem uma proposta de mudança e o médico recebe o debate junto com ela. O tribunal é consultivo, nunca altera a fila sozinho, e nunca responde com texto simulado: sem provedor configurado ele registra indisponibilidade.
4. **Reavaliação a cada evento.** Exame, laudo ou pedido do médico gera uma proposta; o médico aprova, rejeita com motivo ou pede informações. Toda decisão fica registrada com nome, data e hora e entra no histórico.

## Para quem

O **regulador / médico revisor** é o usuário principal: recebe a lista de propostas, vê as evidências aprovadas, o parecer do tribunal e o histórico, e decide. O **paciente** acompanha a própria posição e envia exames; ele não relata sintomas, porque relato não substitui exame.

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

## Tratamento dos defeitos dos dados

Entrada: 941 solicitações, 1.505 eventos e 23 procedimentos. O tratamento mantém os arquivos originais intactos e registra cada decisão.

- **16 solicitações excluídas** da fila (desistência ou cirurgia em outro serviço, por texto de observação), todas listadas com o motivo no `DECISOES.md` gerado pela pipeline. **Nenhuma tem CID oncológico.** Duas delas têm só texto de familiar ("operou pelo convênio") e três dizem "não deseja mais operar no momento, melhorou com remédio": **pedem confirmação de quem conhece a regulação** antes de uso real.
- **Duplicatas:** 44 candidatas ficam ativas e marcadas para revisão, porque a equivalência positiva não foi comprovada. Eventos duplicados exatos (6) são unificados; 9 eventos órfãos ficam separados.
- **Flags que não batem**: 44 de oncológico, 30 de diabético e 76 de piora clínica divergem do diagnóstico ou dos eventos; o CID e os eventos prevalecem.
- **Valores ausentes ou inválidos** (ASA 26, dor 38, limitação 20, distância 20) recebem a mediana da especialidade, ficam marcados como "dado incompleto" (103 imputações) e nunca provam ausência de urgência.
- **Biópsia positiva com CID divergente** (23): gera revisão clínica; o sistema não reescreve o diagnóstico.

## Resultado

`fila_priorizada.csv` (nesta pasta): 925 posições, de 1 a 925, sem repetição, com justificativa em todas. Gerado pela `dev` (commit `3ec2864`) a partir de `fila_cirurgica.csv` com SHA-256 `fadce426…f11b2`.

- **Verificador oficial**: OK (regra de ouro respeitada e formato válido). Mediana dos oncológicos: posição 143; 100% estão no primeiro terço; 100% dos pacientes sem urgência estão no último terço.
- **Incerteza**: dos 924 pares vizinhos, 612 ainda são incertos; a 50 posições de distância nenhum par é incerto.
- **Testes**: 155 testes, Ruff e formatação passando.

Para reproduzir: `uv sync --locked --no-editable --extra dev` e `uv run --no-sync python tools/acceptance.py --dataset <pasta do dataset> --output-root <pasta nova>`; detalhes no [README](README.md).

## O que ficou pendente (não escondido)

- **Validação clínica** de pesos, forma linear, limiares da classe SWALIS (dor 7 e 4) e relação ASA × porte. Hoje tudo é hipótese técnica de demonstração.
- **Aceite das exclusões** pelo responsável (acima).
- **Extração com IA** de exames e laudos: implementada e testada com extrator simulado; falta rodar com o Gemini real e o conjunto de 40 documentos sintéticos com gabarito. Só PDF com texto é lido automaticamente; imagens vão para revisão manual.
- **Termo de envio**: há uma minuta; o texto final e o canal alternativo dependem do produto.
- **Prioridade validada pela regulação**, a análise de benefício, risco e alternativas (BRAN) e o parecer especializado ainda não existem como funcionalidade.
- **Web e app do paciente** usam contratos próprios; falta alinhá-los a estas rotas (lista e detalhe de propostas já existem).
