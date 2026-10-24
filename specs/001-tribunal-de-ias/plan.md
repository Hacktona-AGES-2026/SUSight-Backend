# Plano: Tribunal de IAs

Spec: ./spec.md
Status: em revisão

## Abordagem

Módulo Python `tribunal` dentro da API FastAPI do backend. Quando uma proposta de mudança de posição é criada, o serviço do tribunal:

1. Roda as travas determinísticas (regra de ouro, limite de elevação, não ultrapassar quem tem prioridade maior e mais espera). Se a proposta viola alguma trava, ela é barrada ou reduzida antes de gastar chamadas de LLM, e o motivo vai para o parecer.
2. Monta o contexto do caso já mascarado (sem nome, CNS ou município) e chama os três agentes em paralelo (`asyncio.gather`). Cada agente é uma chamada ao LLM com um prompt de papel próprio e uma saída estruturada validada por um schema.
3. Consolida os três votos por maioria, em uma função pura.
4. Se a recomendação for ajustar, passa a posição sugerida pelas travas de novo, porque os agentes não podem furar as regras.
5. Persiste o parecer vinculado à proposta e muda a situação para `pronta_para_medico`.

Se alguma chamada falhar ou estourar o tempo limite, a proposta fica em `aguardando_tribunal` e entra numa fila de novas tentativas com espera crescente. Depois de 3 falhas seguidas, a situação vira `tribunal_indisponivel` (o aviso da spec) e as tentativas continuam em intervalo maior.

## Dados e interfaces

**Contexto enviado aos agentes (mascarado):** id pseudônimo da solicitação, idade, sexo, CID principal e secundário, ASA, dor (EVA), limitação funcional, comorbidades, dias em fila, prioridade da regulação, posição atual, posição proposta, critérios que motivaram a mudança e as evidências (eventos clínicos e trechos de laudo). Também vai um resumo dos pacientes que seriam ultrapassados (CID, prioridade e dias em fila, sem identificação).

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
| Provedor: Google Gemini, modelo Flash do plano gratuito (via SDK `google-genai`) | Groq (gratuito, modelos abertos), OpenRouter `:free`, Ollama local, Claude (pago) | O time quer custo zero. O plano gratuito do Gemini tem a cota mais folgada entre as opções gratuitas e saída estruturada por schema. O Groq limita a 8 mil tokens por minuto, e um caso usa cerca de 11 mil. O OpenRouter limita a 50 requisições por dia, cerca de 16 casos. O Ollama depende do hardware de quem roda a demo. |
| Nome do modelo e chave em variáveis de ambiente (`GEMINI_MODEL`, `GEMINI_API_KEY`) | Fixar no código | Os modelos e as cotas gratuitas mudam com frequência; dá para trocar sem commit. |
| Travas antes e depois dos agentes, em código puro | Pedir aos agentes que respeitem as regras | A spec exige que as travas sejam determinísticas e impossíveis de furar. Rodar antes também economiza cota. |
| Três chamadas em paralelo | Em sequência | O tempo total do caso fica igual ao da chamada mais lenta, o que importa na demo ao vivo. |
| Persistência em SQLite (`sqlite3` da biblioteca padrão) | Postgres | Zero infraestrutura no hackathon. Se a #25 escolher outro banco, só a camada de gravação muda. |
| Novas tentativas em tarefa de fundo do próprio FastAPI | Fila externa (Celery, Redis) | Um processo só, sem serviço extra. Limite: as tentativas se perdem se o processo reiniciar; elas são retomadas lendo as propostas em `aguardando_tribunal` ao subir. |
| Testes com o cliente do LLM substituído por respostas fixas | Testes contra a API real | Os testes ficam rápidos, determinísticos e sem gastar cota. Isso vale só para os testes: o produto não tem resposta simulada (spec, item 3). |

## Riscos

- **Cota gratuita esgotar na demo.** Mitigação: semáforo que limita os casos simultâneos; as travas barram antes de chamar o LLM; ensaiar a demo com poucos casos; ter uma segunda chave de API pronta.
- **Plano gratuito do Gemini pode usar os dados enviados para treino.** O dataset é sintético, então não há dado real exposto no hackathon. Em produção com dados reais, isso viola a LGPD e exige um plano pago com retenção zero. Fica registrado no `DECISOES.md`.
- **Cotas e nomes de modelo do plano gratuito mudam.** Mitigação: conferir no AI Studio antes da demo; o modelo fica em variável de ambiente.
- **O LLM pode devolver JSON fora do schema.** Mitigação: validar com Pydantic; uma resposta inválida conta como falha e entra nas novas tentativas.
- **O LLM pode escrever algo que soe como diagnóstico ou alarme.** Mitigação: o prompt de cada agente proíbe isso explicitamente, e um teste confere que o parecer não contém termos proibidos.
- **O valor do limite de elevação ainda não foi definido** (#6). Mitigação: fica em configuração com um valor provisório marcado no código até a #6 fechar.
