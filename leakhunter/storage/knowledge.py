"""SQLite knowledge bank: immutable run artifacts, mutable pointers and annotations."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def encoded(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def policy_digest(raw: dict) -> str:
    return hashlib.sha256(encoded({k: v for k, v in raw.items() if k not in {"status", "approved_by"}}).encode()).hexdigest()


class KnowledgeBank:
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "knowledge.sqlite3"
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS policies (
                    version TEXT PRIMARY KEY, digest TEXT NOT NULL, payload TEXT NOT NULL,
                    status TEXT NOT NULL, approved_by TEXT, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS snapshots (
                    id TEXT PRIMARY KEY, revision TEXT NOT NULL, parent_id TEXT REFERENCES snapshots(id),
                    branch TEXT NOT NULL, created_at TEXT NOT NULL, digest TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS pointers (branch TEXT PRIMARY KEY, snapshot_id TEXT NOT NULL REFERENCES snapshots(id));
                CREATE TABLE IF NOT EXISTS annotations (
                    kind TEXT NOT NULL, id TEXT NOT NULL, payload TEXT, PRIMARY KEY(kind,id));
                CREATE TABLE IF NOT EXISTS metrics (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS repairs (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS evaluations (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS facts (
                    snapshot_id TEXT NOT NULL REFERENCES snapshots(id), relation TEXT NOT NULL,
                    id TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(snapshot_id,relation,id));
                CREATE INDEX IF NOT EXISTS facts_relation ON facts(relation,snapshot_id);
                CREATE TRIGGER IF NOT EXISTS snapshots_no_update BEFORE UPDATE ON snapshots
                    BEGIN SELECT RAISE(ABORT,'Snapshots are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS snapshots_no_delete BEFORE DELETE ON snapshots
                    BEGIN SELECT RAISE(ABORT,'Snapshots are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS facts_no_update BEFORE UPDATE ON facts
                    BEGIN SELECT RAISE(ABORT,'Snapshot facts are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS facts_no_delete BEFORE DELETE ON facts
                    BEGIN SELECT RAISE(ABORT,'Snapshot facts are immutable'); END;
            """)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def register_policy(self, raw: dict, *, approve_by: str | None = None) -> dict:
        version, digest = str(raw["version"]), policy_digest(raw)
        status = "approved" if approve_by else raw.get("status", "draft")
        actor = approve_by or raw.get("approved_by")
        if status == "approved" and (not isinstance(actor, str) or not actor.strip()):
            raise ValueError("Approved policies require a named approved_by operator")
        if approve_by is not None and (not isinstance(approve_by, str) or not approve_by.strip()):
            raise ValueError("Approval requires approved_by")
        with self.connect() as db:
            existing = db.execute("SELECT * FROM policies WHERE version=?", (version,)).fetchone()
            if existing and existing["digest"] != digest:
                raise ValueError("Policy content changed without a new version")
            if existing and not approve_by and status != "retired":
                return self._policy(existing)
            if existing and existing["status"] == "retired" and status != "retired":
                raise ValueError("Retired policy versions cannot be approved again")
            if existing:
                db.execute("UPDATE policies SET status=?,approved_by=? WHERE version=?", (status, actor, version))
            else:
                db.execute("INSERT INTO policies VALUES(?,?,?,?,?,?)", (version, digest, encoded(raw), status, actor, now()))
            return self._policy(db.execute("SELECT * FROM policies WHERE version=?", (version,)).fetchone())

    @staticmethod
    def _policy(row) -> dict:
        return {"version": row["version"], "digest": row["digest"], "policy": json.loads(row["payload"]),
                "status": row["status"], "approved_by": row["approved_by"], "created_at": row["created_at"]}

    def policies(self) -> list[dict]:
        with self.connect() as db:
            return [self._policy(row) for row in db.execute("SELECT * FROM policies ORDER BY created_at DESC")]

    def snapshot(self, ident: str | None = None, branch: str = "main") -> dict | None:
        with self.connect() as db:
            if ident is None:
                row = db.execute("SELECT s.* FROM snapshots s JOIN pointers p ON p.snapshot_id=s.id WHERE p.branch=?", (branch,)).fetchone()
            else:
                row = db.execute("SELECT * FROM snapshots WHERE id=?", (ident,)).fetchone()
            if row is None:
                return None
            payload = row["payload"]
            if hashlib.sha256(payload.encode()).hexdigest() != row["digest"]:
                raise ValueError("Snapshot integrity check failed")
            return json.loads(payload)

    def snapshots(self) -> list[dict]:
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT id,revision,parent_id,branch,created_at,digest FROM snapshots ORDER BY rowid DESC LIMIT 100")]

    def save_snapshot(self, value: dict, branch: str = "main", parent_id: str | None = None) -> dict:
        snapshot = dict(value, snapshot_id=uuid.uuid4().hex, branch=branch, parent_id=parent_id, created_at=now())
        payload = encoded(snapshot)
        digest = hashlib.sha256(payload.encode()).hexdigest()
        facts = []
        for relation, items in (("symbols", snapshot.get("nodes", [])), ("flow_paths", snapshot.get("edges", [])),
                                ("findings", snapshot.get("findings", []))):
            for item in items:
                facts.append((snapshot["snapshot_id"], relation, item["id"], encoded(item)))
        for finding in snapshot.get("findings", []):
            evidence = finding.get("runtime_evidence", {"status": "NOT_RUN", "observed": False})
            facts.append((snapshot["snapshot_id"], "evidence", finding["id"], encoded(evidence)))
        for file, metadata in snapshot.get("index", {}).get("files", {}).items():
            facts.append((snapshot["snapshot_id"], "analysis_dependencies", file, encoded(metadata)))
        with self.connect() as db:
            db.execute("INSERT INTO snapshots VALUES(?,?,?,?,?,?,?)", (snapshot["snapshot_id"], snapshot.get("revision_sha", ""), parent_id, branch, snapshot["created_at"], digest, payload))
            db.executemany("INSERT INTO facts VALUES(?,?,?,?)", facts)
            db.execute("INSERT INTO pointers VALUES(?,?) ON CONFLICT(branch) DO UPDATE SET snapshot_id=excluded.snapshot_id", (branch, snapshot["snapshot_id"]))
        return snapshot

    def graph(self) -> dict:
        snapshot = self.snapshot() or {"nodes": [], "edges": [], "findings": []}
        value = dict(snapshot)
        nodes = {item["id"]: item for item in snapshot.get("nodes", [])}
        edges = {item["id"]: item for item in snapshot.get("edges", [])}
        with self.connect() as db:
            for row in db.execute("SELECT * FROM annotations ORDER BY rowid"):
                target = nodes if row["kind"] == "nodes" else edges
                if row["payload"] is None:
                    target.pop(row["id"], None)
                else:
                    target[row["id"]] = json.loads(row["payload"])
        value["nodes"] = list(nodes.values())
        value["edges"] = [edge for edge in edges.values() if edge["source"] in nodes and edge["target"] in nodes]
        return value

    def mutate(self, kind: str, action: str, item: dict | None = None, ident: str | None = None) -> dict:
        if kind not in {"nodes", "edges"}:
            raise ValueError("Unknown knowledge collection")
        graph = self.graph()
        existing = {record["id"]: record for record in graph[kind]}
        item = dict(item or {})
        ident = ident or item.get("id") or f"user-{uuid.uuid4().hex}"
        if not isinstance(ident, str) or not ident or len(ident) > 500:
            raise ValueError("Invalid record id")
        if action != "create" and ident not in existing:
            raise KeyError(ident)
        if action == "create" and ident in existing:
            raise FileExistsError("Record id already exists")
        if "id" in item and item["id"] != ident:
            raise ValueError("Record id cannot change")
        if action == "update":
            item = dict(existing[ident], **item)
        item["id"] = ident
        if action != "delete":
            required = ("label", "kind") if kind == "nodes" else ("source", "target", "type")
            if any(not isinstance(item.get(key), str) or not item[key].strip() for key in required):
                raise ValueError("Required nonempty strings: " + ", ".join(required))
            if kind == "edges":
                node_ids = {node["id"] for node in graph["nodes"]}
                if item["source"] not in node_ids or item["target"] not in node_ids:
                    raise ValueError("Edge endpoints must refer to existing nodes")
            encoded(item)
        with self.connect() as db:
            db.execute("INSERT INTO annotations VALUES(?,?,?) ON CONFLICT(kind,id) DO UPDATE SET payload=excluded.payload", (kind, ident, None if action == "delete" else encoded(item)))
            if kind == "nodes" and action == "delete":
                for edge in graph["edges"]:
                    if ident in {edge["source"], edge["target"]}:
                        db.execute("INSERT INTO annotations VALUES('edges',?,NULL) ON CONFLICT(kind,id) DO UPDATE SET payload=NULL", (edge["id"],))
        return {"ok": True, "id": ident} if action == "delete" else item

    def append(self, collection: str, value: dict) -> dict:
        if collection not in {"metrics", "repairs", "evaluations"}:
            raise ValueError("Unknown artifact collection")
        value = dict(value)
        value.setdefault("id", uuid.uuid4().hex)
        value.setdefault("created_at", now())
        with self.connect() as db:
            db.execute(f"INSERT INTO {collection} VALUES(?,?,?)", (value["id"], value["created_at"], encoded(value)))
        return value

    def records(self, collection: str) -> list[dict]:
        if collection not in {"metrics", "repairs", "evaluations"}:
            raise ValueError("Unknown artifact collection")
        with self.connect() as db:
            return [json.loads(row[0]) for row in db.execute(f"SELECT payload FROM {collection} ORDER BY rowid DESC LIMIT 100")]
