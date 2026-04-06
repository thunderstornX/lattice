"""SQLite-backed persistent store for the LATTICE DAG."""

from __future__ import annotations

import json
import os
import sqlite3
import time
from base64 import urlsafe_b64encode
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
)
from cryptography.hazmat.primitives import hashes
from cryptography.fernet import Fernet, InvalidToken

from lattice.agent import AgentHandle, generate_keypair
from lattice.exceptions import (
    AgentKeyLockedError,
    AmbiguousClaimIdError,
    AgentNotFoundError,
    ClaimNotFoundError,
    EvidenceNotFoundError,
    StoreError,
)
from lattice.models import Claim, Evidence

LATTICE_DIR_NAME = ".lattice"
DB_FILENAME = "lattice.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_info (
    version INTEGER PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS agents (
    agent_id    TEXT PRIMARY KEY,
    role        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    public_key  BLOB NOT NULL,
    private_key BLOB NOT NULL,
    key_status  TEXT NOT NULL DEFAULT 'active',
    key_kind    TEXT NOT NULL DEFAULT 'raw',
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
CREATE INDEX IF NOT EXISTS idx_claims_id    ON claims(claim_id);
"""

CURRENT_SCHEMA_VERSION = 2


class LatticeStore:
    """SQLite-backed store for agents, evidence, and claims."""

    def __init__(self, db_path: str, passphrase: str | None = None) -> None:
        self._db_path = db_path
        self._passphrase = passphrase
        self._conn = sqlite3.connect(db_path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA)
        self._ensure_schema()
        self._run_migrations()
        self._conn.commit()

    # -- agents ------------------------------------------------------------

    def agent(self, agent_id: str, role: str = "default", description: str = "") -> AgentHandle:
        """Register or retrieve an agent."""
        if self._agent_exists(agent_id):
            return self._get_agent(agent_id)
        return self._register_agent(agent_id, role, description)

    def _register_agent(self, agent_id: str, role: str, description: str) -> AgentHandle:
        private_key, public_bytes = generate_keypair()
        private_bytes = private_key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
        encrypted, key_kind = self._encode_private_key(private_bytes)
        self._conn.execute(
            "INSERT INTO agents (agent_id, role, description, public_key, private_key, created_at, key_status, key_kind)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (agent_id, role, description, public_bytes, encrypted, time.time(), "active", key_kind),
        )
        self._conn.commit()
        return AgentHandle(agent_id, role, description, public_bytes, private_key, self)

    def _get_agent(self, agent_id: str) -> AgentHandle:
        row = self._conn.execute(
            "SELECT agent_id, role, description, public_key, private_key, key_status, key_kind FROM agents WHERE agent_id=?",
            (agent_id,),
        ).fetchone()
        if row is None:
            raise AgentNotFoundError(f"Agent '{agent_id}' not found")
        if row[5] != "active":
            raise AgentKeyLockedError(f"Agent '{agent_id}' key is {row[5]}")
        private_bytes = self._decode_private_key(bytes(row[4]), row[6])
        private_key = Ed25519PrivateKey.from_private_bytes(private_bytes)
        return AgentHandle(row[0], row[1], row[2], bytes(row[3]), private_key, self)

    def get_agent(self, agent_id: str) -> AgentHandle:
        """Public accessor — raises AgentNotFoundError if missing."""
        return self._get_agent(agent_id)

    def list_agents(self) -> list[dict[str, Any]]:
        """Return all agents as dicts (no private keys)."""
        rows = self._conn.execute(
            "SELECT agent_id, role, description, created_at, key_status, key_kind FROM agents ORDER BY created_at"
        ).fetchall()
        return [
            {
                "agent_id": r[0],
                "role": r[1],
                "description": r[2],
                "created_at": r[3],
                "key_status": r[4],
                "key_kind": r[5],
            }
            for r in rows
        ]

    def _agent_exists(self, agent_id: str) -> bool:
        return self._conn.execute("SELECT 1 FROM agents WHERE agent_id=?", (agent_id,)).fetchone() is not None

    def revoke_agent(self, agent_id: str) -> None:
        """Mark an agent key as revoked."""
        updated = self._conn.execute(
            "UPDATE agents SET key_status='revoked' WHERE agent_id=?",
            (agent_id,),
        ).rowcount
        if updated == 0:
            raise AgentNotFoundError(f"Agent '{agent_id}' not found")
        self._conn.commit()

    def rotate_agent_key(self, agent_id: str) -> AgentHandle:
        """Rotate an agent keypair in place while preserving agent identity."""
        row = self._conn.execute(
            "SELECT role, description FROM agents WHERE agent_id=?",
            (agent_id,),
        ).fetchone()
        if row is None:
            raise AgentNotFoundError(f"Agent '{agent_id}' not found")
        private_key, public_bytes = generate_keypair()
        private_bytes = private_key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
        encrypted, key_kind = self._encode_private_key(private_bytes)
        self._conn.execute(
            "UPDATE agents SET public_key=?, private_key=?, key_status='active', key_kind=? WHERE agent_id=?",
            (public_bytes, encrypted, key_kind, agent_id),
        )
        self._conn.commit()
        return AgentHandle(agent_id, row[0], row[1], public_bytes, private_key, self)

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

    def put_claim(self, claim: Claim) -> None:
        """Persist a claim."""
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

    # -- DAG convenience ---------------------------------------------------

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

    def resolve_claim_id_prefix(self, prefix: str) -> str:
        """Resolve a partial claim ID to one full ID."""
        if not prefix:
            raise ClaimNotFoundError("Claim '' not found")
        rows = self._conn.execute(
            "SELECT claim_id FROM claims WHERE claim_id LIKE ? ORDER BY claim_id LIMIT 2",
            (f"{prefix}%",),
        ).fetchall()
        if len(rows) == 1:
            return rows[0][0]
        if len(rows) > 1:
            raise AmbiguousClaimIdError(f"Ambiguous claim prefix '{prefix}'")
        raise ClaimNotFoundError(f"Claim '{prefix[:12]}…' not found")

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

    def _ensure_schema(self) -> None:
        row = self._conn.execute("SELECT version FROM schema_info LIMIT 1").fetchone()
        if row is None:
            cols = {
                r[1]: r[2]
                for r in self._conn.execute("PRAGMA table_info(agents)").fetchall()
            }
            has_v2_cols = "key_status" in cols and "key_kind" in cols
            inferred_version = CURRENT_SCHEMA_VERSION if has_v2_cols else 1
            self._conn.execute("INSERT INTO schema_info (version) VALUES (?)", (inferred_version,))
        self._conn.commit()

    def _run_migrations(self) -> None:
        row = self._conn.execute("SELECT version FROM schema_info LIMIT 1").fetchone()
        version = row[0] if row else 1
        if version < 2:
            cols = {
                r[1]: r[2]
                for r in self._conn.execute("PRAGMA table_info(agents)").fetchall()
            }
            if "key_status" not in cols:
                self._conn.execute("ALTER TABLE agents ADD COLUMN key_status TEXT NOT NULL DEFAULT 'active'")
            if "key_kind" not in cols:
                self._conn.execute("ALTER TABLE agents ADD COLUMN key_kind TEXT NOT NULL DEFAULT 'raw'")
            self._conn.execute("UPDATE schema_info SET version=2")
        self._conn.commit()

    def _encode_private_key(self, private_bytes: bytes) -> tuple[bytes, str]:
        if not self._passphrase:
            return private_bytes, "raw"
        salt = os.urandom(16)
        key = self._derive_fernet_key(self._passphrase, salt)
        token = Fernet(key).encrypt(private_bytes)
        return salt + token, "fernet_pbkdf2"

    def _decode_private_key(self, encoded: bytes, key_kind: str) -> bytes:
        if key_kind == "raw":
            return encoded
        if key_kind == "fernet_pbkdf2":
            if not self._passphrase:
                raise AgentKeyLockedError("Encrypted agent key requires passphrase")
            if len(encoded) < 17:
                raise StoreError("Encrypted key payload is malformed")
            salt = encoded[:16]
            token = encoded[16:]
            key = self._derive_fernet_key(self._passphrase, salt)
            try:
                return Fernet(key).decrypt(token)
            except InvalidToken as exc:
                raise AgentKeyLockedError("Invalid passphrase for encrypted agent key") from exc
        raise StoreError(f"Unsupported key kind '{key_kind}'")

    @staticmethod
    def _derive_fernet_key(passphrase: str, salt: bytes) -> bytes:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=390000,
        )
        return urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))

    def get_agent_public_key(self, agent_id: str) -> bytes:
        """Return current agent public key."""
        row = self._conn.execute("SELECT public_key FROM agents WHERE agent_id=?", (agent_id,)).fetchone()
        if row is None:
            raise AgentNotFoundError(f"Agent '{agent_id}' not found")
        return bytes(row[0])

    def is_agent_active(self, agent_id: str) -> bool:
        """Whether an agent key is active."""
        row = self._conn.execute("SELECT key_status FROM agents WHERE agent_id=?", (agent_id,)).fetchone()
        if row is None:
            raise AgentNotFoundError(f"Agent '{agent_id}' not found")
        return row[0] == "active"

    def get_claim_signing_public_key(self, claim: Claim) -> bytes:
        """Recover signer key from claim metadata fallback to current key."""
        signer_hex = claim.metadata.get("signing_public_key")
        if signer_hex:
            return bytes.fromhex(signer_hex)
        return self.get_agent_public_key(claim.agent_id)


def _row_to_claim(row: tuple[Any, ...]) -> Claim:
    return Claim(
        claim_id=row[0], agent_id=row[1], assertion=row[2],
        evidence=json.loads(row[3]), confidence=row[4], method=row[5],
        timestamp=row[6], metadata=json.loads(row[7]), signature=row[8],
    )


def init_store(path: str, passphrase: str | None = None) -> LatticeStore:
    """Initialize a LATTICE store at the given path (or :memory:)."""
    if path == ":memory:":
        return LatticeStore(":memory:", passphrase=passphrase)
    lattice_dir = Path(path) / LATTICE_DIR_NAME
    lattice_dir.mkdir(parents=True, exist_ok=True)
    return LatticeStore(str(lattice_dir / DB_FILENAME), passphrase=passphrase)
