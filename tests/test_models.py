"""Tests for lattice.models."""

from __future__ import annotations

import pytest

from lattice.exceptions import InvalidConfidenceError
from lattice.models import Claim, Evidence, compute_claim_id


class TestComputeClaimId:
    def test_deterministic(self) -> None:
        args = dict(agent_id="a", assertion="x", evidence=["e1"], method="m", timestamp=1.0, metadata={})
        assert compute_claim_id(**args) == compute_claim_id(**args)

    def test_different_assertion(self) -> None:
        base = dict(agent_id="a", evidence=[], method="m", timestamp=1.0, metadata={})
        assert compute_claim_id(assertion="A", **base) != compute_claim_id(assertion="B", **base)

    def test_evidence_order_irrelevant(self) -> None:
        base = dict(agent_id="a", assertion="x", method="m", timestamp=1.0, metadata={})
        assert compute_claim_id(evidence=["e1", "e2"], **base) == compute_claim_id(evidence=["e2", "e1"], **base)

    def test_hex_length(self) -> None:
        cid = compute_claim_id("a", "b", [], "m", 0.0, {})
        assert len(cid) == 64
        assert all(c in "0123456789abcdef" for c in cid)


class TestEvidence:
    def test_compute_id_deterministic(self) -> None:
        assert Evidence.compute_id("hello") == Evidence.compute_id("hello")

    def test_compute_id_different(self) -> None:
        assert Evidence.compute_id("a") != Evidence.compute_id("b")

    def test_create(self) -> None:
        ev = Evidence.create("test data", "text/plain")
        assert ev.data == "test data"
        assert ev.evidence_id == Evidence.compute_id("test data")


class TestClaim:
    def test_create(self) -> None:
        c = Claim.create(agent_id="a", assertion="x", evidence=[], confidence=0.5, method="m")
        assert c.agent_id == "a"
        assert len(c.claim_id) == 64

    def test_invalid_confidence_high(self) -> None:
        with pytest.raises(InvalidConfidenceError):
            Claim.create(agent_id="a", assertion="x", evidence=[], confidence=1.5, method="m")

    def test_invalid_confidence_low(self) -> None:
        with pytest.raises(InvalidConfidenceError):
            Claim.create(agent_id="a", assertion="x", evidence=[], confidence=-0.1, method="m")

    def test_to_dict_roundtrip(self) -> None:
        c = Claim.create(agent_id="a", assertion="x", evidence=["e1"], confidence=0.9, method="m", metadata={"k": "v"})
        d = c.to_dict()
        c2 = Claim.from_dict(d)
        assert c.claim_id == c2.claim_id
        assert c.metadata == c2.metadata
