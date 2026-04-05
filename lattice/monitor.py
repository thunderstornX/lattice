"""Zero-friction middleware decorator for LATTICE.

``@lattice_monitor`` wraps any Python function — tool call, LLM invocation,
or plain computation — and invisibly records a signed Claim in the LATTICE
store.  The wrapped function's return value is **never altered**.

Usage::

    store = lattice.init(":memory:")
    harvester = store.agent("harvester", role="collector")

    @lattice_monitor(harvester, method="tool:nslookup")
    def dns_lookup(domain: str) -> dict:
        \"\"\"DNS lookup for {domain}\"\"\"
        ...

    # Call as normal — LATTICE captures everything behind the scenes.
    result = dns_lookup("example.com")
"""

from __future__ import annotations

import functools
import inspect
import json
import time
from typing import Any, Callable, TypeVar

from lattice.agent import AgentHandle

F = TypeVar("F", bound=Callable[..., Any])


def lattice_monitor(
    agent: AgentHandle,
    *,
    method: str | None = None,
    confidence: float = 1.0,
    evidence_ids: list[str] | None = None,
    capture_evidence: bool = True,
) -> Callable[[F], F]:
    """Zero-friction decorator that auto-creates a signed Claim from a function call.

    Args:
        agent: The LATTICE agent handle that will sign the claim.
        method: Derivation method string (e.g. "tool:nslookup", "llm:gpt-4").
                Defaults to "tool:<function_name>".
        confidence: Confidence score for the generated claim (0.0–1.0).
        evidence_ids: Optional list of existing claim/evidence IDs that
                      this function's output depends on.
        capture_evidence: If True (default), store the return value as a
                          raw Evidence blob and include its ID in the claim.

    Returns:
        Decorated function that behaves identically to the original but
        records a Claim as a side effect.
    """

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.time()
            result = fn(*args, **kwargs)
            elapsed = time.time() - start

            # Build assertion from docstring template or signature
            assertion = _build_assertion(fn, args, kwargs)

            # Build metadata capturing the full call context
            meta = _build_metadata(fn, args, kwargs, result, elapsed)

            # Collect evidence references
            refs: list[str] = list(evidence_ids or [])

            # Optionally store the return value as raw evidence
            if capture_evidence:
                try:
                    evidence_data = json.dumps(result, default=str, sort_keys=True)
                except (TypeError, ValueError):
                    evidence_data = str(result)
                eid = agent._store.evidence(evidence_data, content_type="application/json")
                refs.append(eid)

            # Derive method string
            resolved_method = method or f"tool:{fn.__name__}"

            # Create, sign, and persist the claim
            agent.claim(
                assertion=assertion,
                evidence=refs,
                confidence=confidence,
                method=resolved_method,
                metadata=meta,
            )

            return result

        return wrapper  # type: ignore[return-value]

    return decorator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_assertion(
    fn: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]
) -> str:
    """Build an assertion string from the function's docstring or signature.

    If the docstring contains ``{param}`` placeholders they are filled
    from the bound arguments.
    """
    doc = fn.__doc__
    if doc:
        try:
            sig = inspect.signature(fn)
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            return doc.strip().format(**bound.arguments)
        except (KeyError, IndexError, TypeError):
            return doc.strip()

    # Fallback: function_name(arg1, arg2, key=val)
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
    meta: dict[str, Any] = {
        "function": fn.__name__,
        "elapsed_seconds": round(elapsed, 6),
    }

    # Serialize args safely
    try:
        meta["args"] = json.loads(json.dumps(args, default=str))
    except (TypeError, ValueError):
        meta["args"] = [str(a) for a in args]

    # Serialize kwargs safely
    if kwargs:
        try:
            meta["kwargs"] = json.loads(json.dumps(kwargs, default=str))
        except (TypeError, ValueError):
            meta["kwargs"] = {k: str(v) for k, v in kwargs.items()}

    # Serialize result safely
    try:
        meta["result"] = json.loads(json.dumps(result, default=str))
    except (TypeError, ValueError):
        meta["result"] = str(result)

    return meta
