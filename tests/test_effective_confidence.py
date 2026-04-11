"""Tests for effective confidence computation."""

from __future__ import annotations

from lattice.dag import effective_confidence, effective_confidence_bulk, audit
from lattice.store import LatticeStore


class TestEffectiveConfidence:
    def test_single_claim_no_evidence(self, store: LatticeStore) -> None:
        """A claim with no evidence has effective = stated."""
        agent = store.agent("bot")
        c = agent.claim("standalone", confidence=0.8, method="m")
        assert effective_confidence(store, c.claim_id) == 0.8

    def test_chain_min_propagation(self, store: LatticeStore) -> None:
        """Effective confidence is the min across the ancestor chain."""
        agent = store.agent("bot")
        leaf = agent.claim("leaf", confidence=0.6, method="m")
        mid = agent.claim("mid", evidence=[leaf.claim_id], confidence=0.9, method="m")
        top = agent.claim("top", evidence=[mid.claim_id], confidence=0.95, method="m")

        # top's stated is 0.95, but leaf is 0.6 so effective should be 0.6
        assert effective_confidence(store, top.claim_id) == 0.6
        assert effective_confidence(store, mid.claim_id) == 0.6
        assert effective_confidence(store, leaf.claim_id) == 0.6

    def test_diamond_dag(self, store: LatticeStore) -> None:
        """Diamond: A depends on B and C, both depend on D."""
        agent = store.agent("bot")
        d = agent.claim("D", confidence=0.5, method="m")
        b = agent.claim("B", evidence=[d.claim_id], confidence=0.9, method="m")
        c = agent.claim("C", evidence=[d.claim_id], confidence=0.8, method="m")
        a = agent.claim("A", evidence=[b.claim_id, c.claim_id], confidence=0.95, method="m")

        # Effective of A should be 0.5 (D is the floor)
        assert effective_confidence(store, a.claim_id) == 0.5

    def test_evidence_leaf_treated_as_1(self, store: LatticeStore) -> None:
        """Raw evidence refs don't lower confidence (treated as 1.0)."""
        agent = store.agent("bot")
        eid = store.evidence("raw data")
        c = agent.claim("uses evidence", evidence=[eid], confidence=0.85, method="m")
        assert effective_confidence(store, c.claim_id) == 0.85

    def test_mixed_evidence_and_claims(self, store: LatticeStore) -> None:
        """Mix of raw evidence and claim refs; min is from claim chain."""
        agent = store.agent("bot")
        eid = store.evidence("raw data")
        low = agent.claim("low", confidence=0.4, method="m")
        top = agent.claim("top", evidence=[eid, low.claim_id], confidence=0.9, method="m")
        assert effective_confidence(store, top.claim_id) == 0.4

    def test_own_confidence_is_floor(self, store: LatticeStore) -> None:
        """If the claim itself has the lowest confidence, that wins."""
        agent = store.agent("bot")
        high = agent.claim("high", confidence=0.99, method="m")
        low_top = agent.claim("low_top", evidence=[high.claim_id], confidence=0.3, method="m")
        assert effective_confidence(store, low_top.claim_id) == 0.3


class TestEffectiveConfidenceBulk:
    def test_bulk_matches_individual(self, store: LatticeStore) -> None:
        """Bulk computation should match individual calls."""
        agent = store.agent("bot")
        a = agent.claim("a", confidence=0.5, method="m")
        b = agent.claim("b", evidence=[a.claim_id], confidence=0.9, method="m")
        c = agent.claim("c", evidence=[b.claim_id], confidence=0.95, method="m")

        bulk = effective_confidence_bulk(store)
        assert bulk[a.claim_id] == effective_confidence(store, a.claim_id)
        assert bulk[b.claim_id] == effective_confidence(store, b.claim_id)
        assert bulk[c.claim_id] == effective_confidence(store, c.claim_id)

    def test_empty_store(self, store: LatticeStore) -> None:
        """Empty store returns empty dict."""
        assert effective_confidence_bulk(store) == {}


class TestAuditInflatedConfidence:
    def test_detects_inflation(self, store: LatticeStore) -> None:
        """Audit flags claims where stated > effective."""
        agent = store.agent("bot")
        leaf = agent.claim("weak leaf", confidence=0.3, method="m")
        top = agent.claim("strong claim", evidence=[leaf.claim_id], confidence=0.95, method="m")

        issues = audit(store, confidence_threshold=0.1)
        inflated = [i for i in issues if i.issue_type == "inflated_confidence"]
        assert len(inflated) == 1
        assert inflated[0].claim_id == top.claim_id

    def test_no_inflation_when_honest(self, store: LatticeStore) -> None:
        """No inflated_confidence when stated <= effective."""
        agent = store.agent("bot")
        leaf = agent.claim("strong leaf", confidence=0.9, method="m")
        top = agent.claim("honest", evidence=[leaf.claim_id], confidence=0.7, method="m")

        issues = audit(store, confidence_threshold=0.1)
        inflated = [i for i in issues if i.issue_type == "inflated_confidence"]
        assert len(inflated) == 0

    def test_no_inflation_on_unsupported(self, store: LatticeStore) -> None:
        """Claims with no evidence are not flagged as inflated."""
        agent = store.agent("bot")
        agent.claim("no evidence", confidence=0.99, method="m")

        issues = audit(store)
        inflated = [i for i in issues if i.issue_type == "inflated_confidence"]
        assert len(inflated) == 0
