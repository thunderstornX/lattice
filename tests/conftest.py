"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

import lattice
from lattice.agent import AgentHandle
from lattice.cli import cli
from lattice.store import LatticeStore


@pytest.fixture()
def store() -> LatticeStore:
    """Fresh in-memory store (closed on teardown)."""
    s = lattice.init(":memory:")
    yield s
    s.close()


@pytest.fixture()
def file_store(tmp_path: Path) -> LatticeStore:
    """Fresh file-backed store under a temp dir (closed on teardown).

    Use this instead of the in-memory ``store`` when a test needs real
    on-disk persistence (e.g. WAL mode, or surviving a close/reopen cycle).
    """
    s = lattice.init(str(tmp_path))
    yield s
    s.close()


@pytest.fixture()
def agent(store: LatticeStore) -> AgentHandle:
    """A registered test agent."""
    return store.agent("test-agent", role="tester", description="Unit test agent")


@pytest.fixture()
def linear_chain(store: LatticeStore):
    """evidence -> a -> b -> c, with descending confidence.

    Returns ``(agent, eid, claim_a, claim_b, claim_c)``.
    """
    agent = store.agent("analyst", role="analyst")
    eid = store.evidence("raw dns output for example.com")
    claim_a = agent.claim(
        assertion="example.com resolves to 93.184.216.34",
        evidence=[eid], confidence=0.99, method="tool:nslookup",
    )
    claim_b = agent.claim(
        assertion="example.com and example.org share infra",
        evidence=[claim_a.claim_id], confidence=0.85, method="llm:analysis",
    )
    claim_c = agent.claim(
        assertion="Both domains are operated by IANA",
        evidence=[claim_b.claim_id], confidence=0.70, method="llm:synthesis",
    )
    return agent, eid, claim_a, claim_b, claim_c


@pytest.fixture()
def diamond_dag(store: LatticeStore):
    """Diamond DAG: A -> B, A -> C, {B, C} -> D.

    Returns ``(agent, a, b, c, d)``.
    """
    agent = store.agent("analyst", role="analyst")
    a = agent.claim("Root finding", confidence=0.9, method="tool:scan")
    b = agent.claim("Branch B", evidence=[a.claim_id], confidence=0.8, method="llm:analysis")
    c = agent.claim("Branch C", evidence=[a.claim_id], confidence=0.8, method="llm:analysis")
    d = agent.claim(
        "Conclusion", evidence=[b.claim_id, c.claim_id], confidence=0.7, method="llm:synthesis",
    )
    return agent, a, b, c, d


@pytest.fixture()
def cli_runner() -> CliRunner:
    """Click ``CliRunner`` for invoking the lattice CLI."""
    return CliRunner()


@pytest.fixture()
def cli_store(cli_runner: CliRunner, tmp_path: Path) -> tuple[CliRunner, str]:
    """An initialized CLI store directory.

    Runs ``lattice init`` in a temp dir and returns ``(runner, directory)``
    so tests can immediately invoke commands with ``-d <directory>``.
    """
    directory = str(tmp_path)
    cli_runner.invoke(cli, ["init", directory])
    return cli_runner, directory
