# Spec: Contas e sessões

Issue: a definir
Status: rascunho

## Contexto

O app do paciente (spec 005-login) e o web do médico (spec 002-login) precisam autenticar pessoas. Os pacientes vêm do dataset e o app não cria conta. Os médicos são cadastrados previamente. Hoje as identidades do backend vêm de um arquivo `access.json` com permissões por paciente, sem senha de paciente, sessão com expiração nem bloqueio por tentativas.

## Comportamento esperado

1. O paciente entra com um identificador (CPF ou Cartão SUS, a decidir) e uma senha. O backend valida contra os pacientes cadastrados a partir do dataset e não permite criar conta nova.
2. O médico entra com identificador e senha de profissional cadastrado.
3. Credenciais inválidas retornam mensagem em português sem dizer qual campo está errado.
4. O login bem-sucedido devolve uma sessão que expira por inatividade. A sessão pode ser encerrada ("Sair da conta"), o que invalida o acesso e remove o dispositivo de avisos (spec 005).
5. Depois de um número de tentativas erradas, a conta fica bloqueada por um período.
6. Senha nunca é guardada em texto claro. Identificador e senha não aparecem em registros nem em mensagens de erro.
7. O paciente acessa apenas dados da própria solicitação; o médico, os casos que tem permissão para revisar. Toda decisão guarda o responsável autenticado.
8. A ligação entre paciente do dataset e conta é feita no cadastro inicial, com senha provisória de demonstração.

## Critérios de aceite

- [ ] Login válido de paciente e de médico devolve sessão; credencial inválida não revela qual campo errou.
- [ ] Não existe operação para criar conta de paciente.
- [ ] Senha é guardada apenas como hash.
- [ ] A sessão expira por inatividade e deixa de dar acesso depois de "Sair da conta".
- [ ] Excesso de tentativas erradas bloqueia temporariamente a conta.
- [ ] Um paciente não consegue ler dados de outro; um médico sem permissão não revisa o caso.
- [ ] Identificador e senha não aparecem em registros de log.

## Testes (TDD)

Os testes vêm antes do código. Cada critério de aceite acima vira pelo menos um teste automatizado que falha primeiro (red), e a implementação só termina quando todos passam (green). Critério que não puder ser testado automaticamente leva uma justificativa escrita. Testes automatizados com pytest, incluindo o verificador oficial da fila quando houver `fila_priorizada.csv` (`tools/verificar_fila_priorizada.py`).

## Fora do escopo

- Login pelo gov.br.
- Face ID (feito no aparelho, spec 003 do app).
- Recuperação de senha.

## Questões em aberto

- Qual identificador vale: CPF, Cartão SUS ou ambos? O dataset tem CPF?
- Tempo de inatividade da sessão e número de tentativas antes do bloqueio.
- Como o time entrega as senhas provisórias da demonstração?
- Médico e paciente usam a mesma tabela de contas ou tabelas separadas?
