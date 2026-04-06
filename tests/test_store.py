"""Tests for lattice.store."""

from __future__ import annotations

import sqlite3

import pytest

import lattice
from lattice.exceptions import (
    AgentKeyLockedError,
    AgentNotFoundError,
    AmbiguousClaimIdError,
    ClaimNotFoundError,
    EvidenceNotFoundError,
)
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

    def test_rotate_key(self, store: LatticeStore) -> None:
        a = store.agent("bot")
        first = a.public_key
        rotated = store.rotate_agent_key("bot")
        assert rotated.public_key != first

    def test_revoke_agent(self, store: LatticeStore) -> None:
        store.agent("bot")
        store.revoke_agent("bot")
        with pytest.raises(AgentKeyLockedError):
            store.get_agent("bot")


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

    def test_resolve_claim_prefix(self, store: LatticeStore) -> None:
        agent = store.agent("bot")
        c = agent.claim("x", method="m")
        assert store.resolve_claim_id_prefix(c.claim_id[:12]) == c.claim_id

    def test_resolve_claim_prefix_missing(self, store: LatticeStore) -> None:
        with pytest.raises(ClaimNotFoundError):
            store.resolve_claim_id_prefix("deadbeef")

    def test_resolve_claim_prefix_ambiguous(self, store: LatticeStore) -> None:
        conn = store._conn  # noqa: SLF001
        row = conn.execute(
            "SELECT claim_id, agent_id, assertion, evidence, confidence, method, timestamp, metadata, signature FROM claims LIMIT 1"
        ).fetchone()
        if row is None:
            agent = store.agent("bot")
            c = agent.claim("x", method="m")
            row = conn.execute(
                "SELECT claim_id, agent_id, assertion, evidence, confidence, method, timestamp, metadata, signature FROM claims WHERE claim_id=?",
                (c.claim_id,),
            ).fetchone()
        prefix = row[0][:8]
        conn.execute(
            "INSERT OR REPLACE INTO claims (claim_id, agent_id, assertion, evidence, confidence, method, timestamp, metadata, signature) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                prefix + "f" * (64 - len(prefix)),
                row[1],
                row[2],
                row[3],
                row[4],
                row[5],
                row[6] + 1,
                row[7],
                row[8],
            ),
        )
        conn.commit()
        with pytest.raises(AmbiguousClaimIdError):
            store.resolve_claim_id_prefix(prefix)


class TestExport:
    def test_export_json(self, store: LatticeStore) -> None:
        agent = store.agent("bot")
        agent.claim("test", method="m")
        data = store.export_json()
        assert data["stats"]["claims"] == 1
        assert len(data["claims"]) == 1


class TestEncryptionAndMigration:
    def test_encrypted_keys_require_passphrase(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        root = str(tmp_path)
        s1 = lattice.init(root, passphrase="secret")
        s1.agent("bot")
        s1.close()

        s2 = lattice.init(root)
        with pytest.raises(AgentKeyLockedError):
            s2.get_agent("bot")
        s2.close()

        s3 = lattice.init(root, passphrase="secret")
        a = s3.get_agent("bot")
        assert a.agent_id == "bot"
        s3.close()

    def test_schema_migration_from_v1(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        db = tmp_path / ".lattice" / "lattice.db"
        db.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db))
        conn.executescript(
            """
            CREATE TABLE agents (
                agent_id TEXT PRIMARY KEY,
                role TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                public_key BLOB NOT NULL,
                private_key BLOB NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE TABLE evidence (
                evidence_id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                content_type TEXT NOT NULL DEFAULT 'text/plain',
                created_at REAL NOT NULL
            );
            CREATE TABLE claims (
                claim_id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                assertion TEXT NOT NULL,
                evidence TEXT NOT NULL DEFAULT '[]',
                confidence REAL NOT NULL,
                method TEXT NOT NULL,
                timestamp REAL NOT NULL,
                metadata TEXT NOT NULL DEFAULT '{}',
                signature TEXT NOT NULL DEFAULT ''
            );
            """
        )
        conn.commit()
        conn.close()

        store = lattice.init(str(tmp_path))
        cols = {
            r[1]
            for r in store._conn.execute("PRAGMA table_info(agents)").fetchall()  # noqa: SLF001
        }
        assert "key_status" in cols
        assert "key_kind" in cols
        ver = store._conn.execute("SELECT version FROM schema_info LIMIT 1").fetchone()[0]  # noqa: SLF001
        assert ver == 2
        store.close()
