# Plano: Tribunal de IAs

Spec: ./spec.md
Status: aprovado para implementação pelo usuário em 2026-10-24

## Abordagem

Módulo Python `tribunal` dentro da API FastAPI do backend. Quando uma proposta de mudança de posição é criada, o serviço do tribunal:

1. Roda as travas determinísticas (regra de ouro, limite de elevação, hierarquia, sem preferência por espera). Se a proposta viola alguma trava, ela é barrada ou reduzida antes de gastar chamadas de LLM, e o motivo vai para o parecer.
2. Monta o contexto do caso já mascarado (sem nome, CNS ou município) e chama os três agentes em paralelo (`asyncio.gather`). Cada agente é uma chamada ao LLM com um prompt de papel próprio e uma saída estruturada validada por um schema.
3. Consolida os três votos por maioria, em uma função pura.
4. Se a recomendação for ajustar, passa a posição sugerida pelas travas de novo, porque os agentes não podem furar as regras.
5. Persiste o parecer vinculado à proposta e muda a situação para `pronta_para_medico`.

Se alguma chamada falhar ou estourar o tempo limite, a proposta fica em `aguardando_tribunal` e entra numa fila de novas tentativas com espera crescente. Depois de 3 falhas seguidas, a situação vira `tribunal_indisponivel` (o aviso da spec) e as tentativas continuam em intervalo maior.

## Dados e interfaces

**Contexto atual enviado aos agentes (mascarado):** identificador pseudônimo, CID, pontuação e posição da solicitação e dos afetados; evidências estruturadas aprovadas com IDs pseudônimos, travas e motivo de convocação. Sem dias de fila, nome, CNS, município ou trechos livres. Dados adicionais para BRAN dependem da revisão abaixo.

**Saída de cada agente (schema):**

```
agente: "evidencias" | "contestacao" | "equidade"
veredito: "a_favor" | "contra" | "ajustar"
posicao_sugerida: inteiro ou nulo (obrigatório quando veredito = ajustar)
justificativa: texto em português simples
evidencias_citadas: lista de ids de evento ou trechos usados
sem_comprovacao: booleano (só relato do paciente, sem exame)
```

**Parecer persistido:** `proposta_id`, as três manifestações, a recomendação (`aprovar` | `ajustar` | `negar`), o voto vencido (se houver), as travas aplicadas com o motivo, o modelo usado, a data e hora e o número de tentativas.

**Situação da proposta:** `aguardando_tribunal` → `pronta_para_medico`, ou `tribunal_indisponivel` (volta para `pronta_para_medico` quando uma nova tentativa der certo).

**Endpoints:**

- `POST /propostas/{id}/tribunal`: convoca o tribunal (também é chamado internamente quando a proposta é criada).
- `GET /propostas/{id}/parecer`: devolve o parecer e a situação.

## Decisões

| Decisão | Alternativas consideradas | Motivo |
|---|---|---|
| Provedor configurável por ambiente; adaptador existente preservado | Seleção adiada | Não escolher modelo nem realizar chamadas externas nesta revisão. |
| Nome do modelo e chave em variáveis de ambiente (`GEMINI_MODEL`, `GEMINI_API_KEY`) | Fixar no código | Os modelos e as cotas gratuitas mudam com frequência; dá para trocar sem commit. |
| Travas antes e depois dos agentes, em código puro | Pedir aos agentes que respeitem as regras | A spec exige que as travas sejam determinísticas e impossíveis de furar. Rodar antes também economiza cota. |
| Três chamadas em paralelo | Em sequência | O tempo total do caso fica igual ao da chamada mais lenta, o que importa na demo ao vivo. |
| Persistência em SQLite (`sqlite3` da biblioteca padrão) | Postgres | Zero infraestrutura no hackathon. Se a #25 escolher outro banco, só a camada de gravação muda. |
| Novas tentativas em tarefa de fundo do próprio FastAPI | Fila externa (Celery, Redis) | Um processo só, sem serviço extra. Limite: as tentativas se perdem se o processo reiniciar; elas são retomadas lendo as propostas em `aguardando_tribunal` ao subir. |
| Testes com o cliente do LLM substituído por respostas fixas | Testes contra a API real | Os testes ficam rápidos, determinísticos e sem gastar cota. Isso vale só para os testes: o produto não tem resposta simulada (spec, item 3). |

## Riscos

- **Cota gratuita esgotar na demo.** Mitigação: semáforo que limita os casos simultâneos; as travas barram antes de chamar o LLM; ensaiar a demo com poucos casos; ter uma segunda chave de API pronta.
- **Plano gratuito do Gemini pode usar os dados enviados para treino.** O dataset é sintético, então não há dado real exposto no hackathon. Uso com dados reais requer avaliação dos termos do provedor e dos requisitos aplicáveis; nenhuma conclusão jurídica é inferida do plano contratado. Fica registrado no `DECISOES.md`.
- **Cotas e nomes de modelo do plano gratuito mudam.** Mitigação: conferir no AI Studio antes da demo; o modelo fica em variável de ambiente.
- **O LLM pode devolver JSON fora do schema.** Mitigação: validar com Pydantic; uma resposta inválida conta como falha e entra nas novas tentativas.
- **O LLM pode escrever algo que soe como diagnóstico ou alarme.** Mitigação: o prompt de cada agente proíbe isso explicitamente, e um teste confere que o parecer não contém termos proibidos.
- **Limite de elevação:** 10% da fila ativa, arredondado para baixo, com prevalência da regra de ouro e hierarquia compartilhada com a pontuação.

## Atualização para implementação

Configurar GEMINI_MODEL explicitamente, sem supor cota ou gratuidade. API local protegida por token. Timeout 30 segundos/agente; tentativas persistidas em SQLite com backoff exponencial limitado a 300 segundos, aviso na terceira falha. Posições limitadas a 10%, exceto regra de ouro; o tribunal não pode dispensar essa trava. O serviço consulta a versão atual da fila, e exige nova análise quando ela muda. Prompts e allowlist de dados reduzem exposição; texto livre é removido do contexto do provedor e os agentes recebem códigos estruturados de evidência. O provedor deve satisfazer os requisitos de uso de dados aplicáveis; plano pago isoladamente não garante conformidade. Teste real depende de credenciais externas e deve ser registrado separadamente.

## Complemento autorizado em 2026-10-24

Implementar identidades com permissões por paciente, registro documental com evidência e revisão auditável, retenção máxima de sete dias e bloqueio de tentativas quando referências perderem validade. Tokens de acesso são individuais e carregados da configuração local; decisões usam identidade autenticada. A integração documental registra fonte/trecho/valor e aprovação, sem implementar OCR nem chamar Gemini nesta etapa. Dados aprovados são comparados ao registro do servidor; o cliente não pode declarar aprovação por conta própria. Limpeza abrange conteúdo dependente, relatórios e arquivos gerados em diretórios registrados, preservando originais. Testes usam relógio injetado. Atualizar documentação e verificar todos os critérios técnicos; revisão clínica não é fabricada.

## Revisão BRAN e parecer especializado — plano em revisão

A implementação de retirada da espera usa somente regra oncológica, hierarquia e
limite de elevação. Dias em fila não são enviados ao provedor. A ampliação abaixo
é uma entrega posterior; nenhum prompt de provedor foi alterado nesta etapa.

1. Acrescentar à manifestação de Contestação um bloco `bran` com quatro dimensões:
   benefícios, riscos, alternativas e consequências de não realizar/adiar. Cada
   dimensão contém situação (`documentado`, `ausente` ou `conflitante`), resumo e
   referências a evidências aprovadas do caso. Campos ausentes não são completados.
2. Antes de implementar, revisar com a equipe quais dados aprovados serão necessários:
   o contexto atual tem códigos de evidência e não contém informação suficiente para
   responder a todas as perguntas. Não ampliar o envio externo com texto livre sem
   revisão de minimização/mascaramento. Campos sem evidência retornam `ausente`.
3. Rever o contrato e a proveniência para eventual parecer especializado, com origem,
   protocolo, data e revisão profissional. O contrato atual não aceita um tipo livre
   de parecer; não disfarçá-lo como exame para passar na validação.
4. Acrescentar pendência explícita de revisão de indicação quando faltarem elementos.
   Isso não muda o veredito por regra fixa, não cancela a solicitação nem recomenda
   tratamento alternativo. Permanecem três agentes e decisão médica específica.
5. Testar o contrato com provedor de teste: dimensões ausentes, referências de outro
   caso, conflito, ausência de evidência, versão antiga e nenhuma exclusão automática.
   Testes de contrato não comprovam qualidade clínica da resposta de um LLM real.

Saída esperada: revisão de `Vote`, contexto e persistência, após aprovação deste
complemento e da suficiência dos dados. Escolha/alteração de LLM e chamada real a
Gemini continuam fora da implementação autorizada desta revisão da pontuação.
