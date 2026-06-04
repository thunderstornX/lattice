"""Tests for lattice.cli."""

from __future__ import annotations

import json
import os

from lattice.cli import cli
from lattice.store import DB_FILENAME, LatticeStore


class TestCLI:
    def test_init(self, cli_runner, tmp_path) -> None:
        result = cli_runner.invoke(cli, ["init", str(tmp_path)])
        assert result.exit_code == 0
        assert (tmp_path / ".lattice" / "lattice.db").exists()

    def test_agents_empty(self, cli_store) -> None:
        runner, directory = cli_store
        result = runner.invoke(cli, ["agents", "-d", directory])
        assert result.exit_code == 0
        assert "No agents" in result.output

    def test_stats_empty(self, cli_store) -> None:
        runner, directory = cli_store
        result = runner.invoke(cli, ["stats", "-d", directory])
        assert result.exit_code == 0

    def test_export(self, cli_store) -> None:
        runner, directory = cli_store
        out = os.path.join(directory, "out.json")
        result = runner.invoke(cli, ["export", out, "-d", directory])
        assert result.exit_code == 0
        with open(out) as f:
            data = json.load(f)
        assert "claims" in data

    @staticmethod
    def _populate(directory: str) -> str:
        """Create a small evidence-backed claim chain in directory/.lattice."""
        store = LatticeStore(os.path.join(directory, ".lattice", DB_FILENAME))
        agent = store.agent("bot")
        eid = store.evidence("raw observation")
        base = agent.claim("base fact", evidence=[eid], method="m",
                           confidence=0.6)
        derived = agent.claim("derived conclusion",
                              evidence=[base.claim_id], method="m",
                              confidence=0.95)
        store.close()
        return derived.claim_id

    def test_claims_on_populated_store(self, cli_store) -> None:
        # Regression: `claims` computes effective confidence AFTER querying
        # the store; it must not close the store first (would raise
        # sqlite3.ProgrammingError on any non-empty store).
        runner, directory = cli_store
        self._populate(directory)
        result = runner.invoke(cli, ["claims", "-d", directory])
        assert result.exception is None, result.exception
        assert result.exit_code == 0
        assert "derived conclusion" in result.output
        # min-propagation: derived (0.95) is capped by base (0.60)
        assert "0.60" in result.output

    def test_trace_on_populated_store(self, cli_store) -> None:
        # Regression: same use-after-close guard for `trace`.
        runner, directory = cli_store
        cid = self._populate(directory)
        result = runner.invoke(cli, ["trace", cid, "-d", directory])
        assert result.exception is None, result.exception
        assert result.exit_code == 0
