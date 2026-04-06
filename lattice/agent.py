"""Agent registry and Ed25519 key management."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

from lattice.models import Claim

if TYPE_CHECKING:
    from lattice.store import LatticeStore


def generate_keypair() -> tuple[Ed25519PrivateKey, bytes]:
    """Generate a fresh Ed25519 keypair → (private_key, public_bytes_raw)."""
    private_key = Ed25519PrivateKey.generate()
    public_bytes = private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return private_key, public_bytes


def sign_claim_id(private_key: Ed25519PrivateKey, claim_id: str) -> str:
    """Sign a claim ID, return hex-encoded signature."""
    return private_key.sign(claim_id.encode("utf-8")).hex()


def verify_signature(public_key_bytes: bytes, claim_id: str, signature_hex: str) -> bool:
    """Verify an Ed25519 signature on a claim ID."""
    try:
        pub = Ed25519PublicKey.from_public_bytes(public_key_bytes)
        pub.verify(bytes.fromhex(signature_hex), claim_id.encode("utf-8"))
        return True
    except Exception:  # noqa: BLE001
        return False


@dataclass
class AgentHandle:
    """Live handle for a registered agent with signing capability.

    Attributes:
        agent_id: Unique identifier.
        role: Role label (collector, analyst, etc.).
        description: Human-readable description.
        public_key: Raw 32-byte Ed25519 public key.
    """

    agent_id: str
    role: str
    description: str
    public_key: bytes
    _private_key: Ed25519PrivateKey
    _store: LatticeStore

    def claim(
        self,
        assertion: str,
        evidence: list[str] | None = None,
        confidence: float = 1.0,
        method: str = "manual",
        metadata: dict[str, Any] | None = None,
    ) -> Claim:
        """Create, sign, and persist a new Claim."""
        unsigned = Claim.create(
            agent_id=self.agent_id,
            assertion=assertion,
            evidence=evidence or [],
            confidence=confidence,
            method=method,
            metadata={
                **(metadata or {}),
                "signing_public_key": self.public_key.hex(),
            },
        )
        signature = sign_claim_id(self._private_key, unsigned.claim_id)
        signed = Claim(
            claim_id=unsigned.claim_id,
            agent_id=unsigned.agent_id,
            assertion=unsigned.assertion,
            evidence=unsigned.evidence,
            confidence=unsigned.confidence,
            method=unsigned.method,
            timestamp=unsigned.timestamp,
            metadata=unsigned.metadata,
            signature=signature,
        )
        self._store.put_claim(signed)
        return signed

    def private_key_bytes(self) -> bytes:
        """Export private key as raw 32-byte seed."""
        return self._private_key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
