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

    def test_trace_missing_id(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            runner.invoke(cli, ["init", tmp])
            result = runner.invoke(cli, ["trace", "deadbeef", "-d", tmp])
            assert result.exit_code == 1
            assert "Claim not found" in result.output
