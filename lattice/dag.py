"""DAG traversal, trace-back, audit, verification, and effective confidence."""

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


# ---------------------------------------------------------------------------
# Effective confidence
# ---------------------------------------------------------------------------


def effective_confidence(store: LatticeStore, claim_id: str) -> float:
    """Compute the effective confidence of a claim.

    The effective confidence is the minimum confidence across the claim
    itself and all of its ancestors in the DAG.  This ensures that a
    high-confidence conclusion cannot mask low-confidence evidence
    deeper in the chain.

    Formally:
        gamma*(c) = min(gamma(c), min_{c' in ancestors(c)} gamma(c'))

    If a reference points to raw evidence (not a claim), it is treated
    as having confidence 1.0 (raw data is maximally trustworthy as data;
    its interpretation is a separate concern).

    Returns:
        The effective confidence as a float in [0.0, 1.0].

    Raises:
        ClaimNotFoundError: if claim_id does not exist.
    """
    root = store.get_claim(claim_id)
    min_conf = root.confidence

    visited: set[str] = set()
    queue: deque[str] = deque()

    # Seed with evidence refs
    for ref in root.evidence:
        queue.append(ref)

    while queue:
        cid = queue.popleft()
        if cid in visited:
            continue
        visited.add(cid)
        try:
            claim = store.get_claim(cid)
        except ClaimNotFoundError:
            continue  # evidence leaf, confidence 1.0 by convention
        if claim.confidence < min_conf:
            min_conf = claim.confidence
        for ref in claim.evidence:
            if ref not in visited:
                queue.append(ref)

    return min_conf


def effective_confidence_bulk(store: LatticeStore) -> dict[str, float]:
    """Compute effective confidence for all claims in the store.

    Returns a dict mapping claim_id to effective confidence.  Uses an
    iterative reverse-topological traversal (Kahn's algorithm) to avoid
    Python's recursion limit on deep chains.
    """
    claims = store.list_claims(limit=100_000)
    if not claims:
        return {}

    claim_map: dict[str, Claim] = {c.claim_id: c for c in claims}
    claim_ids = set(claim_map.keys())

    # Build reverse adjacency: for each claim, which claims depend on it?
    # Also count how many *claim* dependencies each claim has (in-degree).
    dependents: dict[str, list[str]] = {cid: [] for cid in claim_ids}
    in_degree: dict[str, int] = {cid: 0 for cid in claim_ids}

    for c in claims:
        for ref in c.evidence:
            if ref in claim_ids:
                dependents[ref].append(c.claim_id)
                in_degree[c.claim_id] += 1

    # Kahn's algorithm: start from leaves (claims with no claim-dependencies)
    queue: deque[str] = deque()
    for cid, deg in in_degree.items():
        if deg == 0:
            queue.append(cid)

    cache: dict[str, float] = {}

    while queue:
        cid = queue.popleft()
        claim = claim_map[cid]
        # Effective confidence = min of own confidence and all evidence refs
        min_c = claim.confidence
        for ref in claim.evidence:
            if ref in cache:
                if cache[ref] < min_c:
                    min_c = cache[ref]
            elif ref not in claim_ids:
                pass  # raw evidence leaf, confidence 1.0
        cache[cid] = min_c

        # Decrement in-degree for dependents, enqueue if ready
        for dep in dependents[cid]:
            in_degree[dep] -= 1
            if in_degree[dep] == 0:
                queue.append(dep)

    return cache


@dataclass
class AuditIssue:
    """A single issue found during audit."""

    claim_id: str
    issue_type: str
    description: str


def audit(store: LatticeStore, confidence_threshold: float = 0.3) -> list[AuditIssue]:
    """Audit the DAG for unsupported claims, low confidence, broken refs,
    and inflated confidence."""
    issues: list[AuditIssue] = []
    claims = store.list_claims(limit=100_000)
    known_ids = {c.claim_id for c in claims}

    # Compute effective confidence for all claims once
    eff_conf = effective_confidence_bulk(store)

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
                        f"Ref '{ref[:12]}...' not found",
                    ))

        # Inflated confidence: stated > effective by more than 0.01
        eff = eff_conf.get(claim.claim_id, claim.confidence)
        if claim.confidence - eff > 0.01 and claim.evidence:
            issues.append(AuditIssue(
                claim.claim_id, "inflated_confidence",
                f"Stated {claim.confidence:.2f} but effective {eff:.2f} "
                f"(ancestor floor): '{claim.assertion[:50]}'",
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
            agent = store.get_agent(claim.agent_id)
            valid = verify_signature(agent.public_key, claim.claim_id, claim.signature)
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

    # Effective confidence stats
    eff = effective_confidence_bulk(store) if claims else {}
    eff_vals = list(eff.values()) if eff else []

    return {
        "total_agents": store.agent_count(),
        "total_claims": len(claims),
        "total_evidence": store.evidence_count(),
        "avg_confidence": sum(confs) / len(confs) if confs else 0.0,
        "min_confidence": min(confs) if confs else 0.0,
        "max_confidence": max(confs) if confs else 0.0,
        "avg_effective_confidence": sum(eff_vals) / len(eff_vals) if eff_vals else 0.0,
        "min_effective_confidence": min(eff_vals) if eff_vals else 0.0,
        "methods": methods,
        "claims_per_agent": per_agent,
    }
