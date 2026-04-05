"""Tests for lattice.dashboard — FastAPI API endpoints."""

import pytest

import lattice
from lattice.dashboard import create_app
from lattice.store import LatticeStore

# We need httpx for testing FastAPI with TestClient
try:
    from starlette.testclient import TestClient
except ImportError:
    pytest.skip("starlette not installed", allow_module_level=True)


@pytest.fixture
def populated_store(tmp_path) -> str:
    """Create a LATTICE store with sample data and return the db path."""
    store = lattice.init(str(tmp_path))
    agent = store.agent("test-agent", role="analyst")

    eid = store.evidence("raw evidence data")
    claim_a = agent.claim(
        assertion="Finding A",
        evidence=[eid],
        confidence=0.95,
        method="tool:scan",
    )
    claim_b = agent.claim(
        assertion="Conclusion B based on A",
        evidence=[claim_a.claim_id],
        confidence=0.80,
        method="llm:analysis",
    )

    db_path = str(tmp_path / ".lattice" / "lattice.db")
    store.close()
    return db_path


@pytest.fixture
def client(populated_store: str) -> TestClient:
    app = create_app(populated_store)
    return TestClient(app)


class TestDashboardHTML:
    def test_index_serves_html(self, client: TestClient):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "LATTICE Dashboard" in resp.text
        assert "<svg" in resp.text


class TestAgentsEndpoint:
    def test_list_agents(self, client: TestClient):
        resp = client.get("/api/agents")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["agent_id"] == "test-agent"


class TestClaimsEndpoint:
    def test_list_claims(self, client: TestClient):
        resp = client.get("/api/claims")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        for claim in data:
            assert "status" in claim
            assert claim["status"] == "VALID"

    def test_get_claim_detail(self, client: TestClient):
        # Get the list first, then fetch one
        claims = client.get("/api/claims").json()
        claim_id = claims[0]["claim_id"]
        resp = client.get(f"/api/claims/{claim_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["claim_id"] == claim_id
        assert "signature_valid" in data
        assert data["signature_valid"] is True

    def test_claim_not_found(self, client: TestClient):
        resp = client.get("/api/claims/nonexistent_id_that_does_not_exist")
        assert resp.status_code == 404


class TestTraceEndpoint:
    def test_trace_claim(self, client: TestClient):
        claims = client.get("/api/claims").json()
        # Find the conclusion (the one with a claim reference as evidence)
        conclusion = [c for c in claims if any(
            e in [cc["claim_id"] for cc in claims] for e in c.get("evidence", [])
        )]
        if conclusion:
            cid = conclusion[0]["claim_id"]
            resp = client.get(f"/api/claims/{cid}/trace")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data) >= 2  # conclusion + its dependency


class TestVerifyEndpoint:
    def test_verify_claim(self, client: TestClient):
        claims = client.get("/api/claims").json()
        cid = claims[0]["claim_id"]
        resp = client.get(f"/api/claims/{cid}/verify")
        assert resp.status_code == 200
        data = resp.json()
        assert data["content_integrity"] is True
        assert data["signature_valid"] is True


class TestGraphEndpoint:
    def test_graph_structure(self, client: TestClient):
        resp = client.get("/api/graph")
        assert resp.status_code == 200
        data = resp.json()
        assert "nodes" in data
        assert "edges" in data
        assert len(data["nodes"]) >= 2
        assert len(data["edges"]) >= 1
        # Check node structure
        for node in data["nodes"]:
            assert "id" in node
            assert "status" in node
            assert "type" in node


class TestRevocationsEndpoint:
    def test_empty_revocations(self, client: TestClient):
        resp = client.get("/api/revocations")
        assert resp.status_code == 200
        assert resp.json() == []


class TestStatsEndpoint:
    def test_stats(self, client: TestClient):
        resp = client.get("/api/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_agents"] == 1
        assert data["total_claims"] == 2
        assert "total_revocations" in data
