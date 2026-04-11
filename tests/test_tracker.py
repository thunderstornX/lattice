"""Tests for lattice.tracker (deprecated, wraps lattice_monitor)."""

from __future__ import annotations

import warnings

from lattice.store import LatticeStore
from lattice.tracker import track


class TestTrack:
    def test_basic_tracking(self, store: LatticeStore) -> None:
        agent = store.agent("bot")

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)

            @track(agent=agent, method="tool:test")
            def my_func(x: int) -> dict:
                """Process {x}"""
                return {"result": x * 2}

        result = my_func(5)
        assert result == {"result": 10}

        claims = store.list_claims(agent_id="bot")
        assert len(claims) == 1
        assert "Process 5" in claims[0].assertion

    def test_fallback_assertion(self, store: LatticeStore) -> None:
        agent = store.agent("bot")

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)

            @track(agent=agent)
            def no_doc(x: int) -> int:
                return x

        no_doc(42)
        claims = store.list_claims(agent_id="bot")
        assert "no_doc" in claims[0].assertion

    def test_metadata_captured(self, store: LatticeStore) -> None:
        agent = store.agent("bot")

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)

            @track(agent=agent)
            def func() -> str:
                """Do thing"""
                return "done"

        func()
        claims = store.list_claims(agent_id="bot")
        meta = claims[0].metadata
        assert meta["function"] == "func"
        assert "elapsed_seconds" in meta
        assert meta["result"] == "done"

    def test_emits_deprecation_warning(self, store: LatticeStore) -> None:
        agent = store.agent("bot")
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            @track(agent=agent)
            def noop() -> None:
                """Noop"""
                pass

            assert any(issubclass(x.category, DeprecationWarning) for x in w)
            assert any("@track is deprecated" in str(x.message) for x in w)
