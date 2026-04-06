# Contributing to LATTICE

## Getting Started

```bash
git clone <private-repo-url>
cd lattice
pip install -e . pytest
PYTHONPATH=. pytest
```

All 41 tests should pass before you start.

## Code Standards

- Type hints on every function
- Docstrings on every public function and class
- Functions under 20 lines (split if longer)
- Specific exceptions (never bare `except:`)
- No magic numbers

## Running Tests

```bash
PYTHONPATH=. pytest tests/ -v
```

## What We Need

### Priority: Framework Adapters (v0.2)

If you use LangGraph, CrewAI, or AutoGen, we need adapter plugins that hook into those frameworks' callback/event systems and automatically generate LATTICE claims. The ideal adapter requires zero changes to existing agent code.

### Priority: Confidence Propagation (v0.3)

Pluggable modules for propagating confidence changes through the DAG. If a leaf claim's confidence drops, how should parent claims update? We want multiple strategies (simple decay, Bayesian, configurable) behind a clean interface.

### Priority: Web Dashboard (v0.4)

Interactive DAG visualization. The main interaction is clicking a conclusion node and seeing its full evidence chain highlighted. Tech: probably a small FastAPI server serving a static frontend.

### Always Welcome

- Bug reports with reproducible examples
- Documentation improvements
- Performance work (especially for large DAGs with 10k+ claims)
- Test coverage improvements

## Pull Request Process

1. Fork the repo
2. Create a branch from `main`
3. Write tests for new functionality
4. Make sure all tests pass
5. Open a PR with a clear description of what changed and why

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
