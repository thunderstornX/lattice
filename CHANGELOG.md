# Changelog

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

## [0.2.0] - 2026-04-06

### Added
- Schema version tracking via `schema_info` with migration to key lifecycle fields
- Optional encrypted-at-rest agent private keys via `lattice.init(..., passphrase=...)`
- Agent key lifecycle controls in store: rotation and revocation
- Signature verification fallback to per-claim signing key metadata for rotated keys
- Adapter helper module with `wrap_runnable(...)` for low-friction framework integration
- Efficient claim ID prefix resolution in store for CLI trace operations

### Changed
- Unified local install/test flow to `pip install -e .` and `PYTHONPATH=. pytest tests/ -v`
- Python support baseline aligned to 3.11+ in packaging and CI
- CLI version now uses package `__version__`
- Project positioning/documentation updated for private-first operation
