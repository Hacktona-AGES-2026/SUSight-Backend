# Plano: Contas e sessões

Spec: ./spec.md
Status: em revisão

## Abordagem

Contas e sessões no mesmo SQLite do `Store`. Senha com `hashlib.scrypt` e sal
aleatório, comparada com `hmac.compare_digest`, só biblioteca padrão. O token de
sessão é aleatório (`secrets`), devolvido uma vez e guardado só como SHA-256. A
autenticação da API tenta primeiro os tokens estáticos do `access.json` e depois a
sessão.

## Dados e interfaces

- **`accounts`**: `id` (identificador), `papel`, `pacientes` (JSON), `senha_hash`, `sal`, `tentativas`, `bloqueado_ate`, `created_at`.
- **`sessions`**: `token_sha256`, `account_id`, `created_at`, `last_seen`.

| Rota | Efeito |
|---|---|
| `POST /sessoes` `{identificador, senha}` | 200 com `token`, `papel` e `inatividade_segundos`; 401 genérico; 429 com conta bloqueada |
| `DELETE /sessoes` | encerra a sessão do token e remove os dispositivos da identidade |

Linha de comando: `python -m susight.accounts --database BANCO --id ID --papel paciente|medico
--paciente PAC... --senha-arquivo ARQUIVO`. Grava a senha gerada em `ARQUIVO` com
permissão 0600 e falha se o arquivo ou a conta já existirem.

## Decisões

| Decisão | Alternativas consideradas | Motivo |
|---|---|---|
| `hashlib.scrypt` | bcrypt, argon2 | Biblioteca padrão, sem dependência nova, resistente a força bruta. |
| Token de sessão guardado como hash | Guardar o token | Vazamento do banco não entrega sessões válidas. |
| Inatividade medida pelo relógio do `Store` | Relógio do sistema | Mesmo relógio controlável dos testes. |
| Mensagem única para identificador ou senha errados | Mensagens distintas | Não revela quais identificadores existem. |

## Riscos

- Bloqueio por tentativas permite travar a conta de outra pessoa: aceitável na demonstração; rever antes de uso real.
