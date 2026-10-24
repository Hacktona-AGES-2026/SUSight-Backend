from __future__ import annotations

import hashlib
import hmac
import json
import secrets
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


class LoginRefused(ValueError):
    pass


class AccountLocked(ValueError):
    pass


# Spec 007: demonstration values.
SESSION_IDLE_SECONDS = 1800
MAX_ATTEMPTS = 5
LOCK_SECONDS = 900


def password_hash(password, salt):
    return hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1).hex()


# Spec 005: fixed, non-alarming texts; never document content, name or CNS.
EVENT_NOTICES = {
    "documento_recebido": [
        ("paciente", "documento_recebido", "Documento recebido", "Recebemos o seu documento.")
    ],
    "informacao_solicitada": [
        ("paciente", "exame_pedido", "Falta um exame", "O médico pediu um exame. Envie pela aba Documentos.")
    ],
    "posicao_alterada": [
        (
            "paciente",
            "posicao_alterada",
            "Sua posição mudou",
            "Sua posição na fila foi atualizada após revisão médica.",
        ),
        (
            "profissional",
            "fila_atualizada",
            "Fila aprovada e atualizada",
            "Uma mudança de posição foi aprovada.",
        ),
    ],
    "reavaliacao_concluida": [
        (
            "paciente",
            "reavaliacao_concluida",
            "Reavaliação concluída",
            "A reavaliação da sua solicitação terminou.",
        )
    ],
    "exame_recebido": [
        (
            "profissional",
            "paciente_respondeu",
            "Paciente respondeu ao pedido",
            "O paciente enviou o exame pedido.",
        )
    ],
}
OPTIONAL_NOTICES = ("documento_recebido", "analise_concluida", "prioridade_validada")


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
            -- Requested exams (spec 006): like the trail, never expire and hold only names.
            CREATE TABLE IF NOT EXISTS exam_requests(id TEXT PRIMARY KEY, sid TEXT NOT NULL, paciente_id TEXT,
              proposal_id TEXT NOT NULL, exame TEXT NOT NULL, explicacao TEXT NOT NULL, actor TEXT NOT NULL,
              created_at TEXT NOT NULL, status TEXT NOT NULL, document_id TEXT, updated_at TEXT NOT NULL);
            -- Disputes and export log (spec 008): audit records, never expire, no CSV content.
            CREATE TABLE IF NOT EXISTS disputes(id INTEGER PRIMARY KEY, sid TEXT NOT NULL, paciente_id TEXT,
              actor TEXT NOT NULL, motivo TEXT NOT NULL, created_at TEXT NOT NULL, status TEXT NOT NULL,
              resultado TEXT, justificativa TEXT, concluded_at TEXT);
            CREATE TABLE IF NOT EXISTS exports(id INTEGER PRIMARY KEY, actor TEXT NOT NULL, created_at TEXT NOT NULL,
              versao_fila INTEGER NOT NULL, linhas INTEGER NOT NULL);
            -- Notifications, preferences, contacts and devices (spec 005); no expiry, no document content.
            CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY, publico TEXT NOT NULL, paciente_id TEXT,
              sid TEXT NOT NULL, tipo TEXT NOT NULL, titulo TEXT NOT NULL, texto TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS notification_reads(notification_id INTEGER NOT NULL, leitor TEXT NOT NULL,
              PRIMARY KEY(notification_id, leitor));
            CREATE TABLE IF NOT EXISTS notification_prefs(paciente_id TEXT NOT NULL, tipo TEXT NOT NULL,
              ativo INTEGER NOT NULL, PRIMARY KEY(paciente_id, tipo));
            CREATE TABLE IF NOT EXISTS contacts(id INTEGER PRIMARY KEY, paciente_id TEXT NOT NULL, nome TEXT NOT NULL,
              parentesco TEXT NOT NULL, telefone TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS devices(id INTEGER PRIMARY KEY, principal_id TEXT NOT NULL, paciente_id TEXT,
              plataforma TEXT NOT NULL, token TEXT NOT NULL, created_at TEXT NOT NULL);
            -- Accounts and sessions (spec 007): scrypt password hash, session token stored as SHA-256 only.
            CREATE TABLE IF NOT EXISTS accounts(id TEXT PRIMARY KEY, papel TEXT NOT NULL, pacientes TEXT NOT NULL,
              senha_hash TEXT NOT NULL, sal TEXT NOT NULL, tentativas INTEGER NOT NULL DEFAULT 0,
              bloqueado_ate REAL NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions(token_sha256 TEXT PRIMARY KEY, account_id TEXT NOT NULL,
              created_at TEXT NOT NULL, last_seen REAL NOT NULL);
            -- Extraction (spec 001): file and derivatives expire with the document.
            CREATE TABLE IF NOT EXISTS consents(id INTEGER PRIMARY KEY, document_id TEXT NOT NULL,
              termo_versao TEXT NOT NULL, actor TEXT NOT NULL, accepted_at TEXT NOT NULL, expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS document_files(document_id TEXT PRIMARY KEY, mime TEXT NOT NULL,
              conteudo BLOB NOT NULL, expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS extractions(document_id TEXT PRIMARY KEY, situacao TEXT NOT NULL,
              avisos TEXT NOT NULL, updated_at TEXT NOT NULL, expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS extraction_fields(id INTEGER PRIMARY KEY, document_id TEXT NOT NULL,
              campo TEXT NOT NULL, valor_extraido TEXT, situacao TEXT NOT NULL, confianca TEXT,
              requer_revisao INTEGER NOT NULL, evidencias TEXT NOT NULL, expires REAL NOT NULL,
              UNIQUE(document_id, campo));
            CREATE TABLE IF NOT EXISTS field_reviews(id INTEGER PRIMARY KEY, field_id INTEGER NOT NULL,
              reviewer TEXT NOT NULL, acao TEXT NOT NULL, valor_corrigido TEXT, justificativa TEXT NOT NULL,
              reviewed_at TEXT NOT NULL, expires REAL NOT NULL);
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
            for table in ["consents", "document_files", "extractions", "extraction_fields"]:
                db.execute(
                    f"DELETE FROM {table} WHERE expires<=? OR document_id NOT IN (SELECT id FROM documents)",
                    (now,),
                )
            db.execute(
                "DELETE FROM field_reviews WHERE expires<=? OR field_id NOT IN (SELECT id FROM extraction_fields)",
                (now,),
            )
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
            db.execute("DELETE FROM sessions WHERE last_seen<?", (now - SESSION_IDLE_SECONDS,))

    def provision_account(self, aid, role, patients, password):
        if role not in {"admin", "medico", "paciente"} or (role == "paciente" and len(patients) != 1):
            raise ValueError("Conta invalida")
        salt = secrets.token_bytes(16)
        with self.db() as db:
            try:
                db.execute(
                    "INSERT INTO accounts(id,papel,pacientes,senha_hash,sal,created_at) VALUES (?,?,?,?,?,?)",
                    (
                        aid,
                        role,
                        json.dumps(sorted(patients)),
                        password_hash(password, salt),
                        salt.hex(),
                        self.instant(),
                    ),
                )
            except sqlite3.IntegrityError:
                raise ValueError("Conta ja existe") from None

    def login(self, aid, password):
        now, token, outcome = self.clock(), None, LoginRefused
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM accounts WHERE id=?", (aid,)).fetchone()
            if row is None:
                password_hash(password, b"\0" * 16)  # same work as a real check
            elif row["bloqueado_ate"] > now:
                outcome = AccountLocked
            elif hmac.compare_digest(row["senha_hash"], password_hash(password, bytes.fromhex(row["sal"]))):
                db.execute("UPDATE accounts SET tentativas=0,bloqueado_ate=0 WHERE id=?", (aid,))
                token = secrets.token_urlsafe(32)
                db.execute(
                    "INSERT INTO sessions VALUES (?,?,?,?)",
                    (hashlib.sha256(token.encode()).hexdigest(), aid, self.instant(), now),
                )
            else:
                attempts = row["tentativas"] + 1
                locked = attempts >= MAX_ATTEMPTS
                db.execute(
                    "UPDATE accounts SET tentativas=?,bloqueado_ate=? WHERE id=?",
                    (0 if locked else attempts, now + LOCK_SECONDS if locked else 0, aid),
                )
        # Raise only after the attempt counter is committed.
        if token is None:
            raise outcome("Acesso recusado")
        return {"token": token, "papel": row["papel"]}

    def session(self, token):
        digest, now = hashlib.sha256(token.encode()).hexdigest(), self.clock()
        with self.db() as db:
            row = db.execute(
                "SELECT s.last_seen,a.id,a.papel,a.pacientes FROM sessions s JOIN accounts a ON a.id=s.account_id"
                " WHERE s.token_sha256=?",
                (digest,),
            ).fetchone()
            if row is None:
                return None
            if now - row["last_seen"] > SESSION_IDLE_SECONDS:
                db.execute("DELETE FROM sessions WHERE token_sha256=?", (digest,))
                return None
            db.execute("UPDATE sessions SET last_seen=? WHERE token_sha256=?", (now, digest))
        return {"id": row["id"], "papel": row["papel"], "pacientes": json.loads(row["pacientes"])}

    def logout(self, token):
        digest = hashlib.sha256(token.encode()).hexdigest()
        with self.db() as db:
            row = db.execute("SELECT account_id FROM sessions WHERE token_sha256=?", (digest,)).fetchone()
            if row is None:
                return None
            db.execute("DELETE FROM sessions WHERE token_sha256=?", (digest,))
            db.execute("DELETE FROM devices WHERE principal_id=?", (row["account_id"],))
        return row["account_id"]

    def _event(self, db, sid, patient, kind, actor, text, reason=None):
        db.execute(
            "INSERT INTO events(sid,paciente_id,tipo,actor,texto,motivo,created_at) VALUES (?,?,?,?,?,?,?)",
            (sid, patient, kind, actor, text, reason or None, self.instant()),
        )
        for notice in EVENT_NOTICES.get(kind, []):
            self._notify(db, sid, patient, *notice)

    def _notify(self, db, sid, patient, audience, kind, title, text):
        if audience == "paciente" and kind in OPTIONAL_NOTICES:
            pref = db.execute(
                "SELECT ativo FROM notification_prefs WHERE paciente_id=? AND tipo=?", (patient, kind)
            ).fetchone()
            if pref is not None and not pref["ativo"]:
                return
        db.execute(
            "INSERT INTO notifications(publico,paciente_id,sid,tipo,titulo,texto,created_at) VALUES (?,?,?,?,?,?,?)",
            (audience, patient, sid, kind, title, text, self.instant()),
        )

    def _patient_of(self, db, sid):
        row = db.execute(
            "SELECT paciente_id FROM events WHERE sid=? AND paciente_id IS NOT NULL ORDER BY id LIMIT 1",
            (sid,),
        ).fetchone()
        return row["paciente_id"] if row else None

    def notifications(self, audience, patients, reader):
        """`patients=None` means every patient (admin)."""
        with self.db() as db:
            rows = db.execute(
                "SELECT n.*, EXISTS(SELECT 1 FROM notification_reads r WHERE r.notification_id=n.id AND r.leitor=?)"
                " AS lida FROM notifications n WHERE publico=? ORDER BY id DESC",
                (reader, audience),
            )
            return [dict(r) for r in rows if patients is None or r["paciente_id"] in patients]

    def mark_read(self, nid, audience, patients, reader):
        if not any(n["id"] == nid for n in self.notifications(audience, patients, reader)):
            return False
        with self.db() as db:
            db.execute("INSERT OR IGNORE INTO notification_reads VALUES (?,?)", (nid, reader))
        return True

    def preferences(self, patient):
        with self.db() as db:
            stored = {
                r["tipo"]: bool(r["ativo"])
                for r in db.execute(
                    "SELECT tipo,ativo FROM notification_prefs WHERE paciente_id=?", (patient,)
                )
            }
        return {kind: stored.get(kind, True) for kind in OPTIONAL_NOTICES}

    def set_preferences(self, patient, values):
        with self.db() as db:
            for kind, active in values.items():
                db.execute(
                    "INSERT INTO notification_prefs VALUES (?,?,?) ON CONFLICT(paciente_id,tipo) DO UPDATE SET ativo=?",
                    (patient, kind, int(active), int(active)),
                )
        return self.preferences(patient)

    def add_contact(self, patient, body):
        with self.db() as db:
            return db.execute(
                "INSERT INTO contacts(paciente_id,nome,parentesco,telefone,created_at) VALUES (?,?,?,?,?)",
                (patient, body["nome"], body["parentesco"], body["telefone"], self.instant()),
            ).lastrowid

    def contacts(self, patient):
        with self.db() as db:
            return [
                dict(r)
                for r in db.execute("SELECT * FROM contacts WHERE paciente_id=? ORDER BY id", (patient,))
            ]

    def delete_contact(self, patient, cid):
        with self.db() as db:
            return (
                db.execute("DELETE FROM contacts WHERE id=? AND paciente_id=?", (cid, patient)).rowcount == 1
            )

    def add_device(self, principal, patient, body):
        with self.db() as db:
            return db.execute(
                "INSERT INTO devices(principal_id,paciente_id,plataforma,token,created_at) VALUES (?,?,?,?,?)",
                (principal, patient, body["plataforma"], body["token"], self.instant()),
            ).lastrowid

    def devices(self, principal):
        with self.db() as db:
            return [
                dict(r)
                for r in db.execute("SELECT * FROM devices WHERE principal_id=? ORDER BY id", (principal,))
            ]

    def delete_device(self, principal, did):
        with self.db() as db:
            return (
                db.execute("DELETE FROM devices WHERE id=? AND principal_id=?", (did, principal)).rowcount
                == 1
            )

    def _queued(self, db, version, sid):
        row = db.execute("SELECT body FROM queues WHERE version=?", (version,)).fetchone()
        return next((r for r in json.loads(row["body"]) if r["solicitacao_id"] == sid), {}) if row else {}

    def open_dispute(self, sid, patient, actor, reason):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute(
                "SELECT 1 FROM disputes WHERE sid=? AND status='em_reavaliacao'", (sid,)
            ).fetchone():
                raise ValueError("Solicitacao ja esta em reavaliacao")
            db.execute(
                "INSERT INTO disputes(sid,paciente_id,actor,motivo,created_at,status) VALUES (?,?,?,?,?,?)",
                (sid, patient, actor, reason, self.instant(), "em_reavaliacao"),
            )
            self._event(
                db,
                sid,
                patient,
                "contestacao",
                actor,
                "Posição contestada; solicitação em reavaliação.",
                reason,
            )

    def _conclude_dispute(self, db, sid, actor, result, justification=None):
        row = db.execute("SELECT * FROM disputes WHERE sid=? AND status='em_reavaliacao'", (sid,)).fetchone()
        if row is None:
            return False
        db.execute(
            "UPDATE disputes SET status='concluida',resultado=?,justificativa=?,concluded_at=? WHERE id=?",
            (result, justification, self.instant(), row["id"]),
        )
        text = {
            "nova_proposta": "Reavaliação concluída: nova proposta enviada para análise.",
            "posicao_mantida": "Reavaliação concluída: posição mantida.",
        }[result]
        self._event(db, sid, row["paciente_id"], "reavaliacao_concluida", actor, text, justification)
        return True

    def conclude_dispute(self, sid, actor, justification):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            if not self._conclude_dispute(db, sid, actor, "posicao_mantida", justification):
                raise ValueError("Nao ha contestacao em reavaliacao")

    def disputed(self):
        with self.db() as db:
            return {r[0] for r in db.execute("SELECT sid FROM disputes WHERE status='em_reavaliacao'")}

    def log_export(self, actor, version, lines):
        with self.db() as db:
            db.execute(
                "INSERT INTO exports(actor,created_at,versao_fila,linhas) VALUES (?,?,?,?)",
                (actor, self.instant(), version, lines),
            )

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

    def register_document(self, body, actor, file=None, term_version=None):
        """`file=(bytes, mime)` and `term_version` come from the upload route (spec 001)."""
        self.purge_expired()
        _, queue = self.queue()
        row = next((r for r in queue if r["solicitacao_id"] == body["solicitacao_id"]), None)
        if row is None:
            raise ValueError("Solicitacao nao pertence a fila ativa")
        did = uuid4().hex
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            request = None
            if body.get("pedido_id"):
                request = db.execute(
                    "SELECT * FROM exam_requests WHERE id=? AND sid=? AND status='pendente'",
                    (body["pedido_id"], body["solicitacao_id"]),
                ).fetchone()
                if request is None:
                    raise ValueError("Pedido inexistente, de outra solicitacao ou ja respondido")
            expires = self.clock() + TTL
            db.execute(
                "INSERT INTO documents VALUES (?,?,?,?,?,?)",
                (did, body["solicitacao_id"], json.dumps(body), actor, self.instant(), expires),
            )
            if file is not None:
                db.execute("INSERT INTO document_files VALUES (?,?,?,?)", (did, file[1], file[0], expires))
                db.execute(
                    "INSERT INTO consents(document_id,termo_versao,actor,accepted_at,expires) VALUES (?,?,?,?,?)",
                    (did, term_version, actor, self.instant(), expires),
                )
            self._event(
                db,
                body["solicitacao_id"],
                row.get("paciente_id"),
                "documento_recebido",
                actor,
                "Documento recebido.",
            )
            if request is not None:
                db.execute(
                    "UPDATE exam_requests SET status='recebido',document_id=?,updated_at=? WHERE id=?",
                    (did, self.instant(), request["id"]),
                )
                self._event(
                    db,
                    body["solicitacao_id"],
                    row.get("paciente_id"),
                    "exame_recebido",
                    actor,
                    f"Exame pedido recebido: {request['exame']}.",
                )
        return did

    def document_file(self, did):
        with self.db() as db:
            row = db.execute(
                "SELECT conteudo,mime FROM document_files WHERE document_id=? AND expires>?",
                (did, self.clock()),
            ).fetchone()
        return (bytes(row["conteudo"]), row["mime"]) if row else None

    def save_extraction(self, did, status, warnings, fields):
        """Replace the extraction of a document; the extracted value is never edited afterwards."""
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            doc = db.execute("SELECT expires FROM documents WHERE id=?", (did,)).fetchone()
            if doc is None:
                raise KeyError(did)
            old = [r[0] for r in db.execute("SELECT id FROM extraction_fields WHERE document_id=?", (did,))]
            db.executemany("DELETE FROM field_reviews WHERE field_id=?", [(i,) for i in old])
            db.execute("DELETE FROM extraction_fields WHERE document_id=?", (did,))
            db.execute(
                "INSERT OR REPLACE INTO extractions VALUES (?,?,?,?,?)",
                (did, status, json.dumps(warnings), self.instant(), doc["expires"]),
            )
            for name, item in fields.items():
                db.execute(
                    "INSERT INTO extraction_fields(document_id,campo,valor_extraido,situacao,confianca,requer_revisao,"
                    "evidencias,expires) VALUES (?,?,?,?,?,?,?,?)",
                    (
                        did,
                        name,
                        json.dumps(item["valor_extraido"], ensure_ascii=False),
                        item["situacao"],
                        item["confianca"],
                        int(item["requer_revisao"]),
                        json.dumps(item["evidencias"], ensure_ascii=False),
                        doc["expires"],
                    ),
                )

    def extraction(self, did):
        self.purge_expired()
        with self.db() as db:
            head = db.execute("SELECT * FROM extractions WHERE document_id=?", (did,)).fetchone()
            if head is None:
                return None
            fields = {}
            for row in db.execute("SELECT * FROM extraction_fields WHERE document_id=? ORDER BY id", (did,)):
                review = db.execute(
                    "SELECT * FROM field_reviews WHERE field_id=? ORDER BY id DESC LIMIT 1", (row["id"],)
                ).fetchone()
                fields[row["campo"]] = {
                    "valor_extraido": json.loads(row["valor_extraido"]),
                    "situacao": row["situacao"],
                    "confianca": row["confianca"],
                    "requer_revisao": bool(row["requer_revisao"]),
                    "evidencias": json.loads(row["evidencias"]),
                    "revisao": {
                        "acao": review["acao"],
                        "valor_corrigido": json.loads(review["valor_corrigido"]),
                        "justificativa": review["justificativa"],
                        "revisor": review["reviewer"],
                        "data_hora": review["reviewed_at"],
                    }
                    if review
                    else None,
                }
        return {"situacao": head["situacao"], "avisos": json.loads(head["avisos"]), "campos": fields}

    def review_field(self, did, name, actor, action, corrected, reason):
        with self.db() as db:
            row = db.execute(
                "SELECT * FROM extraction_fields WHERE document_id=? AND campo=? AND expires>?",
                (did, name, self.clock()),
            ).fetchone()
            if row is None:
                raise KeyError(name)
            if action == "aprovar" and json.loads(row["valor_extraido"]) is None:
                raise ValueError("Campo sem valor extraido: corrija com valor ou rejeite")
            db.execute(
                "INSERT INTO field_reviews(field_id,reviewer,acao,valor_corrigido,justificativa,reviewed_at,expires)"
                " VALUES (?,?,?,?,?,?,?)",
                (
                    row["id"],
                    actor,
                    action,
                    json.dumps(corrected, ensure_ascii=False),
                    reason,
                    self.instant(),
                    row["expires"],
                ),
            )

    def _advance_request(self, db, document_id, old, new):
        db.execute(
            "UPDATE exam_requests SET status=?,updated_at=? WHERE document_id=? AND status=?",
            (new, self.instant(), document_id, old),
        )

    def exam_requests(self, sid):
        with self.db() as db:
            return [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM exam_requests WHERE sid=? ORDER BY created_at DESC, rowid DESC", (sid,)
                )
            ]

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
            self._advance_request(db, body["documento_id"], "recebido", "em_analise")
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
            self._advance_request(db, row["document_id"], "em_analise", "atendido")
            self._notify(
                db,
                row["sid"],
                self._patient_of(db, row["sid"]),
                "paciente",
                "analise_concluida",
                "Análise do documento concluída",
                "A análise do seu documento terminou.",
            )
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

    def create(self, body, actor="sistema"):
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
            self._conclude_dispute(db, body["solicitacao_id"], actor, "nova_proposta")
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

    @staticmethod
    def _summary(proposal, row):
        body, opinion = json.loads(proposal["body"]), proposal["opinion"]
        return {
            "proposta_id": proposal["id"],
            "solicitacao_id": body["solicitacao_id"],
            "situacao": proposal["status"],
            "posicao_atual": row.get("posicao"),
            "posicao_proposta": body["posicao_proposta"],
            "recomendacao": json.loads(opinion)["recomendacao"] if opinion else None,
            "ordenacao_incerta": body["ordenacao_incerta"],
            "evidencias_conflitantes": body["evidencias_conflitantes"],
            "criada_em": proposal["created_at"],
        }

    def list_proposals(self, statuses, patients):
        """Read-only listing for review (spec 009); `patients=None` means every case (admin)."""
        _, queue = self.queue()
        rows = {r["solicitacao_id"]: r for r in queue}
        marks = ",".join("?" * len(statuses))
        listed = []
        with self.db() as db:
            found = db.execute(
                f"SELECT * FROM proposals WHERE expires>? AND status IN ({marks}) ORDER BY created_at, rowid",
                (self.clock(), *statuses),
            ).fetchall()
            for proposal in found:
                sid = json.loads(proposal["body"])["solicitacao_id"]
                row = rows.get(sid, {})
                patient = row.get("paciente_id") or self._patient_of(db, sid)
                if patients is None or patient in patients:
                    listed.append(self._summary(proposal, row))
        return listed

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
            updated = db.execute(
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
            if updated.rowcount == 1 and status == "pronta_para_medico":
                sid = json.loads(row["body"])["solicitacao_id"]
                self._notify(
                    db,
                    sid,
                    self._patient_of(db, sid),
                    "profissional",
                    "proposta_para_revisao",
                    "Nova proposta para revisão",
                    "Uma proposta com parecer do tribunal aguarda sua decisão.",
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

    def decide(self, pid, actor, action, reason, rows=None, exams=()):
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
                if not exams:
                    raise ValueError("Pedir informacoes exige ao menos um exame")
                kind = "informacao_solicitada"
                text = "O médico pediu mais informações: " + ", ".join(e["exame"] for e in exams) + "."
                for exam in exams:
                    db.execute(
                        "INSERT INTO exam_requests VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            uuid4().hex,
                            sid,
                            before.get("paciente_id"),
                            pid,
                            exam["exame"],
                            exam.get("explicacao", ""),
                            actor,
                            self.instant(),
                            "pendente",
                            None,
                            self.instant(),
                        ),
                    )
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
