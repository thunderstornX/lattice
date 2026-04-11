"""Legacy auto-instrumentation decorator.

``@track`` is a convenience alias for ``@lattice_monitor`` with
``capture_evidence=False``.  New code should prefer ``@lattice_monitor``
directly since it offers more control (evidence capture, custom evidence
IDs, etc.).

.. deprecated:: 1.1
   Use :func:`lattice.monitor.lattice_monitor` instead.
"""

from __future__ import annotations

import warnings
from typing import Any, Callable, TypeVar

from lattice.agent import AgentHandle
from lattice.monitor import lattice_monitor

F = TypeVar("F", bound=Callable[..., Any])


def track(
    agent: AgentHandle,
    method: str | None = None,
    confidence: float = 1.0,
) -> Callable[[F], F]:
    """Decorator that auto-creates a Claim from a function call.

    This is a thin wrapper around :func:`lattice_monitor` with
    ``capture_evidence=False``.  Prefer ``@lattice_monitor`` for new code.

    Example::

        @track(agent=harvester, method="tool:nslookup")
        def dns_lookup(domain: str) -> dict:
            \"\"\"DNS lookup for {domain}\"\"\"
            ...

    .. deprecated:: 1.1
       Use ``@lattice_monitor`` instead.
    """
    warnings.warn(
        "@track is deprecated; use @lattice_monitor instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return lattice_monitor(
        agent,
        method=method,
        confidence=confidence,
        capture_evidence=False,
    )
