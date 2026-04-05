"""LATTICE custom exceptions."""


class LatticeError(Exception):
    """Base exception for all LATTICE errors."""


class StoreError(LatticeError):
    """Failed to read from or write to the backing store."""


class StoreNotInitializedError(StoreError):
    """Store has not been initialized."""


class AgentNotFoundError(LatticeError):
    """Agent does not exist in the registry."""


class AgentAlreadyExistsError(LatticeError):
    """Agent with this ID already exists."""


class ClaimNotFoundError(LatticeError):
    """Claim does not exist in the store."""


class EvidenceNotFoundError(LatticeError):
    """Evidence blob does not exist in the store."""


class SignatureVerificationError(LatticeError):
    """Cryptographic signature verification failed."""


class InvalidConfidenceError(LatticeError):
    """Confidence value outside [0.0, 1.0]."""

    def __init__(self, value: float) -> None:
        self.value = value
        super().__init__(f"Confidence must be between 0.0 and 1.0, got {value}")


class CyclicDependencyError(LatticeError):
    """Evidence references would create a cycle in the DAG."""


class RevocationError(LatticeError):
    """Revocation operation failed."""


class UnauthorizedRevocationError(RevocationError):
    """Agent is not authorized to revoke this claim."""

    def __init__(self, agent_id: str, claim_id: str) -> None:
        self.agent_id = agent_id
        self.claim_id = claim_id
        super().__init__(
            f"Agent '{agent_id}' is not authorized to revoke claim '{claim_id[:12]}…'"
        )


class AlreadyRevokedError(RevocationError):
    """Claim has already been revoked."""

    def __init__(self, claim_id: str) -> None:
        self.claim_id = claim_id
        super().__init__(f"Claim '{claim_id[:12]}…' is already revoked")
