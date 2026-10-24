# Regras do projeto

- Nunca me coloque como coautor ou autor em nada no GitHub: commits (sem `Co-Authored-By`), PRs, issues, comentários, tasks do project, descrições e qualquer outro texto.
- Não adicione linhas de atribuição como "Generated with Claude Code".
- Toda alteração que eu fizer vai em commits atômicos: cada commit tem uma única mudança lógica e funciona sozinho. Quando a Fernanda começar uma task, eu já comito conforme avanço, em commits pequenos e bem organizados, sem me colocar como coautor.
- O projeto segue git flow. Branches: `main` (produção), `dev` (integração), `feature/<nome>` (saem da `dev` e voltam por PR para a `dev`), `release/<versão>` e `hotfix/<nome>`. PRs de trabalho normal sempre têm a `dev` como destino.
- Nunca faça merge de nada, em nenhuma branch (incluindo `dev` e `main`). Todo merge só acontece depois de revisão de um desenvolvedor, feita por uma pessoa. Eu posso abrir PRs, mas não mergeio nem habilito auto-merge.
