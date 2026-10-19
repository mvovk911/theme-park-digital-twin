"""Bounded durable proposals and execution intent, in an independent database."""
import json
from pathlib import Path
import sqlite3
import threading
from .contracts import WorkflowError

MAX_PROPOSALS = 256
MAX_BYTES = 16 * 1024 * 1024
MAX_RECORD_BYTES = 64 * 1024


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


class WorkflowStore:
    def __init__(self, path, max_proposals=MAX_PROPOSALS, max_bytes=MAX_BYTES):
        if type(max_proposals) is not int or not 1 <= max_proposals <= MAX_PROPOSALS or type(max_bytes) is not int or not 1 <= max_bytes <= MAX_BYTES:
            raise ValueError("Workflow retention exceeds supported bounds")
        self.max_proposals, self.max_bytes = max_proposals, max_bytes
        self.lock = threading.RLock()
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        tables = {r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if tables - {"workflow_proposals"}:
            self.db.close()
            raise ValueError("Workflow store refuses a database with foreign tables")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("CREATE TABLE IF NOT EXISTS workflow_proposals(proposal_id TEXT PRIMARY KEY,create_request_id TEXT UNIQUE NOT NULL,create_payload TEXT NOT NULL,body TEXT NOT NULL,execution_request_id TEXT UNIQUE)")
        self.db.commit()

    def close(self):
        with self.lock:
            self.db.close()

    def by_request(self, request_id, payload):
        with self.lock:
            row = self.db.execute("SELECT * FROM workflow_proposals WHERE create_request_id=?", (request_id,)).fetchone()
        if row and row["create_payload"] != encoded(payload):
            raise WorkflowError("proposal_request_conflict", "Create request ID was already used for different proposal inputs")
        return json.loads(row["body"]) if row else None

    def get(self, ident):
        with self.lock:
            row = self.db.execute("SELECT body FROM workflow_proposals WHERE proposal_id=?", (ident,)).fetchone()
        if row is None:
            raise WorkflowError("proposal_not_found", "Unknown workflow proposal", 404)
        return json.loads(row["body"])

    def _check_size(self, body, replacing=None):
        size = len(body.encode())
        if size > MAX_RECORD_BYTES:
            raise WorkflowError("proposal_too_large", "Workflow proposal exceeds 64 KiB", 413)
        count, total = self.db.execute("SELECT COUNT(*),COALESCE(SUM(length(CAST(body AS BLOB))),0) FROM workflow_proposals").fetchone()
        previous_size = 0
        if replacing:
            row = self.db.execute("SELECT length(CAST(body AS BLOB)) FROM workflow_proposals WHERE proposal_id=?", (replacing,)).fetchone()
            previous_size = row[0] if row else 0
        if (not replacing and count >= self.max_proposals) or total - previous_size + size > self.max_bytes:
            raise WorkflowError("workflow_store_full", "Workflow retention cap reached; no proposals were evicted")

    def create(self, proposal, request_id, payload):
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                body = encoded(proposal)
                self._check_size(body)
                self.db.execute("INSERT INTO workflow_proposals VALUES (?,?,?,?,NULL)", (proposal["id"], request_id, encoded(payload), body))
                self.db.commit()
            except BaseException:
                self.db.rollback()
                raise
        return proposal

    def update(self, proposal):
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                body = encoded(proposal)
                self._check_size(body, replacing=proposal["id"])
                self.db.execute("UPDATE workflow_proposals SET body=?,execution_request_id=? WHERE proposal_id=?", (body, proposal.get("execution_request_id"), proposal["id"]))
                self.db.commit()
            except sqlite3.IntegrityError as exc:
                self.db.rollback()
                raise WorkflowError("execution_request_conflict", "Execution request ID already belongs to another proposal") from exc
            except BaseException:
                self.db.rollback()
                raise
        return proposal

    def list(self, limit=100, offset=0):
        with self.lock:
            rows = self.db.execute("SELECT body FROM workflow_proposals ORDER BY rowid DESC LIMIT ? OFFSET ?", (limit, offset)).fetchall()
            count = self.db.execute("SELECT COUNT(*) FROM workflow_proposals").fetchone()[0]
        return {"items": [json.loads(r[0]) for r in rows], "total": count,
                "retention": {"max_proposals": self.max_proposals, "max_body_bytes": self.max_bytes, "automatic_eviction": False}}
