# Contributing to LATTICE

## Getting Started

```bash
git clone https://github.com/thunderstornX/lattice.git
cd lattice
pip install -e ".[dev]"
pytest
```

All 89 tests should pass before you start.

## Code Standards

- Type hints on every function
- Docstrings on every public function and class
- Functions under 20 lines (split if longer)
- Specific exceptions (never bare `except:`)
- No magic numbers
- Python 3.10+ required

## Running Tests

```bash
pytest tests/ -v
```

## Running Benchmarks

```bash
PYTHONPATH=. python3 benchmarks/run_benchmarks.py
```

## What We Need

### Priority: Framework Adapters

Adapter plugins that hook into LangGraph, CrewAI, or AutoGen callback/event systems and automatically generate LATTICE claims. The ideal adapter requires zero changes to existing agent code.

### Priority: Bayesian Confidence Propagation

The current effective confidence uses min-propagation (worst-case correct under correlated sources). Pluggable modules for alternative propagation strategies (Bayesian, weighted combination) behind a clean interface would be valuable for different threat models.

### Priority: Scalability

Revocation waterfall and cycle detection show super-linear scaling past 1,000 claims. Pre-computed dependency indices or incremental transitive closure maintenance would help. See the paper (Section 6.3) for details.

### Always Welcome

- Bug reports with reproducible examples
- Documentation improvements
- Performance work (especially for large DAGs)
- Test coverage improvements
- Real-world case studies using LATTICE

## Pull Request Process

1. Fork the repo
2. Create a branch from `master`
3. Write tests for new functionality
4. Make sure all tests pass
5. Open a PR with a clear description of what changed and why

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
