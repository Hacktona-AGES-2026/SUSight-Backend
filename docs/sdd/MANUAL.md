# Manual de SDD (Spec-Driven Development)

Neste projeto, a especificação vem antes do código. Ninguém implementa uma feature sem uma spec aprovada.

## Estrutura

```
specs/
  constitution.md        Princípios que valem para todo o projeto
  _template/             Modelos para copiar ao criar uma feature
    spec.md              O que e por quê
    plan.md              Como
    tasks.md             Passos executáveis
  NNN-nome-da-feature/   Uma pasta por feature (copiada de _template)
docs/sdd/MANUAL.md       Este manual
```

## Fluxo

1. **Constituição.** Leia `specs/constitution.md`. Toda spec e todo plano precisam respeitá-la.
2. **Spec.** Copie `specs/_template` para `specs/NNN-nome-da-feature` e preencha `spec.md`. Descreva o comportamento esperado e os critérios de aceite. Não fale de tecnologia aqui.
3. **Revisão da spec.** Uma pessoa da equipe revisa e aprova a spec antes de seguir.
4. **Plano.** Preencha `plan.md`: abordagem técnica, dados envolvidos, riscos e decisões. Revise e aprove.
5. **Tarefas.** Preencha `tasks.md` com passos pequenos e verificáveis. Cada passo vira um commit atômico.
6. **Implementação.** Execute as tarefas em ordem. Se o código precisar divergir da spec, atualize a spec primeiro.
7. **Verificação.** Confira cada critério de aceite da spec. A feature só está pronta quando todos passam.

## Regras

- A spec é a fonte da verdade. Código e spec nunca devem discordar.
- Uma feature por pasta, numerada em sequência (001, 002, ...).
- Dúvida em aberto vai para a seção "Questões em aberto" da spec, não para um palpite no código.
- Um PR por feature ou por grupo pequeno de tarefas, sempre citando a pasta da spec e a issue do GitHub.
- Commits atômicos: uma mudança lógica por commit.
- Nenhum merge sem revisão de uma pessoa desenvolvedora.

## Como criar uma feature

```
cp -r specs/_template specs/001-nome-da-feature
```

Depois preencha `spec.md`, peça revisão, siga para `plan.md` e `tasks.md`.

## Uso com IA

A IA recebe a spec e o plano como contexto e implementa as tarefas. Ela não decide escopo: se faltar informação, registra em "Questões em aberto" e pergunta.
