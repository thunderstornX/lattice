"""Auto-instrumentation decorator for LATTICE."""

from __future__ import annotations

import functools
import inspect
import json
import time
from typing import Any, Callable, TypeVar

from lattice.agent import AgentHandle

F = TypeVar("F", bound=Callable[..., Any])


def track(
    agent: AgentHandle,
    method: str | None = None,
    confidence: float = 1.0,
) -> Callable[[F], F]:
    """Decorator that auto-creates a Claim from a function call.

    The function's docstring becomes the assertion template.
    Return value and args are captured as metadata.

    Example::

        @track(agent=harvester, method="tool:nslookup")
        def dns_lookup(domain: str) -> dict:
            \"\"\"DNS lookup for {domain}\"\"\"
            ...
    """

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.time()
            result = fn(*args, **kwargs)
            elapsed = time.time() - start

            assertion = _build_assertion(fn, args, kwargs)
            meta = _build_metadata(fn, args, kwargs, result, elapsed)

            agent.claim(
                assertion=assertion,
                confidence=confidence,
                method=method or f"func:{fn.__name__}",
                metadata=meta,
            )
            return result

        return wrapper  # type: ignore[return-value]
    return decorator


def _build_assertion(fn: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
    """Build assertion from docstring template or function signature."""
    doc = fn.__doc__
    if doc:
        try:
            sig = inspect.signature(fn)
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            return doc.strip().format(**bound.arguments)
        except (KeyError, IndexError, TypeError):
            return doc.strip()
    arg_strs = [repr(a) for a in args] + [f"{k}={v!r}" for k, v in kwargs.items()]
    return f"{fn.__name__}({', '.join(arg_strs)})"


def _build_metadata(
    fn: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    result: Any,
    elapsed: float,
) -> dict[str, Any]:
    """Capture function call details as JSON-safe metadata."""
    meta: dict[str, Any] = {"function": fn.__name__, "elapsed_seconds": round(elapsed, 4)}
    try:
        meta["args"] = json.loads(json.dumps(args, default=str))
    except (TypeError, ValueError):
        meta["args"] = [str(a) for a in args]
    if kwargs:
        try:
            meta["kwargs"] = json.loads(json.dumps(kwargs, default=str))
        except (TypeError, ValueError):
            meta["kwargs"] = {k: str(v) for k, v in kwargs.items()}
    try:
        meta["result"] = json.loads(json.dumps(result, default=str))
    except (TypeError, ValueError):
        meta["result"] = str(result)
    return meta
