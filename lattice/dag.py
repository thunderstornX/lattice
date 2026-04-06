"""DAG traversal, trace-back, audit, and verification."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any

from lattice.agent import verify_signature
from lattice.exceptions import ClaimNotFoundError
from lattice.models import Claim
from lattice.store import LatticeStore


def trace(store: LatticeStore, claim_id: str) -> list[Claim]:
    """Walk backward from a claim through all dependencies (BFS).

    Returns claims in breadth-first order: conclusion first, then
    its evidence, then their evidence, etc.
    """
    store.get_claim(claim_id)  # validate root exists

    visited: set[str] = set()
    result: list[Claim] = []
    queue: deque[str] = deque([claim_id])

    while queue:
        cid = queue.popleft()
        if cid in visited:
            continue
        visited.add(cid)
        try:
            claim = store.get_claim(cid)
        except ClaimNotFoundError:
            continue  # evidence hash leaf
        result.append(claim)
        for ref in claim.evidence:
            if ref not in visited:
                queue.append(ref)

    return result


@dataclass
class AuditIssue:
    """A single issue found during audit."""

    claim_id: str
    issue_type: str
    description: str


def audit(store: LatticeStore, confidence_threshold: float = 0.3) -> list[AuditIssue]:
    """Audit the DAG for unsupported claims, low confidence, and broken refs."""
    issues: list[AuditIssue] = []
    claims = store.list_claims(limit=100_000)
    known_ids = {c.claim_id for c in claims}

    for claim in claims:
        if not claim.evidence:
            issues.append(AuditIssue(
                claim.claim_id, "unsupported",
                f"No evidence: '{claim.assertion[:60]}'",
            ))
        if claim.confidence < confidence_threshold:
            issues.append(AuditIssue(
                claim.claim_id, "low_confidence",
                f"Confidence {claim.confidence:.2f} < {confidence_threshold:.2f}: '{claim.assertion[:60]}'",
            ))
        for ref in claim.evidence:
            if ref not in known_ids:
                try:
                    store.get_evidence(ref)
                except Exception:  # noqa: BLE001
                    issues.append(AuditIssue(
                        claim.claim_id, "broken_reference",
                        f"Ref '{ref[:12]}…' not found",
                    ))
    return issues


@dataclass
class VerifyResult:
    """Signature verification result."""

    claim_id: str
    agent_id: str
    valid: bool
    error: str = ""


def verify_all(store: LatticeStore) -> list[VerifyResult]:
    """Verify content integrity AND Ed25519 signatures on all claims.

    Two checks per claim:
      1. Re-hash content to confirm claim_id matches (tamper detection).
      2. Verify Ed25519 signature over claim_id (agent attribution).
    """
    from lattice.models import compute_claim_id

    results: list[VerifyResult] = []
    for claim in store.list_claims(limit=100_000):
        # Step 1: Content integrity (re-hash and compare)
        recomputed = compute_claim_id(
            claim.agent_id, claim.assertion, claim.evidence,
            claim.method, claim.timestamp, claim.metadata,
        )
        if recomputed != claim.claim_id:
            results.append(VerifyResult(
                claim.claim_id, claim.agent_id, False,
                f"Content tampered (expected {recomputed[:12]}...)",
            ))
            continue

        # Step 2: Signature verification
        if not claim.signature:
            results.append(VerifyResult(claim.claim_id, claim.agent_id, False, "No signature"))
            continue
        try:
            public_key = store.get_claim_signing_public_key(claim)
            valid = verify_signature(public_key, claim.claim_id, claim.signature)
            results.append(VerifyResult(
                claim.claim_id, claim.agent_id, valid,
                "" if valid else "Signature mismatch",
            ))
        except Exception as exc:  # noqa: BLE001
            results.append(VerifyResult(claim.claim_id, claim.agent_id, False, str(exc)))
    return results


def stats(store: LatticeStore) -> dict[str, Any]:
    """Summary statistics for the investigation."""
    claims = store.list_claims(limit=100_000)
    confs = [c.confidence for c in claims]
    methods: dict[str, int] = {}
    per_agent: dict[str, int] = {}
    for c in claims:
        methods[c.method] = methods.get(c.method, 0) + 1
        per_agent[c.agent_id] = per_agent.get(c.agent_id, 0) + 1

    return {
        "total_agents": store.agent_count(),
        "total_claims": len(claims),
        "total_evidence": store.evidence_count(),
        "avg_confidence": sum(confs) / len(confs) if confs else 0.0,
        "min_confidence": min(confs) if confs else 0.0,
        "max_confidence": max(confs) if confs else 0.0,
        "methods": methods,
        "claims_per_agent": per_agent,
    }
