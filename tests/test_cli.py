"""Tests for lattice.cli."""

from __future__ import annotations

import json
import os
import tempfile

from click.testing import CliRunner

from lattice.cli import cli


class TestCLI:
    def test_init(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            result = runner.invoke(cli, ["init", tmp])
            assert result.exit_code == 0
            assert os.path.exists(os.path.join(tmp, ".lattice", "lattice.db"))

    def test_agents_empty(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            runner.invoke(cli, ["init", tmp])
            result = runner.invoke(cli, ["agents", "-d", tmp])
            assert result.exit_code == 0
            assert "No agents" in result.output

    def test_stats_empty(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            runner.invoke(cli, ["init", tmp])
            result = runner.invoke(cli, ["stats", "-d", tmp])
            assert result.exit_code == 0

    def test_export(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            runner.invoke(cli, ["init", tmp])
            out = os.path.join(tmp, "out.json")
            result = runner.invoke(cli, ["export", out, "-d", tmp])
            assert result.exit_code == 0
            with open(out) as f:
                data = json.load(f)
            assert "claims" in data

    @staticmethod
    def _populate(tmp: str) -> str:
        """Create a small evidence-backed claim chain in tmp/.lattice."""
        from lattice.store import LatticeStore, DB_FILENAME
        store = LatticeStore(os.path.join(tmp, ".lattice", DB_FILENAME))
        agent = store.agent("bot")
        eid = store.evidence("raw observation")
        base = agent.claim("base fact", evidence=[eid], method="m",
                           confidence=0.6)
        derived = agent.claim("derived conclusion",
                              evidence=[base.claim_id], method="m",
                              confidence=0.95)
        store.close()
        return derived.claim_id

    def test_claims_on_populated_store(self) -> None:
        # Regression: `claims` computes effective confidence AFTER querying
        # the store; it must not close the store first (would raise
        # sqlite3.ProgrammingError on any non-empty store).
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            runner.invoke(cli, ["init", tmp])
            self._populate(tmp)
            result = runner.invoke(cli, ["claims", "-d", tmp])
            assert result.exception is None, result.exception
            assert result.exit_code == 0
            assert "derived conclusion" in result.output
            # min-propagation: derived (0.95) is capped by base (0.60)
            assert "0.60" in result.output

    def test_trace_on_populated_store(self) -> None:
        # Regression: same use-after-close guard for `trace`.
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            runner.invoke(cli, ["init", tmp])
            cid = self._populate(tmp)
            result = runner.invoke(cli, ["trace", cid, "-d", tmp])
            assert result.exception is None, result.exception
            assert result.exit_code == 0
