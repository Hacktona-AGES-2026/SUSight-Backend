from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


def now():
    return datetime.now(UTC).isoformat()


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS queues(version INTEGER PRIMARY KEY, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS proposals(
              id TEXT PRIMARY KEY, body TEXT NOT NULL, status TEXT NOT NULL,
              attempts INTEGER NOT NULL DEFAULT 0, next_try REAL NOT NULL DEFAULT 0,
              opinion TEXT, error TEXT, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS decisions(
              id INTEGER PRIMARY KEY, proposal_id TEXT NOT NULL, actor TEXT NOT NULL,
              action TEXT NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL);
            """)
            # Interrupted requests are safe to retry; completed opinions are not overwritten.
            db.execute(
                "UPDATE proposals SET status='aguardando_tribunal',next_try=0 WHERE status='processando'"
            )

    @contextmanager
    def db(self):
        with sqlite3.connect(self.path, timeout=10) as db:
            db.row_factory = sqlite3.Row
            yield db

    def queue(self):
        with self.db() as db:
            row = db.execute("SELECT * FROM queues ORDER BY version DESC LIMIT 1").fetchone()
        return (row["version"], json.loads(row["body"])) if row else (0, [])

    def import_queue(self, rows, expected_version):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            version = db.execute("SELECT COALESCE(MAX(version),0) FROM queues").fetchone()[0]
            if version != expected_version:
                raise ValueError("Versao da fila desatualizada")
            version += 1
            db.execute("INSERT INTO queues VALUES (?,?)", (version, json.dumps(rows)))
        return version

    def create(self, body):
        pid = uuid4().hex
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            version = db.execute("SELECT COALESCE(MAX(version),0) FROM queues").fetchone()[0]
            if version != body["versao_fila"]:
                raise ValueError("Versao da fila desatualizada")
            db.execute(
                "INSERT INTO proposals(id,body,status,created_at) VALUES (?,?,?,?)",
                (pid, json.dumps(body), "aguardando_tribunal", now()),
            )
        return pid

    def get(self, pid):
        with self.db() as db:
            row = db.execute("SELECT * FROM proposals WHERE id=?", (pid,)).fetchone()
        if not row:
            raise KeyError(pid)
        result = dict(row)
        result["body"] = json.loads(result["body"])
        result["opinion"] = json.loads(result["opinion"]) if result["opinion"] else None
        return result

    def claim(self, pid):
        with self.db() as db:
            result = db.execute(
                "UPDATE proposals SET status='processando' WHERE id=? AND status IN ('aguardando_tribunal','tribunal_indisponivel')",
                (pid,),
            )
            return result.rowcount == 1

    def finish(self, pid, status, opinion=None, error=None, delay=0):
        import time

        with self.db() as db:
            db.execute(
                "UPDATE proposals SET status=?,opinion=?,error=?,attempts=attempts+1,next_try=? WHERE id=?",
                (
                    status,
                    json.dumps(opinion) if opinion is not None else None,
                    error,
                    time.time() + delay,
                    pid,
                ),
            )

    def due(self):
        import time

        with self.db() as db:
            return [
                r[0]
                for r in db.execute(
                    "SELECT id FROM proposals WHERE status IN ('aguardando_tribunal','tribunal_indisponivel') AND next_try<=? ORDER BY created_at LIMIT 5",
                    (time.time(),),
                )
            ]

    def decide(self, pid, actor, action, reason, rows=None):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            p = db.execute("SELECT * FROM proposals WHERE id=?", (pid,)).fetchone()
            if not p or p["status"] != "pronta_para_medico":
                raise ValueError("Proposta nao esta pronta para decisao")
            body = json.loads(p["body"])
            version = db.execute("SELECT COALESCE(MAX(version),0) FROM queues").fetchone()[0]
            if version != body["versao_fila"]:
                raise ValueError("Fila mudou: nova analise necessaria")
            if action == "aprovar":
                if not rows:
                    raise ValueError("Fila resultante ausente")
                db.execute("INSERT INTO queues VALUES (?,?)", (version + 1, json.dumps(rows)))
            db.execute(
                "INSERT INTO decisions(proposal_id,actor,action,reason,created_at) VALUES (?,?,?,?,?)",
                (pid, actor, action, reason, now()),
            )
            db.execute("UPDATE proposals SET status=? WHERE id=?", (action, pid))
            return version + 1 if action == "aprovar" else version
