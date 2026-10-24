"""Create a demo account with a provisional password written only to a private file."""

from __future__ import annotations

import argparse
import os
import secrets
from pathlib import Path

from .tribunal.store import Store


def create(database, aid, role, patients, secret_path):
    secret_path = Path(secret_path)
    password = secrets.token_urlsafe(18)
    store = Store(database)
    with os.fdopen(os.open(secret_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as stream:
        stream.write(password + "\n")
    try:
        store.provision_account(aid, role, patients, password)
    except BaseException:
        secret_path.unlink(missing_ok=True)
        raise
    return secret_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cria conta de demonstracao com senha provisoria")
    parser.add_argument("--database", required=True)
    parser.add_argument("--id", required=True)
    parser.add_argument("--papel", required=True, choices=["paciente", "medico", "admin"])
    parser.add_argument("--paciente", action="append", default=[])
    parser.add_argument("--senha-arquivo", required=True)
    args = parser.parse_args()
    try:
        path = create(args.database, args.id, args.papel, args.paciente, args.senha_arquivo)
        print("Conta criada; senha provisoria em:", path)
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Erro: {exc}\n")
