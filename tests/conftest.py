"""Shared pytest fixtures."""

from __future__ import annotations

import pytest

import lattice
from lattice.agent import AgentHandle
from lattice.store import LatticeStore


@pytest.fixture()
def store() -> LatticeStore:
    """Fresh in-memory store."""
    s = lattice.init(":memory:")
    yield s
    s.close()


@pytest.fixture()
def agent(store: LatticeStore) -> AgentHandle:
    """A registered test agent."""
    return store.agent("test-agent", role="tester", description="Unit test agent")
