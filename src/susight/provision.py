"""Provision individual demo tokens locally, without printing their values."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
from pathlib import Path


def provision(directory, patient):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    access = directory / "access.json"
    if access.exists():
        raise ValueError("Configuracao existente: nao sobrescrever identidades")
    entries = []
    created = []
    try:
        for uid, role, scope in [
            ("admin-demo", "admin", []),
            ("medico-demo", "medico", [patient]),
            ("paciente-demo", "paciente", [patient]),
        ]:
            token = secrets.token_urlsafe(32)
            path = directory / (uid + ".token")
            with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as stream:
                stream.write(token + "\n")
            created.append(path)
            entries.append(
                {
                    "id": uid,
                    "papel": role,
                    "pacientes": scope,
                    "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
                }
            )
        with os.fdopen(os.open(access, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as stream:
            json.dump({"identidades": entries}, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    except BaseException:
        for path in created:
            path.unlink(missing_ok=True)
        raise
    return access


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cria tokens individuais para a demonstracao sintetica")
    parser.add_argument("--directory", required=True)
    parser.add_argument("--patient", required=True)
    args = parser.parse_args()
    try:
        print("Configuracao criada em:", provision(args.directory, args.patient))
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Erro: {exc}\n")
