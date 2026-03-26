"""Tests for lattice.store."""

from __future__ import annotations

import pytest

from lattice.exceptions import AgentNotFoundError, ClaimNotFoundError, EvidenceNotFoundError
from lattice.store import LatticeStore


class TestAgents:
    def test_register_and_retrieve(self, store: LatticeStore) -> None:
        agent = store.agent("bot", role="tester")
        assert agent.agent_id == "bot"
        assert agent.role == "tester"

    def test_idempotent(self, store: LatticeStore) -> None:
        a1 = store.agent("bot")
        a2 = store.agent("bot")
        assert a1.agent_id == a2.agent_id

    def test_list_agents(self, store: LatticeStore) -> None:
        store.agent("a")
        store.agent("b")
        agents = store.list_agents()
        assert len(agents) == 2

    def test_get_nonexistent(self, store: LatticeStore) -> None:
        with pytest.raises(AgentNotFoundError):
            store.get_agent("nope")


class TestEvidence:
    def test_store_and_retrieve(self, store: LatticeStore) -> None:
        eid = store.evidence("raw data")
        ev = store.get_evidence(eid)
        assert ev.data == "raw data"

    def test_idempotent(self, store: LatticeStore) -> None:
        eid1 = store.evidence("same")
        eid2 = store.evidence("same")
        assert eid1 == eid2

    def test_not_found(self, store: LatticeStore) -> None:
        with pytest.raises(EvidenceNotFoundError):
            store.get_evidence("deadbeef" * 8)


class TestClaims:
    def test_create_and_retrieve(self, store: LatticeStore) -> None:
        agent = store.agent("bot")
        claim = agent.claim("sky is blue", confidence=0.9, method="eyes")
        retrieved = store.get_claim(claim.claim_id)
        assert retrieved.assertion == "sky is blue"

    def test_not_found(self, store: LatticeStore) -> None:
        with pytest.raises(ClaimNotFoundError):
            store.get_claim("0" * 64)

    def test_list_filter_by_agent(self, store: LatticeStore) -> None:
        a = store.agent("a")
        b = store.agent("b")
        a.claim("one", method="m")
        b.claim("two", method="m")
        assert len(store.list_claims(agent_id="a")) == 1

    def test_list_filter_by_confidence(self, store: LatticeStore) -> None:
        agent = store.agent("bot")
        agent.claim("high", confidence=0.9, method="m")
        agent.claim("low", confidence=0.1, method="m")
        assert len(store.list_claims(min_confidence=0.5)) == 1
        assert len(store.list_claims(max_confidence=0.5)) == 1

    def test_counts(self, store: LatticeStore) -> None:
        agent = store.agent("bot")
        store.evidence("data")
        agent.claim("x", method="m")
        assert store.agent_count() == 1
        assert store.evidence_count() == 1
        assert store.claim_count() == 1


class TestExport:
    def test_export_json(self, store: LatticeStore) -> None:
        agent = store.agent("bot")
        agent.claim("test", method="m")
        data = store.export_json()
        assert data["stats"]["claims"] == 1
        assert len(data["claims"]) == 1
