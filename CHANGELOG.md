# Changelog

## [1.2.0] - 2026-04-11

### Added
- **Effective confidence** (min-propagation): `store.effective_confidence(claim_id)` and `effective_confidence_bulk(store)` compute the minimum confidence across the full ancestor chain, ensuring high-confidence conclusions cannot mask low-confidence evidence
- **Inflated confidence audit**: `audit()` now flags claims where stated confidence exceeds effective confidence
- Effective confidence shown in CLI (`lattice claims`, `lattice trace`, `lattice stats`)
- Effective confidence returned in dashboard API (`/api/claims`, `/api/claims/{id}`)
- Comprehensive benchmark suite (`benchmarks/run_benchmarks.py`) with 6 experiments: scalability, operations, revocation, effective confidence, baseline comparison, OSINT case study
- Research paper updated with real benchmark data (Table 1), case study results

### Changed
- `audit()` returns a new issue type: `inflated_confidence`
- `stats()` now includes `avg_effective_confidence` and `min_effective_confidence`
- 89 tests (was 78)

## [1.1.0] - 2026-04-11

### Added
- **Cycle detection** in `put_claim()` prevents circular evidence references with `CyclicDependencyError`
- `py.typed` marker for PEP 561 type checker support

### Changed
- `@track` decorator is now a thin wrapper around `@lattice_monitor` and emits a `DeprecationWarning`. New code should use `@lattice_monitor` directly.
- Minimum Python version bumped from 3.8 to 3.10 (3.8/3.9 are EOL)
- GitHub username updated to `thunderstornX`

### Fixed
- README now documents `@lattice_monitor` as the primary decorator

All notable changes to LATTICE will be documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.0] - 2026-03-26

### Added
- Core library: Claim and Evidence models with SHA-256 content-addressing
- Agent registry with Ed25519 keypair generation and claim signing
- SQLite-backed persistent store (WAL mode)
- DAG traversal: `trace` walks backward from any conclusion to raw evidence
- `audit` detects unsupported claims, low confidence, and broken references
- `verify` checks both content integrity (re-hash) and Ed25519 signatures
- `@track` decorator for auto-instrumenting Python functions
- CLI with 8 commands: init, agents, claims, trace, audit, verify, stats, export
- Two working examples: basic usage and full OSINT investigation pipeline
- 41 tests, all passing
- 14-page technical whitepaper (PDF)
- 2-page visual one-pager (PDF)
- 4 architecture diagrams (SVG + PNG)
- MIT License
