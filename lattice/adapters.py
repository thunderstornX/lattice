"""Framework adapter helpers for low-friction LATTICE integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol

from lattice.agent import AgentHandle
from lattice.tracker import track_callable


class RunnableLike(Protocol):
    """Minimal callable protocol for framework runnables."""

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Execute runnable."""


@dataclass
class TrackedAdapter:
    """Wrap a callable/runnable and emit LATTICE claims on each invocation."""

    name: str
    runnable: RunnableLike
    tracked: Callable[..., Any]

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self.tracked(*args, **kwargs)


def wrap_runnable(
    name: str,
    runnable: RunnableLike,
    *,
    agent: AgentHandle,
    method: str | None = None,
    confidence: float = 1.0,
) -> TrackedAdapter:
    """Wrap an existing runnable/callable for automatic claim emission."""
    fn = track_callable(
        agent=agent,
        fn=runnable,  # type: ignore[arg-type]
        method=method or f"adapter:{name}",
        confidence=confidence,
    )
    return TrackedAdapter(name=name, runnable=runnable, tracked=fn)

