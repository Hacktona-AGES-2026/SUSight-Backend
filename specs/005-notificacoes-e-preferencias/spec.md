# Spec: Notificações, preferências e contatos

Issue: a definir
Status: rascunho

## Contexto

O app do paciente (specs 002, 003 e 004) mostra notificações no sino, permite ligar ou desligar avisos, lista contatos que acompanham a situação e exibe avisos na tela de bloqueio e em widgets. O painel do médico (web) também recebe avisos. O backend ainda não guarda nada disso.

## Comportamento esperado

**Notificações**

1. O backend gera uma notificação quando: o documento é recebido; a análise do documento termina; a prioridade é validada; o médico pede mais informações (um exame); a posição muda depois de aprovação; a reavaliação termina.
2. Cada notificação tem destinatário, tipo, título, texto curto, data e hora e situação lida ou não lida. O paciente lista as suas, da mais recente para a mais antiga, e marca como lida.
3. O texto não faz diagnóstico, não promete mudança de posição e não usa tom de alarme. Não leva nome completo nem CNS.
4. O médico recebe avisos de nova proposta para revisão, de fila aprovada e atualizada e de resposta do paciente a um pedido.

**Preferências**

5. O paciente liga ou desliga os avisos no aplicativo por tipo (documento recebido, análise concluída, prioridade validada). O aviso de exame pedido pelo médico não pode ser desligado e sempre é gerado.
6. Não há canal de WhatsApp.

**Contatos de acompanhamento**

7. O paciente cadastra pessoas que acompanham a situação, com nome, parentesco e telefone. O telefone volta mascarado nas leituras.
8. Contatos recebem apenas avisos curtos sobre a situação da solicitação. Não veem exames, laudos nem histórico clínico.

**Dispositivos**

9. O app registra o dispositivo do paciente para receber avisos na tela de bloqueio e atualizar widgets quando a posição muda ou um exame é pedido, recebido ou entra em análise. O dispositivo pode ser removido ao sair da conta.

## Critérios de aceite

- [ ] Cada evento do item 1 gera uma notificação para o paciente correto.
- [ ] Notificação lida deixa de aparecer como nova.
- [ ] O aviso de exame pedido continua sendo gerado mesmo com os avisos desligados.
- [ ] Preferência desligada impede a notificação do tipo correspondente.
- [ ] Telefone de contato é devolvido mascarado.
- [ ] Um paciente não lê notificações, contatos ou dispositivos de outro.
- [ ] Notificações não contêm diagnóstico, nome completo nem CNS.
- [ ] Ao sair da conta, o dispositivo deixa de receber avisos.

## Testes (TDD)

Os testes vêm antes do código. Cada critério de aceite acima vira pelo menos um teste automatizado que falha primeiro (red), e a implementação só termina quando todos passam (green). Critério que não puder ser testado automaticamente leva uma justificativa escrita. Testes automatizados com pytest, incluindo o verificador oficial da fila quando houver `fila_priorizada.csv` (`tools/verificar_fila_priorizada.py`).

## Fora do escopo

- Telas e widgets (specs do app).
- Envio efetivo pelo serviço de push do iOS ou Android.
- Canal de WhatsApp e chatbot.

## Questões em aberto

- Qual serviço entrega os avisos de push no hackathon, ou só se simula a lista no app?
- Os contatos têm acesso próprio (login) ou só recebem mensagens?
- Notificações expiram? Ver spec 004-historico-e-retencao.
