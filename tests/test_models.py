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


class TestHashSensitivity:
    """compute_claim_id must change if ANY content field changes."""

    @pytest.mark.parametrize(
        "field, val_a, val_b",
        [
            ("agent_id", "a", "b"),
            ("assertion", "x", "y"),
            ("method", "m1", "m2"),
            ("timestamp", 1.0, 2.0),
            ("metadata", {}, {"k": "v"}),
            ("evidence", ["e1"], ["e1", "e2"]),
        ],
    )
    def test_changing_field_changes_id(self, field, val_a, val_b) -> None:
        base = dict(agent_id="a", assertion="x", evidence=["e1"], method="m",
                    timestamp=1.0, metadata={})
        a = dict(base, **{field: val_a})
        b = dict(base, **{field: val_b})
        assert compute_claim_id(**a) != compute_claim_id(**b)


class TestBoundariesAndTimestamp:
    @pytest.mark.parametrize("conf", [0.0, 0.5, 1.0])
    def test_confidence_boundaries_valid(self, conf: float) -> None:
        c = Claim.create(agent_id="a", assertion="x", evidence=[], confidence=conf, method="m")
        assert c.confidence == conf

    def test_zero_timestamp_is_honored(self) -> None:
        # Regression: timestamp=0.0 (a valid Unix epoch) must NOT be replaced
        # by time.time() via a falsy `or` — the claim_id must stay reproducible.
        c = Claim.create(agent_id="a", assertion="x", evidence=[], confidence=0.5,
                         method="m", timestamp=0.0)
        assert c.timestamp == 0.0

    def test_evidence_zero_created_at_is_honored(self) -> None:
        ev = Evidence.create("data", created_at=0.0)
        assert ev.created_at == 0.0

    def test_from_dict_missing_optional_keys(self) -> None:
        minimal = {
            "claim_id": "x" * 64, "agent_id": "a", "assertion": "y",
            "evidence": [], "confidence": 0.5, "method": "m", "timestamp": 1.0,
        }
        c = Claim.from_dict(minimal)
        assert c.metadata == {}
        assert c.signature == ""
