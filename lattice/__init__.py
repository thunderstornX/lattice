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

__version__ = "1.2.0"

from lattice.agent import AgentHandle
from lattice.dag import (
    AuditIssue,
    VerifyResult,
    audit,
    effective_confidence,
    effective_confidence_bulk,
    stats,
    trace,
    verify_all,
)
from lattice.exceptions import (
    AgentAlreadyExistsError,
    AgentNotFoundError,
    AlreadyRevokedError,
    ClaimNotFoundError,
    CyclicDependencyError,
    EvidenceNotFoundError,
    InvalidConfidenceError,
    LatticeError,
    RevocationError,
    SignatureVerificationError,
    StoreError,
    UnauthorizedRevocationError,
)
from lattice.models import Claim, Evidence
from lattice.monitor import lattice_monitor
from lattice.revocation import RevocationRecord, RevocationResult
from lattice.store import LatticeStore, init_store
from lattice.tracker import track

__all__ = [
    "AgentHandle",
    "AlreadyRevokedError",
    "AuditIssue",
    "Claim",
    "Evidence",
    "LatticeStore",
    "RevocationError",
    "RevocationRecord",
    "RevocationResult",
    "UnauthorizedRevocationError",
    "VerifyResult",
    "audit",
    "effective_confidence",
    "effective_confidence_bulk",
    "init",
    "init_store",
    "lattice_monitor",
    "stats",
    "trace",
    "track",
    "verify_all",
]


def init(path: str = ".") -> LatticeStore:
    """Initialize a LATTICE store.

    Args:
        path: Directory for the investigation, or ``:memory:``.

    Returns:
        A ready-to-use ``LatticeStore``.
    """
    return init_store(path)
