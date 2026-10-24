# Plano vinculado: termo antes do upload

Spec: ../specs/001-extracao-de-exames/spec.md
Status: em revisão; upload e aceite ainda não implementados.

## Responsabilidades e dependências

- Produto: conferir finalidade e texto abaixo, identificar responsável pelo tratamento
  e definir canal assistencial alternativo. Aprovar o texto aplicável ao ambiente.
- Backend: fornecer versão/texto vigente; registrar aceite pela identidade autenticada,
  vinculado ao caso e à versão, com data/hora e prazo de guarda coerente com o envio.
- Web/app: exibir o texto antes do envio, sem caixa pré-selecionada, permitir cancelar
  e mostrar o canal alternativo definido. Não receber o arquivo antes da confirmação.

## Fluxo e contrato propostos para revisão

1. Consultar o termo vigente e seu identificador imutável de versão.
2. Registrar confirmação explícita do usuário autenticado, com solicitação vinculada.
   O servidor confere acesso ao caso e a versão vigente; não confia em nome/data do
   cliente. Não coletar IP, localização ou outros identificadores desnecessários.
3. Receber o arquivo somente com referência válida a esse aceite, da mesma identidade
   e caso. Validar antes de persistir bytes ou iniciar leitura/envio externo.
4. Se o termo mudou antes do envio, solicitar nova leitura/aceite; não reaproveitar
   aceite de outra versão, de outro caso ou de outro usuário.
5. Vincular documento, aceite e retenção. Registrar aprovação de evidência e mudança
   de fila separadamente: aceite do termo não aprova extração nem reposicionamento.

Rotas definitivas, transação de recebimento e retenção do aceite pertencem ao futuro
plano de upload. `POST /documentos` atual registra metadados, sem receber arquivos;
acrescentar só um booleano ali não implementa este fluxo.

## Minuta para revisão do produto (demonstração sintética)

> Este ambiente demonstra a leitura de documentos sintéticos. Não envie documentos
> de pacientes reais. O documento será associado à solicitação informada para propor
> informações sobre limitação funcional, ASA, dor, questões socioeconômicas,
> comorbidades, tipo e data do documento. Informações ausentes permanecem sem valor.
>
> As propostas são revisadas por profissionais autorizados e não alteram a posição
> na fila automaticamente. O envio não garante mudança de posição e não substitui
> atendimento de saúde. Documentos e derivados da demonstração são restritos aos
> envolvidos autorizados e têm guarda temporária de até sete dias.
>
> Antes de qualquer uso de serviço externo, serão informados o serviço, a finalidade
> e as condições aplicáveis. A ausência dessa informação impede o envio externo.
> Identificadores desnecessários devem ser mascarados; isso não autoriza dados reais
> neste ambiente. Você pode cancelar o envio e buscar orientação pelo canal
> assistencial indicado pela equipe.
>
> Confirmo que li as informações e que o arquivo contém somente dados sintéticos
> preparados para esta demonstração.

A minuta ainda não é texto vigente: faltam responsável/canal e conferência de
compatibilidade com o fluxo. Não presume base legal ou consentimento para atendimento
real. Mudança de finalidade ou ambiente exige nova revisão do termo.

## Critérios da futura implementação

- Sem aceite vigente, nenhum arquivo é recebido, armazenado ou processado.
- Aceite registra identidade do servidor, versão, caso e horário verificáveis.
- Versão antiga, usuário diferente e caso fora do escopo são rejeitados.
- Cancelar não dispara envio e apresenta o canal alternativo aprovado.
- Falha ou revogação aplicável impede uso futuro; não presume apagamento forense.
- Aceite não autoriza dados reais, diagnóstico, evidência aprovada ou mudança de fila.
