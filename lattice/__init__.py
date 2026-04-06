"""LATTICE — Ledgered Agent Traces for Transparent, Inspectable Collaborative Execution.

Accountability layer for multi-agent AI systems.

Quick start::

    import lattice

    store = lattice.init(":memory:")
    harvester = store.agent("harvester", role="collector")
    eid = store.evidence("nslookup output…")
    claim = harvester.claim("example.com → 93.184.216.34", evidence=[eid])
    chain = store.trace(claim.claim_id)
"""

__version__ = "0.2.0"

from lattice.agent import AgentHandle
from lattice.adapters import TrackedAdapter, wrap_runnable
from lattice.dag import AuditIssue, VerifyResult, audit, stats, trace, verify_all
from lattice.exceptions import (
    AgentAlreadyExistsError,
    AgentNotFoundError,
    ClaimNotFoundError,
    EvidenceNotFoundError,
    InvalidConfidenceError,
    LatticeError,
    SignatureVerificationError,
    StoreError,
)
from lattice.models import Claim, Evidence
from lattice.store import LatticeStore, init_store
from lattice.tracker import track

__all__ = [
    "AgentHandle",
    "AuditIssue",
    "Claim",
    "Evidence",
    "LatticeStore",
    "TrackedAdapter",
    "VerifyResult",
    "audit",
    "init",
    "init_store",
    "stats",
    "trace",
    "track",
    "wrap_runnable",
    "verify_all",
]


def init(path: str = ".", passphrase: str | None = None) -> LatticeStore:
    """Initialize a LATTICE store.

    Args:
        path: Directory for the investigation, or ``:memory:``.
        passphrase: Optional passphrase used to encrypt agent private keys at rest.

    Returns:
        A ready-to-use ``LatticeStore``.
    """
    return init_store(path, passphrase=passphrase)
