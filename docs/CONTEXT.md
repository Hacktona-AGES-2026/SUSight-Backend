# Contexto: SUSight-Backend

## Este repositório

API, tratamento do dataset, pontuação da fila, pipeline de análise de exames, tribunal de IAs, registro auditável de decisões e geração da fila ordenada. Tasks com o prefixo [Backend].

## O desafio

Hackathon. A equipe recebeu um dataset não tratado da fila do SUS e precisa:

1. Tratar o dataset.
2. Criar uma aplicação para gerenciar a fila de cirurgias eletivas do SUS.

Tema: decidir de forma justa, segura e explicável quem deve operar primeiro e manter essa decisão atualizada enquanto o paciente espera.

Entrega final: export em CSV da lista ordenada corretamente.

## Critérios de movimento da fila

A posição sobe conforme o quanto o paciente está sendo prejudicado por esperar. Critérios atuais:

- limitação funcional;
- ASA (classificação de risco anestésico);
- dor;
- questões socioeconômicas;
- comorbidades;
- tempo de espera;
- deterioração durante a espera.

A prioridade manual da regulação é informativa, sem peso na pontuação (spec 002). As preferências de swing e ROR dependem de validação; regras de equidade incluem limite de elevação de 10% por reavaliação e a regra de ouro oncológica. Há conflito de modelagem no dataset completo, descrito em `docs/backend-validation.md`.

## Fluxo do sistema

```
Paciente ou médico envia exame, laudo ou atualização
        |
IA aplica os critérios
        |
Tribunal de IAs: agentes argumentam prós e contras de mudar a posição
        |
IA envia a proposta de nova fila ao médico
        |
Médico revisa
   - Aprova: fila do SUS é atualizada e o paciente é avisado
   - Pede informações ao paciente
   - Rejeita com motivo: volta para a IA reavaliar com o motivo
        |
Export CSV da fila ordenada (entrega do hackathon)
```

## Princípios

- A IA só propõe. Nada muda na fila até um profissional aprovar.
- Toda decisão é registrada com nome, data e hora.
- A IA nunca decide sozinha. Relatos do paciente não substituem exames.
- Sem diagnóstico e sem substituir atendimento de urgência (orientar para UPA ou SAMU 192).
- Textos em português do Brasil, linguagem simples e sem alarme.

A lista completa está em `specs/constitution.md`.

## Tribunal de IAs

Hoje a interface mostra três agentes dando veredito sobre cada proposta:

| Agente | Papel |
|---|---|
| Evidências | Argumenta a favor da mudança, citando evidências |
| Contestação | Argumenta contra e aponta o que falta confirmar |
| Equidade e regras | Confere limites e justiça frente ao resto da fila |

O modelo definido usa três agentes fixos. O tribunal recebe propostas de ordenação incerta ou evidência conflitante; não analisa automaticamente toda a fila inicial.

## Produto

- **Pulse (app do paciente, híbrido):** upload de exames e laudos, posição na fila, notificações, widgets, histórico, atualizar situação (dor, mobilidade, texto ou áudio), perfil e preferências (LGPD, Face ID).
- **Pulse Clinical (web, médico):** revisões pendentes, revisão da proposta com tribunal, aprovar, rejeitar com motivo ou pedir informações, fila do SUS e contestação, decisões registradas e exportar a fila em CSV.
- Fora do escopo: chatbot do paciente.

## Repositórios

| Repositório | Conteúdo |
|---|---|
| SUSight | App Pulse (paciente), design, documentação e coordenação |
| SUSight-Web | Pulse Clinical (médico) |
| SUSight-Backend | API, tratamento de dados, pontuação da fila, IA e tribunal |

Tasks: https://github.com/orgs/Hacktona-AGES-2026/projects/6. O título de cada task começa com o repositório de destino.

## Como trabalhamos

- Spec-driven development: veja `docs/sdd/MANUAL.md`.
- Git flow: `main`, `dev` e `feature/<nome>`. PRs vão para a `dev`.
- Commits atômicos e nenhum merge sem revisão de uma pessoa desenvolvedora.

## Glossário

- **Fila do SUS / regulação:** lista de espera de cirurgias eletivas gerida pela regulação.
- **CNS:** Cartão Nacional de Saúde, exibido mascarado.
- **ASA:** classificação do estado físico do paciente para risco anestésico.
- **UBS / UPA / SAMU (192):** atenção básica, urgência e ambulância.
- **LGPD:** lei de proteção de dados pessoais.
- **Prioridade:** Baixa, Moderada ou Alta, validada pela regulação.

## Decisões em aberto

1. Resolver o conflito entre regras rígidas e ordem necessária da ROR no dataset completo.
2. Pesos dos critérios e regras de equidade.
3. Tratamento do dataset: limpeza, deduplicação e campos de prioridade e tempo de espera.
4. Integração do Backend Python/FastAPI/SQLite com o setup da equipe e validação do provedor de IA.
