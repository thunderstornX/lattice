"""Convenience re-exports for evidence operations."""

from lattice.models import Evidence

__all__ = ["Evidence", "hash_content"]


def hash_content(data: str) -> str:
    """Compute content-addressed ID without storing.

    Args:
        data: Raw evidence content.

    Returns:
        SHA-256 hex digest.
    """
    return Evidence.compute_id(data)
