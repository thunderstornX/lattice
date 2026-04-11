"""SQLite-backed persistent store for the LATTICE DAG."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
)

from lattice.agent import AgentHandle, generate_keypair
from lattice.exceptions import (
    AgentAlreadyExistsError,
    AgentNotFoundError,
    ClaimNotFoundError,
    CyclicDependencyError,
    EvidenceNotFoundError,
    StoreError,
)
from lattice.models import Claim, Evidence
from lattice.revocation import (
    RevocationRecord,
    RevocationResult,
    ensure_schema as _ensure_revocation_schema,
    get_claim_status as _get_claim_status,
    is_compromised as _is_compromised,
    is_revoked as _is_revoked,
    list_revocations as _list_revocations,
    revoke_claim as _revoke_claim,
)

LATTICE_DIR_NAME = ".lattice"
DB_FILENAME = "lattice.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS agents (
    agent_id    TEXT PRIMARY KEY,
    role        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    public_key  BLOB NOT NULL,
    private_key BLOB NOT NULL,
    created_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS evidence (
    evidence_id  TEXT PRIMARY KEY,
    data         TEXT NOT NULL,
    content_type TEXT NOT NULL DEFAULT 'text/plain',
    created_at   REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS claims (
    claim_id   TEXT PRIMARY KEY,
    agent_id   TEXT NOT NULL REFERENCES agents(agent_id),
    assertion  TEXT NOT NULL,
    evidence   TEXT NOT NULL DEFAULT '[]',
    confidence REAL NOT NULL,
    method     TEXT NOT NULL,
    timestamp  REAL NOT NULL,
    metadata   TEXT NOT NULL DEFAULT '{}',
    signature  TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_claims_agent ON claims(agent_id);
CREATE INDEX IF NOT EXISTS idx_claims_ts    ON claims(timestamp);
"""


class LatticeStore:
    """SQLite-backed store for agents, evidence, and claims."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._conn = sqlite3.connect(db_path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        _ensure_revocation_schema(self._conn)

    # -- agents ------------------------------------------------------------

    def agent(self, agent_id: str, role: str = "default", description: str = "") -> AgentHandle:
        """Register or retrieve an agent."""
        if self._agent_exists(agent_id):
            return self._get_agent(agent_id)
        return self._register_agent(agent_id, role, description)

    def _register_agent(self, agent_id: str, role: str, description: str) -> AgentHandle:
        private_key, public_bytes = generate_keypair()
        private_bytes = private_key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
        self._conn.execute(
            "INSERT INTO agents (agent_id, role, description, public_key, private_key, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (agent_id, role, description, public_bytes, private_bytes, time.time()),
        )
        self._conn.commit()
        return AgentHandle(agent_id, role, description, public_bytes, private_key, self)

    def _get_agent(self, agent_id: str) -> AgentHandle:
        row = self._conn.execute(
            "SELECT agent_id, role, description, public_key, private_key FROM agents WHERE agent_id=?",
            (agent_id,),
        ).fetchone()
        if row is None:
            raise AgentNotFoundError(f"Agent '{agent_id}' not found")
        private_key = Ed25519PrivateKey.from_private_bytes(row[4])
        return AgentHandle(row[0], row[1], row[2], bytes(row[3]), private_key, self)

    def get_agent(self, agent_id: str) -> AgentHandle:
        """Public accessor — raises AgentNotFoundError if missing."""
        return self._get_agent(agent_id)

    def list_agents(self) -> list[dict[str, Any]]:
        """Return all agents as dicts (no private keys)."""
        rows = self._conn.execute(
            "SELECT agent_id, role, description, created_at FROM agents ORDER BY created_at"
        ).fetchall()
        return [{"agent_id": r[0], "role": r[1], "description": r[2], "created_at": r[3]} for r in rows]

    def _agent_exists(self, agent_id: str) -> bool:
        return self._conn.execute("SELECT 1 FROM agents WHERE agent_id=?", (agent_id,)).fetchone() is not None

    # -- evidence ----------------------------------------------------------

    def evidence(self, data: str, content_type: str = "text/plain") -> str:
        """Store raw evidence (idempotent). Returns evidence ID."""
        ev = Evidence.create(data, content_type)
        self._conn.execute(
            "INSERT OR IGNORE INTO evidence (evidence_id, data, content_type, created_at) VALUES (?,?,?,?)",
            (ev.evidence_id, ev.data, ev.content_type, ev.created_at),
        )
        self._conn.commit()
        return ev.evidence_id

    def get_evidence(self, evidence_id: str) -> Evidence:
        """Retrieve evidence by ID."""
        row = self._conn.execute(
            "SELECT evidence_id, data, content_type, created_at FROM evidence WHERE evidence_id=?",
            (evidence_id,),
        ).fetchone()
        if row is None:
            raise EvidenceNotFoundError(f"Evidence '{evidence_id[:12]}…' not found")
        return Evidence(row[0], row[1], row[2], row[3])

    # -- claims ------------------------------------------------------------

    def _check_no_cycle(self, claim: Claim) -> None:
        """Verify that storing this claim would not create a cycle.

        Walks the ancestor chain of each evidence reference.  If the new
        claim's own ID appears anywhere upstream, that would form a cycle.

        Note: this works because claim_id is deterministic (SHA-256 of
        canonical content) and computed *before* insertion.  The claim's
        ID is known before it exists in the store, so we can check
        whether any ancestor already references it.
        """
        if not claim.evidence:
            return
        visited: set[str] = set()
        queue = list(claim.evidence)
        while queue:
            ref = queue.pop()
            if ref == claim.claim_id:
                raise CyclicDependencyError(
                    f"Adding claim '{claim.claim_id[:12]}...' would create "
                    f"a cycle through evidence reference '{ref[:12]}...'"
                )
            if ref in visited:
                continue
            visited.add(ref)
            row = self._conn.execute(
                "SELECT evidence FROM claims WHERE claim_id=?", (ref,)
            ).fetchone()
            if row is not None:
                for parent_ref in json.loads(row[0]):
                    if parent_ref not in visited:
                        queue.append(parent_ref)

    def put_claim(self, claim: Claim) -> None:
        """Persist a claim.

        Raises:
            CyclicDependencyError: if the claim's evidence references would
                create a cycle in the DAG.
        """
        self._check_no_cycle(claim)
        try:
            self._conn.execute(
                "INSERT OR REPLACE INTO claims"
                " (claim_id, agent_id, assertion, evidence, confidence, method, timestamp, metadata, signature)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    claim.claim_id, claim.agent_id, claim.assertion,
                    json.dumps(claim.evidence), claim.confidence, claim.method,
                    claim.timestamp, json.dumps(claim.metadata), claim.signature,
                ),
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            raise StoreError(f"Failed to store claim: {exc}") from exc

    def get_claim(self, claim_id: str) -> Claim:
        """Retrieve a claim by ID."""
        row = self._conn.execute(
            "SELECT claim_id, agent_id, assertion, evidence, confidence, method, timestamp, metadata, signature"
            " FROM claims WHERE claim_id=?",
            (claim_id,),
        ).fetchone()
        if row is None:
            raise ClaimNotFoundError(f"Claim '{claim_id[:12]}…' not found")
        return _row_to_claim(row)

    def list_claims(
        self,
        agent_id: str | None = None,
        min_confidence: float | None = None,
        max_confidence: float | None = None,
        limit: int = 1000,
    ) -> list[Claim]:
        """Query claims with optional filters."""
        conds: list[str] = []
        params: list[Any] = []
        if agent_id is not None:
            conds.append("agent_id=?")
            params.append(agent_id)
        if min_confidence is not None:
            conds.append("confidence>=?")
            params.append(min_confidence)
        if max_confidence is not None:
            conds.append("confidence<=?")
            params.append(max_confidence)
        where = f" WHERE {' AND '.join(conds)}" if conds else ""
        params.append(limit)
        rows = self._conn.execute(
            f"SELECT claim_id, agent_id, assertion, evidence, confidence, method, timestamp, metadata, signature"
            f" FROM claims{where} ORDER BY timestamp LIMIT ?",
            params,
        ).fetchall()
        return [_row_to_claim(r) for r in rows]

    def claim_count(self) -> int:
        """Total claims in store."""
        return self._conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0]

    def evidence_count(self) -> int:
        """Total evidence blobs."""
        return self._conn.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]

    def agent_count(self) -> int:
        """Total registered agents."""
        return self._conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0]

    # -- revocation --------------------------------------------------------

    def revoke_claim(
        self,
        target_claim_id: str,
        agent_id: str,
        reason: str = "",
        *,
        governance: bool = False,
    ) -> RevocationResult:
        """Revoke a claim and compute the downstream waterfall."""
        return _revoke_claim(self._conn, target_claim_id, agent_id, reason, governance=governance)

    def is_revoked(self, claim_id: str) -> bool:
        """Check if a claim has been directly revoked."""
        return _is_revoked(self._conn, claim_id)

    def is_compromised(self, claim_id: str) -> bool:
        """Check if a claim is compromised (directly or transitively)."""
        return _is_compromised(self._conn, claim_id)

    def get_claim_status(self, claim_id: str) -> str:
        """Return 'VALID', 'REVOKED', or 'COMPROMISED'."""
        return _get_claim_status(self._conn, claim_id)

    def list_revocations(self) -> list[RevocationRecord]:
        """List all revocation records."""
        return _list_revocations(self._conn)

    # -- DAG convenience ---------------------------------------------------

    def effective_confidence(self, claim_id: str) -> float:
        """Compute the effective confidence of a claim (min across ancestors)."""
        from lattice.dag import effective_confidence as _eff_conf
        return _eff_conf(self, claim_id)

    def trace(self, claim_id: str) -> list[Claim]:
        """Trace backward from a claim to all dependencies."""
        from lattice.dag import trace as _trace
        return _trace(self, claim_id)

    def audit(self, confidence_threshold: float = 0.3) -> list:
        """Audit the DAG for issues."""
        from lattice.dag import audit as _audit
        return _audit(self, confidence_threshold)

    def verify(self) -> list:
        """Verify all claim signatures."""
        from lattice.dag import verify_all as _verify
        return _verify(self)

    # -- export ------------------------------------------------------------

    def export_json(self) -> dict[str, Any]:
        """Export entire investigation as JSON-serializable dict."""
        return {
            "agents": self.list_agents(),
            "claims": [c.to_dict() for c in self.list_claims(limit=100_000)],
            "stats": {"agents": self.agent_count(), "claims": self.claim_count(), "evidence": self.evidence_count()},
        }

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()


def _row_to_claim(row: tuple[Any, ...]) -> Claim:
    return Claim(
        claim_id=row[0], agent_id=row[1], assertion=row[2],
        evidence=json.loads(row[3]), confidence=row[4], method=row[5],
        timestamp=row[6], metadata=json.loads(row[7]), signature=row[8],
    )


def init_store(path: str) -> LatticeStore:
    """Initialize a LATTICE store at the given path (or :memory:)."""
    if path == ":memory:":
        return LatticeStore(":memory:")
    lattice_dir = Path(path) / LATTICE_DIR_NAME
    lattice_dir.mkdir(parents=True, exist_ok=True)
    return LatticeStore(str(lattice_dir / DB_FILENAME))
