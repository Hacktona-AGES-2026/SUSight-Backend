from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from susight.artifacts import TTL
from susight.policy import POLICY_VERSION

from .guards import validate_queue


class EvidenceUnavailable(ValueError):
    pass


class Store:
    def __init__(self, path, clock=time.time):
        self.path, self.clock = str(path), clock
        Path(path).parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.db() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS queues(version INTEGER PRIMARY KEY, body TEXT NOT NULL, expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS proposals(
              id TEXT PRIMARY KEY, body TEXT NOT NULL, status TEXT NOT NULL,
              attempts INTEGER NOT NULL DEFAULT 0, next_try REAL NOT NULL DEFAULT 0,
              opinion TEXT, error TEXT, created_at TEXT NOT NULL, expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS decisions(
              id INTEGER PRIMARY KEY, proposal_id TEXT NOT NULL, actor TEXT NOT NULL,
              action TEXT NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL, expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY, sid TEXT NOT NULL, body TEXT NOT NULL,
              actor TEXT NOT NULL, created_at TEXT NOT NULL, expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS evidence(id TEXT PRIMARY KEY, document_id TEXT NOT NULL,
              body TEXT NOT NULL, status TEXT NOT NULL, actor TEXT NOT NULL, reviewer TEXT,
              reason TEXT, reviewed_at TEXT, expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS counters(name TEXT PRIMARY KEY, value INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS queue_imports(version INTEGER PRIMARY KEY, actor TEXT NOT NULL, created_at TEXT NOT NULL, expires REAL NOT NULL);
            -- Audit trail (spec 004): never expires and never holds document content, name or CNS.
            CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, sid TEXT NOT NULL, paciente_id TEXT,
              tipo TEXT NOT NULL, actor TEXT NOT NULL, texto TEXT NOT NULL, motivo TEXT, created_at TEXT NOT NULL);
            """)
            for table in ["queues", "proposals", "decisions"]:
                if "expires" not in {r[1] for r in db.execute(f"PRAGMA table_info({table})")}:
                    # Legacy queues lack a trustworthy creation instant: expire conservatively.
                    db.execute(f"ALTER TABLE {table} ADD COLUMN expires REAL NOT NULL DEFAULT 0")
            if "policy" not in {r[1] for r in db.execute("PRAGMA table_info(queues)")}:
                db.execute("ALTER TABLE queues ADD COLUMN policy TEXT NOT NULL DEFAULT 'legado'")
            db.execute(
                "UPDATE proposals SET status='desatualizada',error='Politica mudou: reimporte a fila e crie nova proposta' "
                "WHERE status IN ('processando','aguardando_tribunal','tribunal_indisponivel','pronta_para_medico') "
                "AND CAST(json_extract(body,'$.versao_fila') AS INTEGER) IN (SELECT version FROM queues WHERE policy<>?)",
                (POLICY_VERSION,),
            )
            db.execute(
                "INSERT OR IGNORE INTO counters VALUES ('queue', (SELECT COALESCE(MAX(version),0) FROM queues))"
            )
            db.execute(
                "UPDATE proposals SET status='aguardando_tribunal',next_try=0 WHERE status='processando'"
            )
        Path(path).chmod(0o600)
        self.purge_expired()

    @contextmanager
    def db(self):
        with sqlite3.connect(self.path, timeout=10) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA secure_delete=ON")
            yield db

    def instant(self):
        return datetime.fromtimestamp(self.clock(), UTC).isoformat()

    def purge_expired(self):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            now = self.clock()
            db.execute(
                "DELETE FROM evidence WHERE expires<=? OR document_id IN (SELECT id FROM documents WHERE expires<=?)",
                (now, now),
            )
            db.execute("DELETE FROM documents WHERE expires<=?", (now,))
            db.execute(
                "DELETE FROM proposals WHERE expires<=? OR CAST(json_extract(body,'$.versao_fila') AS INTEGER) IN (SELECT version FROM queues WHERE expires<=?)",
                (now, now),
            )
            db.execute(
                "DELETE FROM decisions WHERE expires<=? OR proposal_id NOT IN (SELECT id FROM proposals)",
                (now,),
            )
            db.execute("DELETE FROM queues WHERE expires<=?", (now,))
            db.execute("DELETE FROM queue_imports WHERE expires<=?", (now,))

    def _event(self, db, sid, patient, kind, actor, text, reason=None):
        db.execute(
            "INSERT INTO events(sid,paciente_id,tipo,actor,texto,motivo,created_at) VALUES (?,?,?,?,?,?,?)",
            (sid, patient, kind, actor, text, reason or None, self.instant()),
        )

    def _queued(self, db, version, sid):
        row = db.execute("SELECT body FROM queues WHERE version=?", (version,)).fetchone()
        return next((r for r in json.loads(row["body"]) if r["solicitacao_id"] == sid), {}) if row else {}

    def history(self, sid):
        with self.db() as db:
            return [dict(r) for r in db.execute("SELECT * FROM events WHERE sid=? ORDER BY id DESC", (sid,))]

    def queue(self):
        self.purge_expired()
        with self.db() as db:
            row = db.execute("SELECT * FROM queues ORDER BY version DESC LIMIT 1").fetchone()
            version = db.execute("SELECT value FROM counters WHERE name='queue'").fetchone()[0]
        return (
            (row["version"], json.loads(row["body"]))
            if row and row["policy"] == POLICY_VERSION
            else (version, [])
        )

    def import_queue(self, rows, expected_version, actor="operador-demo"):
        rows = validate_queue(rows)
        self.purge_expired()
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            version = db.execute("SELECT value FROM counters WHERE name='queue'").fetchone()[0]
            if version != expected_version:
                raise ValueError("Versao da fila desatualizada")
            version += 1
            db.execute(
                "INSERT INTO queues(version,body,expires,policy) VALUES (?,?,?,?)",
                (version, json.dumps(rows), self.clock() + TTL, POLICY_VERSION),
            )
            db.execute(
                "UPDATE proposals SET status='desatualizada',error='Fila reimportada: nova proposta necessaria' "
                "WHERE status IN ('processando','aguardando_tribunal','tribunal_indisponivel','pronta_para_medico')"
            )
            db.execute("UPDATE counters SET value=? WHERE name='queue'", (version,))
            db.execute(
                "INSERT INTO queue_imports VALUES (?,?,?,?)",
                (version, actor, self.instant(), self.clock() + TTL),
            )
            entered = {r[0] for r in db.execute("SELECT sid FROM events WHERE tipo='entrada_na_fila'")}
            for row in rows:
                if row["solicitacao_id"] not in entered:
                    self._event(
                        db,
                        row["solicitacao_id"],
                        row.get("paciente_id"),
                        "entrada_na_fila",
                        actor,
                        "Entrou na fila de cirurgia.",
                    )
        return version

    def register_document(self, body, actor):
        self.purge_expired()
        _, queue = self.queue()
        row = next((r for r in queue if r["solicitacao_id"] == body["solicitacao_id"]), None)
        if row is None:
            raise ValueError("Solicitacao nao pertence a fila ativa")
        did = uuid4().hex
        with self.db() as db:
            db.execute(
                "INSERT INTO documents VALUES (?,?,?,?,?,?)",
                (did, body["solicitacao_id"], json.dumps(body), actor, self.instant(), self.clock() + TTL),
            )
            self._event(
                db,
                body["solicitacao_id"],
                row.get("paciente_id"),
                "documento_recebido",
                actor,
                "Documento recebido.",
            )
        return did

    def document(self, did):
        self.purge_expired()
        with self.db() as db:
            row = db.execute("SELECT * FROM documents WHERE id=?", (did,)).fetchone()
        if not row:
            raise KeyError(did)
        return dict(row) | {"body": json.loads(row["body"])}

    def register_evidence(self, body, actor):
        document = self.document(body["documento_id"])
        if body["pagina"] > document["body"]["paginas"]:
            raise ValueError("Pagina fora do documento")
        eid = body["evidencia"]["evidencia_id"]
        with self.db() as db:
            try:
                db.execute(
                    "INSERT INTO evidence(id,document_id,body,status,actor,expires) VALUES (?,?,?,?,?,?)",
                    (eid, body["documento_id"], json.dumps(body), "pendente", actor, document["expires"]),
                )
            except sqlite3.IntegrityError:
                raise ValueError("Identificador de evidencia ja registrado") from None
        return eid

    def evidence(self, eid):
        self.purge_expired()
        with self.db() as db:
            row = db.execute(
                "SELECT e.*,d.sid FROM evidence e JOIN documents d ON d.id=e.document_id WHERE e.id=?", (eid,)
            ).fetchone()
        if not row:
            raise KeyError(eid)
        return dict(row) | {"body": json.loads(row["body"])}

    def review_evidence(self, eid, action, actor, reason):
        row = self.evidence(eid)
        body = row["body"]
        if action == "aprovar" and (body["valor"] is None or body["confianca"] == "baixa"):
            raise ValueError(
                "Valor ausente ou de baixa confianca exige correcao documentada, nao aprovacao automatica"
            )
        with self.db() as db:
            result = db.execute(
                "UPDATE evidence SET status=?,reviewer=?,reason=?,reviewed_at=? WHERE id=? AND status='pendente' AND expires>?",
                (
                    "aprovada" if action == "aprovar" else "rejeitada",
                    actor,
                    reason,
                    self.instant(),
                    eid,
                    self.clock(),
                ),
            )
            if result.rowcount != 1:
                raise ValueError("Evidencia ja revisada ou expirada; registre nova versao para corrigir")
        return self.evidence(eid)

    def _approved(self, db, body):
        expires = self.clock() + TTL
        for incoming in body["evidencias"]:
            row = db.execute(
                "SELECT e.*,d.sid FROM evidence e JOIN documents d ON d.id=e.document_id WHERE e.id=? AND e.expires>? AND d.expires>?",
                (incoming["evidencia_id"], self.clock(), self.clock()),
            ).fetchone()
            if not row or row["status"] != "aprovada" or row["sid"] != body["solicitacao_id"]:
                raise EvidenceUnavailable("Evidencia inexistente, expirada, nao aprovada ou de outro caso")
            if json.loads(row["body"])["evidencia"] != incoming:
                raise EvidenceUnavailable("Evidencia difere do registro aprovado")
            expires = min(expires, row["expires"])
        return expires

    def approved_payload(self, eid, sid):
        row = self.evidence(eid)
        if row["status"] != "aprovada" or row["sid"] != sid:
            raise ValueError("Evidencia nao aprovada para esta solicitacao")
        return row["body"]["evidencia"]

    def create(self, body):
        self.purge_expired()
        pid = uuid4().hex
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            queue = db.execute("SELECT * FROM queues ORDER BY version DESC LIMIT 1").fetchone()
            if not queue or queue["policy"] != POLICY_VERSION or queue["version"] != body["versao_fila"]:
                raise ValueError("Versao da fila desatualizada")
            expiry = min(queue["expires"], self._approved(db, body))
            db.execute(
                "INSERT INTO proposals(id,body,status,created_at,expires) VALUES (?,?,?,?,?)",
                (pid, json.dumps(body), "aguardando_tribunal", self.instant(), expiry),
            )
        return pid

    def get(self, pid):
        self.purge_expired()
        with self.db() as db:
            row = db.execute("SELECT * FROM proposals WHERE id=?", (pid,)).fetchone()
        if not row:
            raise KeyError(pid)
        result = dict(row)
        result["body"] = json.loads(result["body"])
        result["opinion"] = json.loads(result["opinion"]) if result["opinion"] else None
        return result

    def live_evidence(self, body):
        self.purge_expired()
        with self.db() as db:
            self._approved(db, body)

    def claim(self, pid):
        self.purge_expired()
        with self.db() as db:
            result = db.execute(
                "UPDATE proposals SET status='processando' WHERE id=? AND expires>? AND status IN ('aguardando_tribunal','tribunal_indisponivel')",
                (pid, self.clock()),
            )
        return result.rowcount == 1

    def finish(self, pid, status, opinion=None, error=None, delay=0):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT body FROM proposals WHERE id=?", (pid,)).fetchone()
            current = db.execute("SELECT version,policy FROM queues ORDER BY version DESC LIMIT 1").fetchone()
            if row and (
                not current
                or current["policy"] != POLICY_VERSION
                or current["version"] != json.loads(row["body"])["versao_fila"]
            ):
                status, opinion, error = (
                    "desatualizada",
                    None,
                    "Fila ou politica mudou: nova proposta necessaria",
                )
            db.execute(
                "UPDATE proposals SET status=?,opinion=?,error=?,attempts=attempts+1,next_try=? WHERE id=? AND expires>? AND status='processando'",
                (
                    status,
                    json.dumps(opinion) if opinion is not None else None,
                    error,
                    self.clock() + delay,
                    pid,
                    self.clock(),
                ),
            )

    def due(self):
        self.purge_expired()
        with self.db() as db:
            return [
                r[0]
                for r in db.execute(
                    "SELECT id FROM proposals WHERE status IN ('aguardando_tribunal','tribunal_indisponivel') AND next_try<=? AND expires>? ORDER BY created_at LIMIT 5",
                    (self.clock(), self.clock()),
                )
            ]

    def decide(self, pid, actor, action, reason, rows=None):
        self.purge_expired()
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            p = db.execute("SELECT * FROM proposals WHERE id=? AND expires>?", (pid, self.clock())).fetchone()
            if not p or p["status"] != "pronta_para_medico":
                raise ValueError("Proposta nao esta pronta para decisao")
            body = json.loads(p["body"])
            version = db.execute("SELECT value FROM counters WHERE name='queue'").fetchone()[0]
            active = db.execute("SELECT policy FROM queues WHERE version=?", (version,)).fetchone()
            if not active or active["policy"] != POLICY_VERSION or version != body["versao_fila"]:
                raise ValueError("Fila mudou: nova analise necessaria")
            self._approved(db, body)
            sid = body["solicitacao_id"]
            before = self._queued(db, version, sid)
            if action == "aprovar":
                if not rows:
                    raise ValueError("Fila resultante ausente")
                db.execute(
                    "INSERT INTO queues(version,body,expires,policy) VALUES (?,?,?,?)",
                    (version + 1, json.dumps(validate_queue(rows)), p["expires"], POLICY_VERSION),
                )
                db.execute("UPDATE counters SET value=? WHERE name='queue'", (version + 1,))
                after = self._queued(db, version + 1, sid)
                kind = "posicao_alterada"
                text = f"Posição alterada de {before['posicao']}ª para {after['posicao']}ª após aprovação médica."
            elif action == "rejeitar":
                kind, text = "proposta_rejeitada", "A proposta de mudança não foi aprovada."
            else:
                kind, text = "informacao_solicitada", "O médico pediu mais informações."
            self._event(db, sid, before.get("paciente_id"), kind, actor, text, reason)
            db.execute(
                "INSERT INTO decisions(proposal_id,actor,action,reason,created_at,expires) VALUES (?,?,?,?,?,?)",
                (pid, actor, action, reason, self.instant(), p["expires"]),
            )
            db.execute("UPDATE proposals SET status=? WHERE id=?", (action, pid))
            return version + 1 if action == "aprovar" else version

    def cancel(self, pid, actor, reason):
        self.purge_expired()
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            p = db.execute("SELECT * FROM proposals WHERE id=? AND expires>?", (pid, self.clock())).fetchone()
            if not p or p["status"] in {"aprovar", "rejeitar", "pedir_informacoes", "cancelada"}:
                raise ValueError("Proposta ausente ou encerrada")
            db.execute(
                "UPDATE proposals SET status='cancelada',opinion=NULL,error='Cancelada pelo responsavel' WHERE id=?",
                (pid,),
            )
            db.execute(
                "INSERT INTO decisions(proposal_id,actor,action,reason,created_at,expires) VALUES (?,?,?,?,?,?)",
                (pid, actor, "cancelar", reason, self.instant(), p["expires"]),
            )
            body = json.loads(p["body"])
            row = self._queued(db, body["versao_fila"], body["solicitacao_id"])
            self._event(
                db,
                body["solicitacao_id"],
                row.get("paciente_id"),
                "proposta_cancelada",
                actor,
                "A proposta de mudança foi cancelada.",
                reason,
            )
