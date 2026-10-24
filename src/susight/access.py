"""Locally provisioned demo identities; no self-assigned roles or patient scopes."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Principal:
    id: str
    papel: str
    pacientes: frozenset[str] = field(default_factory=frozenset)

    def permits(self, row):
        return self.papel == "admin" or row.get("paciente_id") in self.pacientes


class Access:
    def __init__(self, entries=None, token=None):
        self.entries = []
        if token:
            if len(token) < 16:
                raise ValueError("Token deve ter pelo menos 16 caracteres")
            self.entries.append(
                (hashlib.sha256(token.encode()).hexdigest(), Principal("admin-demo", "admin"))
            )
        seen = set()
        for entry in entries or []:
            digest = entry["token_sha256"]
            if entry["papel"] not in {"admin", "medico", "paciente"} or len(digest) != 64:
                raise ValueError("Identidade de acesso invalida")
            int(digest, 16)
            if digest in seen or not entry["id"].strip():
                raise ValueError("Identidades e tokens devem ser distintos")
            seen.add(digest)
            scope = frozenset(entry.get("pacientes", []))
            if entry["papel"] == "paciente" and len(scope) != 1:
                raise ValueError("Paciente exige exatamente um vinculo")
            self.entries.append((digest, Principal(entry["id"], entry["papel"], scope)))
        if len({p.id for _, p in self.entries}) != len(self.entries):
            raise ValueError("Identidade repetida")

    @classmethod
    def from_file(cls, path):
        return cls(entries=json.loads(Path(path).read_text())["identidades"])

    def resolve(self, authorization):
        if not authorization or not authorization.startswith("Bearer "):
            return None
        digest = hashlib.sha256(authorization[7:].encode()).hexdigest()
        for expected, principal in self.entries:
            if hmac.compare_digest(expected, digest):
                return principal
        return None
