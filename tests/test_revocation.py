"""Tests for lattice.revocation — Revocation Waterfall."""

import pytest

import lattice
from lattice.exceptions import (
    AlreadyRevokedError,
    ClaimNotFoundError,
    UnauthorizedRevocationError,
)
from lattice.store import LatticeStore


@pytest.fixture
def store() -> LatticeStore:
    return lattice.init(":memory:")


@pytest.fixture
def chain(store: LatticeStore):
    """Build a 3-claim chain: evidence → claim_a → claim_b → claim_c."""
    agent = store.agent("analyst", role="analyst")

    eid = store.evidence("raw dns output for example.com")

    claim_a = agent.claim(
        assertion="example.com resolves to 93.184.216.34",
        evidence=[eid],
        confidence=0.99,
        method="tool:nslookup",
    )
    claim_b = agent.claim(
        assertion="example.com and example.org share infra",
        evidence=[claim_a.claim_id],
        confidence=0.85,
        method="llm:analysis",
    )
    claim_c = agent.claim(
        assertion="Both domains are operated by IANA",
        evidence=[claim_b.claim_id],
        confidence=0.70,
        method="llm:synthesis",
    )
    return agent, eid, claim_a, claim_b, claim_c


class TestRevokeClaim:
    def test_basic_revocation(self, store: LatticeStore, chain):
        agent, eid, claim_a, claim_b, claim_c = chain
        result = store.revoke_claim(claim_a.claim_id, agent.agent_id)
        assert result.revoked_claim_id == claim_a.claim_id
        # claim_b depends on claim_a, claim_c depends on claim_b
        assert claim_b.claim_id in result.compromised_claim_ids
        assert claim_c.claim_id in result.compromised_claim_ids
        assert result.total_affected == 3

    def test_revoke_leaf(self, store: LatticeStore, chain):
        """Revoking a leaf (no downstream) affects only itself."""
        agent, eid, claim_a, claim_b, claim_c = chain
        result = store.revoke_claim(claim_c.claim_id, agent.agent_id)
        assert result.revoked_claim_id == claim_c.claim_id
        assert result.compromised_claim_ids == []
        assert result.total_affected == 1

    def test_unauthorized_revocation(self, store: LatticeStore, chain):
        """Cannot revoke a claim signed by another agent."""
        _, _, claim_a, _, _ = chain
        intruder = store.agent("intruder", role="hacker")
        with pytest.raises(UnauthorizedRevocationError):
            store.revoke_claim(claim_a.claim_id, intruder.agent_id)

    def test_governance_override(self, store: LatticeStore, chain):
        """Governance flag bypasses the signer check."""
        _, _, claim_a, _, _ = chain
        admin = store.agent("admin", role="governance")
        result = store.revoke_claim(
            claim_a.claim_id, admin.agent_id, reason="Policy violation", governance=True
        )
        assert result.revoked_claim_id == claim_a.claim_id

    def test_already_revoked(self, store: LatticeStore, chain):
        agent, _, claim_a, _, _ = chain
        store.revoke_claim(claim_a.claim_id, agent.agent_id)
        with pytest.raises(AlreadyRevokedError):
            store.revoke_claim(claim_a.claim_id, agent.agent_id)

    def test_claim_not_found(self, store: LatticeStore):
        with pytest.raises(ClaimNotFoundError):
            store.revoke_claim("nonexistent_id", "some_agent")


class TestClaimStatus:
    def test_valid_by_default(self, store: LatticeStore, chain):
        _, _, claim_a, _, _ = chain
        assert store.get_claim_status(claim_a.claim_id) == "VALID"

    def test_revoked_status(self, store: LatticeStore, chain):
        agent, _, claim_a, _, _ = chain
        store.revoke_claim(claim_a.claim_id, agent.agent_id)
        assert store.get_claim_status(claim_a.claim_id) == "REVOKED"

    def test_compromised_status(self, store: LatticeStore, chain):
        agent, _, claim_a, claim_b, claim_c = chain
        store.revoke_claim(claim_a.claim_id, agent.agent_id)
        assert store.get_claim_status(claim_b.claim_id) == "COMPROMISED"
        assert store.get_claim_status(claim_c.claim_id) == "COMPROMISED"

    def test_is_revoked(self, store: LatticeStore, chain):
        agent, _, claim_a, _, _ = chain
        assert not store.is_revoked(claim_a.claim_id)
        store.revoke_claim(claim_a.claim_id, agent.agent_id)
        assert store.is_revoked(claim_a.claim_id)

    def test_is_compromised(self, store: LatticeStore, chain):
        agent, _, claim_a, claim_b, _ = chain
        assert not store.is_compromised(claim_b.claim_id)
        store.revoke_claim(claim_a.claim_id, agent.agent_id)
        assert store.is_compromised(claim_b.claim_id)


class TestListRevocations:
    def test_empty(self, store: LatticeStore):
        assert store.list_revocations() == []

    def test_after_revocation(self, store: LatticeStore, chain):
        agent, _, claim_a, _, _ = chain
        store.revoke_claim(claim_a.claim_id, agent.agent_id, reason="Stale data")
        revs = store.list_revocations()
        assert len(revs) == 1
        assert revs[0].revoked_claim_id == claim_a.claim_id
        assert revs[0].revoked_by == agent.agent_id
        assert revs[0].reason == "Stale data"


class TestDiamondDAG:
    """Test a diamond-shaped DAG: A → B, A → C, B → D, C → D."""

    def test_diamond_waterfall(self, store: LatticeStore):
        agent = store.agent("analyst", role="analyst")
        a = agent.claim(assertion="Root finding", confidence=0.9, method="tool:scan")
        b = agent.claim(assertion="Branch B", evidence=[a.claim_id], confidence=0.8, method="llm:analysis")
        c = agent.claim(assertion="Branch C", evidence=[a.claim_id], confidence=0.8, method="llm:analysis")
        d = agent.claim(assertion="Conclusion", evidence=[b.claim_id, c.claim_id], confidence=0.7, method="llm:synthesis")

        result = store.revoke_claim(a.claim_id, agent.agent_id)
        # All of B, C, D should be compromised
        compromised_set = set(result.compromised_claim_ids)
        assert b.claim_id in compromised_set
        assert c.claim_id in compromised_set
        assert d.claim_id in compromised_set
        assert result.total_affected == 4
