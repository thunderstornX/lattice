"""Core data models: Evidence and Claim."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any

from lattice.exceptions import InvalidConfidenceError

HASH_ALGORITHM = "sha256"
MIN_CONFIDENCE = 0.0
MAX_CONFIDENCE = 1.0


@dataclass(frozen=True)
class Evidence:
    """Content-addressed raw evidence blob.

    Attributes:
        evidence_id: SHA-256 hex digest of data.
        data: Raw evidence content.
        content_type: MIME label (e.g. text/plain).
        created_at: Unix timestamp.
    """

    evidence_id: str
    data: str
    content_type: str
    created_at: float

    @staticmethod
    def compute_id(data: str) -> str:
        """Deterministic content-addressed ID."""
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    @classmethod
    def create(
        cls,
        data: str,
        content_type: str = "text/plain",
        created_at: float | None = None,
    ) -> Evidence:
        """Factory with auto-computed ID."""
        return cls(
            evidence_id=cls.compute_id(data),
            data=data,
            content_type=content_type,
            created_at=created_at or time.time(),
        )


def _validate_confidence(value: float) -> float:
    if not (MIN_CONFIDENCE <= value <= MAX_CONFIDENCE):
        raise InvalidConfidenceError(value)
    return value


def compute_claim_id(
    agent_id: str,
    assertion: str,
    evidence: list[str],
    method: str,
    timestamp: float,
    metadata: dict[str, Any],
) -> str:
    """Deterministic SHA-256 claim ID from canonical JSON."""
    canonical = json.dumps(
        {
            "agent_id": agent_id,
            "assertion": assertion,
            "evidence": sorted(evidence),
            "method": method,
            "timestamp": timestamp,
            "metadata": metadata,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Claim:
    """Signed, content-addressed assertion in the LATTICE DAG.

    Attributes:
        claim_id: SHA-256 digest of canonical content.
        agent_id: Originating agent.
        assertion: Human-readable statement.
        evidence: List of claim/evidence IDs this depends on.
        confidence: Float in [0.0, 1.0].
        method: Derivation method (e.g. tool:nslookup).
        timestamp: Unix timestamp.
        metadata: Arbitrary key/value data.
        signature: Hex-encoded Ed25519 signature.
    """

    claim_id: str
    agent_id: str
    assertion: str
    evidence: list[str]
    confidence: float
    method: str
    timestamp: float
    metadata: dict[str, Any] = field(default_factory=dict)
    signature: str = ""

    def __post_init__(self) -> None:
        _validate_confidence(self.confidence)

    @classmethod
    def create(
        cls,
        agent_id: str,
        assertion: str,
        evidence: list[str],
        confidence: float,
        method: str,
        metadata: dict[str, Any] | None = None,
        timestamp: float | None = None,
        signature: str = "",
    ) -> Claim:
        """Factory with auto-computed content-addressed ID."""
        ts = timestamp or time.time()
        meta = metadata or {}
        cid = compute_claim_id(agent_id, assertion, evidence, method, ts, meta)
        return cls(
            claim_id=cid,
            agent_id=agent_id,
            assertion=assertion,
            evidence=list(evidence),
            confidence=confidence,
            method=method,
            timestamp=ts,
            metadata=meta,
            signature=signature,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-safe dict."""
        return {
            "claim_id": self.claim_id,
            "agent_id": self.agent_id,
            "assertion": self.assertion,
            "evidence": self.evidence,
            "confidence": self.confidence,
            "method": self.method,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
            "signature": self.signature,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Claim:
        """Deserialize from dict."""
        return cls(
            claim_id=data["claim_id"],
            agent_id=data["agent_id"],
            assertion=data["assertion"],
            evidence=data["evidence"],
            confidence=data["confidence"],
            method=data["method"],
            timestamp=data["timestamp"],
            metadata=data.get("metadata", {}),
            signature=data.get("signature", ""),
        )
