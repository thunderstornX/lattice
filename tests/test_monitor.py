"""Tests for lattice.monitor — @lattice_monitor zero-friction decorator."""

import pytest

import lattice
from lattice.monitor import lattice_monitor
from lattice.store import LatticeStore


@pytest.fixture
def store() -> LatticeStore:
    return lattice.init(":memory:")


@pytest.fixture
def agent(store: LatticeStore):
    return store.agent("harvester", role="collector")


class TestLatticeMonitor:
    def test_basic_tracking(self, store: LatticeStore, agent):
        """Decorated function creates a claim and returns the original result."""

        @lattice_monitor(agent, method="tool:nslookup")
        def dns_lookup(domain: str) -> dict:
            """DNS lookup for {domain}"""
            return {"ip": "93.184.216.34", "domain": domain}

        result = dns_lookup("example.com")
        assert result == {"ip": "93.184.216.34", "domain": "example.com"}

        claims = store.list_claims()
        assert len(claims) == 1
        claim = claims[0]
        assert claim.agent_id == "harvester"
        assert claim.method == "tool:nslookup"
        assert "example.com" in claim.assertion
        assert claim.confidence == 1.0
        assert claim.signature  # should be signed

    def test_return_value_unchanged(self, store: LatticeStore, agent):
        """Decorator must not alter the return value."""

        @lattice_monitor(agent)
        def compute(x: int, y: int) -> int:
            return x + y

        assert compute(3, 7) == 10

    def test_evidence_stored(self, store: LatticeStore, agent):
        """Return value should be stored as evidence when capture_evidence=True."""

        @lattice_monitor(agent, capture_evidence=True)
        def get_data() -> dict:
            return {"key": "value"}

        get_data()
        claims = store.list_claims()
        assert len(claims) == 1
        # The claim should reference at least one evidence ID
        assert len(claims[0].evidence) >= 1
        # The evidence should be retrievable
        eid = claims[0].evidence[0]
        ev = store.get_evidence(eid)
        assert "value" in ev.data

    def test_no_evidence_capture(self, store: LatticeStore, agent):
        """When capture_evidence=False, no evidence blob is stored."""

        @lattice_monitor(agent, capture_evidence=False)
        def simple() -> str:
            return "hello"

        simple()
        claims = store.list_claims()
        assert len(claims) == 1
        assert claims[0].evidence == []

    def test_custom_confidence(self, store: LatticeStore, agent):
        @lattice_monitor(agent, confidence=0.6, method="llm:gpt-4")
        def analyze(text: str) -> str:
            return "analysis result"

        analyze("some input")
        claims = store.list_claims()
        assert claims[0].confidence == 0.6
        assert claims[0].method == "llm:gpt-4"

    def test_evidence_ids_passed(self, store: LatticeStore, agent):
        """Explicit evidence_ids are included in the claim."""
        eid = store.evidence("prior data")

        @lattice_monitor(agent, evidence_ids=[eid])
        def derived() -> str:
            return "derived result"

        derived()
        claims = store.list_claims()
        assert eid in claims[0].evidence

    def test_metadata_captured(self, store: LatticeStore, agent):
        """Function name, args, result should appear in metadata."""

        @lattice_monitor(agent)
        def lookup(domain: str) -> str:
            return "1.2.3.4"

        lookup("test.com")
        claims = store.list_claims()
        meta = claims[0].metadata
        assert meta["function"] == "lookup"
        assert meta["result"] == "1.2.3.4"
        assert "elapsed_seconds" in meta

    def test_default_method(self, store: LatticeStore, agent):
        """Without explicit method, defaults to tool:<function_name>."""

        @lattice_monitor(agent)
        def my_tool() -> str:
            return "done"

        my_tool()
        claims = store.list_claims()
        assert claims[0].method == "tool:my_tool"

    def test_multiple_calls(self, store: LatticeStore, agent):
        """Each call creates a separate claim."""

        @lattice_monitor(agent)
        def step(n: int) -> int:
            return n * 2

        step(1)
        step(2)
        step(3)
        claims = store.list_claims()
        assert len(claims) == 3

    def test_signature_valid(self, store: LatticeStore, agent):
        """Claims produced by the monitor must have valid signatures."""
        from lattice.agent import verify_signature

        @lattice_monitor(agent)
        def tool() -> str:
            return "result"

        tool()
        claim = store.list_claims()[0]
        assert verify_signature(agent.public_key, claim.claim_id, claim.signature)
