"""Tests for lattice.dag."""

from __future__ import annotations

import pytest

from lattice.dag import AuditIssue, audit, stats, trace, verify_all
from lattice.exceptions import ClaimNotFoundError
from lattice.store import LatticeStore


class TestTrace:
    def test_single_claim(self, store: LatticeStore) -> None:
        agent = store.agent("bot")
        c = agent.claim("leaf", method="m")
        chain = trace(store, c.claim_id)
        assert len(chain) == 1

    def test_chain(self, store: LatticeStore) -> None:
        agent = store.agent("bot")
        eid = store.evidence("raw")
        c1 = agent.claim("base", evidence=[eid], method="m")
        c2 = agent.claim("derived", evidence=[c1.claim_id], method="m")
        chain = trace(store, c2.claim_id)
        assert len(chain) == 2
        assert chain[0].claim_id == c2.claim_id
        assert chain[1].claim_id == c1.claim_id

    def test_not_found(self, store: LatticeStore) -> None:
        with pytest.raises(ClaimNotFoundError):
            trace(store, "0" * 64)


class TestAudit:
    def test_no_issues(self, store: LatticeStore) -> None:
        agent = store.agent("bot")
        eid = store.evidence("data")
        agent.claim("ok", evidence=[eid], method="m")
        issues = audit(store)
        assert len(issues) == 0

    def test_unsupported(self, store: LatticeStore) -> None:
        agent = store.agent("bot")
        agent.claim("no evidence", method="m")
        issues = audit(store)
        types = [i.issue_type for i in issues]
        assert "unsupported" in types

    def test_low_confidence(self, store: LatticeStore) -> None:
        agent = store.agent("bot")
        eid = store.evidence("d")
        agent.claim("shaky", evidence=[eid], confidence=0.1, method="m")
        issues = audit(store, confidence_threshold=0.3)
        types = [i.issue_type for i in issues]
        assert "low_confidence" in types

    def test_broken_ref(self, store: LatticeStore) -> None:
        agent = store.agent("bot")
        agent.claim("broken", evidence=["nonexistent" * 4], method="m")
        issues = audit(store)
        types = [i.issue_type for i in issues]
        assert "broken_reference" in types


class TestVerify:
    def test_valid_signatures(self, store: LatticeStore) -> None:
        agent = store.agent("bot")
        agent.claim("signed", method="m")
        results = verify_all(store)
        assert all(r.valid for r in results)

    def test_empty(self, store: LatticeStore) -> None:
        assert verify_all(store) == []

    def test_verify_after_key_rotation(self, store: LatticeStore) -> None:
        agent = store.agent("bot")
        agent.claim("before-rotate", method="m")
        store.rotate_agent_key("bot")
        new_agent = store.get_agent("bot")
        new_agent.claim("after-rotate", method="m")
        results = verify_all(store)
        assert all(r.valid for r in results)


class TestStats:
    def test_basic(self, store: LatticeStore) -> None:
        agent = store.agent("bot")
        store.evidence("d")
        agent.claim("x", confidence=0.8, method="tool:test")
        s = stats(store)
        assert s["total_agents"] == 1
        assert s["total_claims"] == 1
        assert s["total_evidence"] == 1
        assert s["avg_confidence"] == 0.8
