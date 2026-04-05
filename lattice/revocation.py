"""Revocation Waterfall — flag claims and their downstream dependents as compromised.

Design principle: Claims are immutable and content-addressed.  Revocation status
is stored in a *separate* table and never alters the original claim or its
Ed25519 signature.  Downstream "compromised" status is computed via a recursive
CTE over the claim dependency graph.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from typing import Any

from lattice.exceptions import (
    AlreadyRevokedError,
    ClaimNotFoundError,
    UnauthorizedRevocationError,
)

# ---------------------------------------------------------------------------
# Schema extension — added to LatticeStore._ensure_revocation_schema()
# ---------------------------------------------------------------------------

REVOCATION_SCHEMA = """
CREATE TABLE IF NOT EXISTS revocations (
    revoked_claim_id  TEXT PRIMARY KEY,
    revoked_by        TEXT NOT NULL,
    revoked_at        REAL NOT NULL,
    reason            TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (revoked_claim_id) REFERENCES claims(claim_id),
    FOREIGN KEY (revoked_by) REFERENCES agents(agent_id)
);
CREATE INDEX IF NOT EXISTS idx_revocations_by ON revocations(revoked_by);
"""

# ---------------------------------------------------------------------------
# Recursive CTE — find all downstream claims that depend (directly or
# transitively) on a given claim.  The evidence column stores a JSON
# array of referenced claim/evidence IDs.
# ---------------------------------------------------------------------------

_DOWNSTREAM_CTE = """
WITH RECURSIVE downstream(claim_id) AS (
    -- Seed: every claim whose evidence list contains the revoked claim
    SELECT c.claim_id
    FROM claims c, json_each(c.evidence) AS je
    WHERE je.value = :root_id

    UNION

    -- Recurse: every claim whose evidence contains an already-found downstream claim
    SELECT c2.claim_id
    FROM claims c2, json_each(c2.evidence) AS je2
    JOIN downstream d ON je2.value = d.claim_id
)
SELECT claim_id FROM downstream;
"""


@dataclass(frozen=True)
class RevocationRecord:
    """A single revocation entry."""

    revoked_claim_id: str
    revoked_by: str
    revoked_at: float
    reason: str


@dataclass(frozen=True)
class RevocationResult:
    """Result of a revoke_claim() call."""

    revoked_claim_id: str
    compromised_claim_ids: list[str]
    total_affected: int


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create the revocations table if it doesn't exist."""
    conn.executescript(REVOCATION_SCHEMA)
    conn.commit()


def revoke_claim(
    conn: sqlite3.Connection,
    target_claim_id: str,
    agent_id: str,
    reason: str = "",
    *,
    governance: bool = False,
) -> RevocationResult:
    """Revoke a claim and compute the downstream waterfall.

    Args:
        conn: Open SQLite connection to the LATTICE store.
        target_claim_id: The claim to revoke.
        agent_id: The agent requesting revocation.
        reason: Human-readable justification.
        governance: If True, skip the "must be signer" check (governance override).

    Returns:
        RevocationResult with the directly revoked claim and all
        downstream compromised claim IDs.

    Raises:
        ClaimNotFoundError: target_claim_id doesn't exist.
        UnauthorizedRevocationError: agent_id didn't sign the target claim
            and governance is False.
        AlreadyRevokedError: claim is already revoked.
    """
    # 1. Validate the target claim exists
    row = conn.execute(
        "SELECT agent_id FROM claims WHERE claim_id = ?", (target_claim_id,)
    ).fetchone()
    if row is None:
        raise ClaimNotFoundError(f"Claim '{target_claim_id[:12]}…' not found")

    # 2. Authorization check
    claim_owner = row[0]
    if not governance and claim_owner != agent_id:
        raise UnauthorizedRevocationError(agent_id, target_claim_id)

    # 3. Idempotency check
    existing = conn.execute(
        "SELECT 1 FROM revocations WHERE revoked_claim_id = ?", (target_claim_id,)
    ).fetchone()
    if existing is not None:
        raise AlreadyRevokedError(target_claim_id)

    # 4. Insert the revocation record
    conn.execute(
        "INSERT INTO revocations (revoked_claim_id, revoked_by, revoked_at, reason)"
        " VALUES (?, ?, ?, ?)",
        (target_claim_id, agent_id, time.time(), reason),
    )
    conn.commit()

    # 5. Compute downstream waterfall via recursive CTE
    downstream_rows = conn.execute(
        _DOWNSTREAM_CTE, {"root_id": target_claim_id}
    ).fetchall()
    compromised = [r[0] for r in downstream_rows]

    return RevocationResult(
        revoked_claim_id=target_claim_id,
        compromised_claim_ids=compromised,
        total_affected=1 + len(compromised),
    )


def is_revoked(conn: sqlite3.Connection, claim_id: str) -> bool:
    """Check if a claim has been directly revoked."""
    row = conn.execute(
        "SELECT 1 FROM revocations WHERE revoked_claim_id = ?", (claim_id,)
    ).fetchone()
    return row is not None


def is_compromised(conn: sqlite3.Connection, claim_id: str) -> bool:
    """Check if a claim is compromised (directly revoked OR depends on a revoked claim).

    Uses a recursive CTE to walk *upstream* from the target claim through
    its evidence chain, checking if any ancestor is revoked.
    """
    # Direct revocation check first (fast path)
    if is_revoked(conn, claim_id):
        return True

    # Walk upstream: find all ancestors of this claim
    upstream_cte = """
    WITH RECURSIVE ancestors(cid) AS (
        -- Seed: direct evidence of the target claim
        SELECT je.value AS cid
        FROM claims c, json_each(c.evidence) AS je
        WHERE c.claim_id = :target_id

        UNION

        -- Recurse: evidence of each ancestor
        SELECT je2.value AS cid
        FROM claims c2, json_each(c2.evidence) AS je2
        JOIN ancestors a ON c2.claim_id = a.cid
    )
    SELECT 1 FROM ancestors a
    JOIN revocations r ON r.revoked_claim_id = a.cid
    LIMIT 1;
    """
    row = conn.execute(upstream_cte, {"target_id": claim_id}).fetchone()
    return row is not None


def get_revocation(conn: sqlite3.Connection, claim_id: str) -> RevocationRecord | None:
    """Retrieve the revocation record for a claim, or None."""
    row = conn.execute(
        "SELECT revoked_claim_id, revoked_by, revoked_at, reason"
        " FROM revocations WHERE revoked_claim_id = ?",
        (claim_id,),
    ).fetchone()
    if row is None:
        return None
    return RevocationRecord(row[0], row[1], row[2], row[3])


def list_revocations(conn: sqlite3.Connection) -> list[RevocationRecord]:
    """List all revocation records."""
    rows = conn.execute(
        "SELECT revoked_claim_id, revoked_by, revoked_at, reason"
        " FROM revocations ORDER BY revoked_at"
    ).fetchall()
    return [RevocationRecord(r[0], r[1], r[2], r[3]) for r in rows]


def get_claim_status(conn: sqlite3.Connection, claim_id: str) -> str:
    """Return the status of a claim: 'VALID', 'REVOKED', or 'COMPROMISED'."""
    if is_revoked(conn, claim_id):
        return "REVOKED"
    if is_compromised(conn, claim_id):
        return "COMPROMISED"
    return "VALID"
