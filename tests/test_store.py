"""Tests for lattice.store."""

from __future__ import annotations

import sqlite3

import pytest

import lattice
from lattice.exceptions import AgentNotFoundError, ClaimNotFoundError, CyclicDependencyError, EvidenceNotFoundError
from lattice.models import Claim
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


class TestCycleDetection:
    def test_self_referencing_claim_rejected(self, store: LatticeStore) -> None:
        """A claim that lists its own ID as evidence should be rejected."""
        from lattice.models import Claim

        agent = store.agent("bot")
        # Manually construct a claim that references itself
        c = Claim.create(
            agent_id="bot",
            assertion="I prove myself",
            evidence=["placeholder"],
            confidence=0.5,
            method="manual",
        )
        # Now make the evidence list include the claim's own ID
        bad_claim = Claim(
            claim_id=c.claim_id,
            agent_id=c.agent_id,
            assertion=c.assertion,
            evidence=[c.claim_id],
            confidence=c.confidence,
            method=c.method,
            timestamp=c.timestamp,
            metadata=c.metadata,
            signature="",
        )
        with pytest.raises(CyclicDependencyError):
            store.put_claim(bad_claim)

    def test_indirect_cycle_rejected(self, store: LatticeStore) -> None:
        """Indirect cycles (A -> B -> C, then C -> A) are rejected.

        A genuine indirect cycle is structurally impossible to build through
        the normal API: a claim's ID is the SHA-256 of its content, so a
        descendant can never share an ancestor's ID without a hash preimage.
        The only way to *attempt* one is to forge a claim that reuses an
        ancestor's ID while pointing its evidence at a descendant;
        ``_check_no_cycle`` walks the ancestry and rejects it.
        """
        agent = store.agent("bot")
        a = agent.claim("claim A", method="m")
        b = agent.claim("claim B", evidence=[a.claim_id], method="m")
        c = agent.claim("claim C", evidence=[b.claim_id], method="m")

        # The legitimate deep chain resolves cleanly.
        assert len(store.trace(c.claim_id)) == 3

        # Forge a claim that reuses A's ID but depends on its own descendant C.
        forged = Claim(
            claim_id=a.claim_id,
            agent_id=a.agent_id,
            assertion=a.assertion,
            evidence=[c.claim_id],
            confidence=a.confidence,
            method=a.method,
            timestamp=a.timestamp,
            metadata=a.metadata,
            signature="",
        )
        with pytest.raises(CyclicDependencyError):
            store.put_claim(forged)


class TestExport:
    def test_export_json(self, store: LatticeStore) -> None:
        agent = store.agent("bot")
        agent.claim("test", method="m")
        data = store.export_json()
        assert data["stats"]["claims"] == 1
        assert len(data["claims"]) == 1


class TestPersistence:
    def test_wal_mode_on_disk(self, file_store: LatticeStore) -> None:
        mode = file_store._conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"

    def test_survives_close_and_reopen(self, tmp_path) -> None:
        s1 = lattice.init(str(tmp_path))
        agent = s1.agent("bot", role="r")
        eid = s1.evidence("raw data")
        claim = agent.claim("fact", evidence=[eid], confidence=0.7, method="m")
        cid = claim.claim_id
        s1.close()

        s2 = lattice.init(str(tmp_path))
        try:
            got = s2.get_claim(cid)
            assert got.assertion == "fact"
            assert got.confidence == 0.7
            assert got.evidence == [eid]
            assert s2.get_evidence(eid).data == "raw data"
            assert [a["agent_id"] for a in s2.list_agents()] == ["bot"]
        finally:
            s2.close()


class TestLifecycle:
    def test_double_close_is_safe(self, tmp_path) -> None:
        s = lattice.init(str(tmp_path))
        s.close()
        s.close()  # must not raise

    def test_use_after_close_raises(self, tmp_path) -> None:
        s = lattice.init(str(tmp_path))
        s.close()
        with pytest.raises(sqlite3.ProgrammingError):
            s.claim_count()
