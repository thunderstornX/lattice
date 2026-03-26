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
