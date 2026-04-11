# LATTICE

**Ledgered Agent Traces for Transparent, Inspectable Collaborative Execution**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://github.com/thunderstornX/lattice/actions/workflows/tests.yml/badge.svg)](https://github.com/thunderstornX/lattice/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-1.2.0-orange.svg)](CHANGELOG.md)

> Accountability layer for multi-agent AI systems. Every agent decision becomes a content-addressed, cryptographically signed claim in a DAG you can trace backward from any conclusion to raw evidence.

**[Read the Paper (PDF)](docs/pdf/LATTICE_Paper.pdf)** | **[Changelog](CHANGELOG.md)** | **[Examples](examples/)**

---

**LATTICE is not an agent framework.** It is the accountability layer that sits *underneath* any agent framework, or raw Python functions.

## The Problem

Multi-agent AI systems produce conclusions, but cannot explain *why*. When Agent X says "this domain is malicious," there is no audit trail showing what evidence it used, how confident it was, or whether that conclusion survives scrutiny.

In OSINT, security research, and regulated industries, an unverifiable claim is worse than no claim.

## The Solution

```
Conclusion -> "domain is malicious" (conf: 0.75, eff: 0.70, agent: reporter)
    +-- "bulletproof hosting detected" (conf: 0.80, agent: analyzer)
        +-- "resolves to 198.51.100.42" (conf: 0.99, agent: harvester)
        |   +-- [evidence: nslookup output]
        +-- "registered via ShadyRegistrar, Panama" (conf: 0.95, agent: harvester)
            +-- [evidence: WHOIS record]
```

Every node is content-addressed (SHA-256), cryptographically signed (Ed25519), and stored in SQLite. Walk backward from any conclusion to raw evidence. Verify nothing was tampered with. Detect inflated confidence automatically.

## Features

- **Content-addressed claims** -- SHA-256 hashes make every claim tamper-evident
- **Ed25519 signatures** -- every claim is cryptographically bound to its originating agent
- **Backward traceability** -- walk from any conclusion to raw evidence
- **Effective confidence** -- min-propagation ensures weak evidence cannot hide behind strong conclusions
- **Revocation waterfall** -- revoking a claim propagates compromise status to all downstream dependents
- **Zero-friction monitoring** -- `@lattice_monitor` instruments any function without changing its behavior
- **Cycle detection** -- DAG acyclicity enforced at insertion time
- **Audit** -- flags unsupported claims, low confidence, broken references, and inflated confidence
- **Local dashboard** -- FastAPI + D3.js visualization, no external dependencies
- **CLI** -- Rich terminal interface for all operations
- **89 tests** across all modules

## Install

```bash
git clone https://github.com/thunderstornX/lattice.git
cd lattice
pip install -e .                    # Core library (no dashboard)
pip install -e ".[dashboard]"       # With local web dashboard
pip install -e ".[dev]"             # With dev/test dependencies
```

## Quick Start

```python
import lattice

store = lattice.init(":memory:")

# Register agents
harvester = store.agent("harvester", role="collector")
analyzer = store.agent("analyzer", role="analyst")

# Store raw evidence
eid = store.evidence("nslookup example.com -> 93.184.216.34")

# Create signed claims backed by evidence
dns_claim = harvester.claim(
    assertion="example.com resolves to 93.184.216.34",
    evidence=[eid],
    confidence=0.99,
    method="tool:nslookup",
)

# Build derived conclusions referencing other claims
conclusion = analyzer.claim(
    assertion="example.com hosted on Edgecast infrastructure",
    evidence=[dns_claim.claim_id],
    confidence=0.85,
    method="llm:analysis",
)

# Trace backward from any conclusion
chain = store.trace(conclusion.claim_id)
for claim in chain:
    print(f"  [{claim.agent_id}] {claim.assertion}")

# Check effective confidence (min across ancestor chain)
eff = store.effective_confidence(conclusion.claim_id)
print(f"  Effective confidence: {eff}")

# Audit for issues (unsupported, low confidence, inflated, broken refs)
issues = store.audit()

# Verify all cryptographic signatures
results = store.verify()
```

## Auto-Instrumentation

Wrap any function with `@lattice_monitor` to auto-generate signed claims:

```python
from lattice import lattice_monitor

@lattice_monitor(harvester, method="tool:nslookup")
def dns_lookup(domain: str) -> dict:
    """DNS lookup for {domain}"""
    result = subprocess.run(["nslookup", domain], capture_output=True, text=True)
    return {"output": result.stdout}

# Calling dns_lookup("example.com") automatically:
# 1. Runs the function
# 2. Stores the return value as raw Evidence
# 3. Creates a signed Claim with "DNS lookup for example.com"
# 4. Links the claim to the evidence in the DAG
# 5. Returns the original output unchanged
```

Options: `confidence=0.9`, `evidence_ids=[...]` to link upstream claims, `capture_evidence=False` to skip evidence storage.

Overhead: **0.24 ms per instrumented call** (see benchmarks).

## Effective Confidence

LATTICE computes the *effective confidence* of every claim: the minimum confidence across the claim and all of its ancestors. A conclusion cannot hide behind a high stated confidence if its evidence chain contains a weak link.

```python
# Stated confidence is 0.95, but an ancestor has 0.6
eff = store.effective_confidence(conclusion.claim_id)
# Returns 0.6 -- the real floor

# Audit catches the mismatch automatically
issues = store.audit()
# -> "inflated_confidence: Stated 0.95 but effective 0.60"
```

Min-propagation is correct under worst-case correlation between evidence sources, making it a defensible choice for adversarial and security contexts.

## Revocation Waterfall

When evidence is invalidated, revoke it and LATTICE propagates compromise status through the entire dependency graph:

```python
# Revoke a claim (only the signer or governance can do this)
result = store.revoke_claim(bad_claim.claim_id, agent_id="harvester", reason="Source retracted")

print(f"Directly revoked: {result.revoked_claim_id}")
print(f"Downstream compromised: {result.compromised_claim_ids}")
print(f"Total affected: {result.total_affected}")

# Check any claim's status
store.get_claim_status(some_claim_id)  # -> "VALID", "REVOKED", or "COMPROMISED"
```

Original claims and signatures are never modified. Revocation is stored separately, preserving the complete historical record.

## CLI

```bash
lattice init ./my-investigation       # Initialize
lattice agents -d ./my-investigation  # List agents
lattice claims -d ./my-investigation  # List claims (shows effective confidence)
lattice trace <claim_id> -d .         # Trace backward
lattice audit -d .                    # Audit for issues
lattice verify -d .                   # Verify all signatures
lattice stats -d .                    # Summary statistics
lattice export out.json -d .          # Export to JSON
lattice revoke <id> --agent bot -d .  # Revoke a claim
lattice revocations -d .             # List revocations
lattice dashboard -d .                # Launch local web dashboard
```

## Dashboard

Local web dashboard (FastAPI + D3.js, no CDN dependencies):

```bash
lattice dashboard -d ./my-investigation
# -> http://127.0.0.1:8420
```

Force-directed DAG visualization with color-coded nodes (valid/revoked/compromised/evidence). Click any node to see full details: claim ID, assertion, agent, confidence, effective confidence, signature verification status, and revocation info.

## Architecture

```
+--------------------------------------------------+
|         YOUR AGENTS (any framework)              |
|  CrewAI / LangGraph / raw Python / shell scripts |
+------------------------+-------------------------+
                         |  store.agent() / .claim()
                         v
+--------------------------------------------------+
|              LATTICE CORE                        |
|                                                  |
|  +----------+  +----------+  +--------------+   |
|  |Claim DAG |  | Evidence |  |   Agent      |   |
|  | (SQLite) |  |  Store   |  |  Registry    |   |
|  +----------+  +----------+  +--------------+   |
|                                                  |
|  +--------------+  +-----------+  +----------+  |
|  | DAG Traversal|  | Effective |  | Signature|  |
|  | + Audit      |  | Confidence|  | Verify   |  |
|  +--------------+  +-----------+  +----------+  |
|                                                  |
|  +--------------+  +-----------+                 |
|  | Revocation   |  | Runtime   |                 |
|  | Waterfall    |  | Monitor   |                 |
|  +--------------+  +-----------+                 |
+------------------------+-------------------------+
                         |
          +--------------+--------------+
          v              v              v
+----------------+ +------------+ +----------+
| CLI (Rich)     | | Dashboard  | | JSON     |
| trace/audit/   | | (FastAPI + | | Export   |
| verify/stats   | |  D3.js)    | |          |
+----------------+ +------------+ +----------+
```

## Performance

Benchmarked on Intel Xeon E5-2676 v3, 2GB RAM, SSD, Ubuntu 20.04 (see `benchmarks/`):

| Operation | Time |
|-----------|------|
| Evidence storage | 0.009 ms |
| Claim creation + signing | 0.68 ms |
| Trace (100-claim chain) | 1.36 ms |
| Effective confidence (single) | 1.30 ms |
| Effective confidence (bulk, 100) | 2.44 ms |
| Audit (100 claims) | 4.01 ms |
| Verify all signatures (100) | 43.33 ms |
| Instrumentation overhead per call | 0.24 ms |

Full scalability curves and case study results in the [paper](docs/pdf/LATTICE_Paper.pdf).

## Core Concepts

### Claim

The fundamental unit. Content-addressed (SHA-256), cryptographically signed (Ed25519):

```python
Claim(
    claim_id="a1b2c3...",     # SHA-256 of canonical content
    agent_id="harvester",     # Who made this claim
    assertion="domain -> IP", # What is claimed
    evidence=["e1", "c2"],    # Supporting claim/evidence IDs
    confidence=0.99,          # 0.0 to 1.0
    method="tool:nslookup",   # How it was derived
    signature="d4e5f6...",    # Ed25519 signature
)
```

### Evidence

Content-addressed raw data (tool output, API responses, etc.). Claims reference evidence by hash.

### DAG

Claims reference other claims and evidence, forming a Directed Acyclic Graph:
- **Leaf nodes** = raw evidence
- **Intermediate nodes** = derived analysis
- **Root nodes** = final conclusions

Cycle detection is enforced at insertion time.

## Dependencies

Minimal by design:

- **Python 3.10+**
- **cryptography** -- Ed25519 signatures
- **click** -- CLI
- **rich** -- terminal formatting
- **fastapi** + **uvicorn** -- local dashboard
- **sqlite3** -- storage (stdlib)

## Security Notes

LATTICE is designed for **single-user, local investigations**:

- **Private keys are stored in plaintext** in the SQLite database. Acceptable for local use with appropriate file permissions. Do not share the database file.
- **No key rotation** in v1.x. If an agent keypair is compromised, register a new agent.
- The database is a local file with no access control beyond filesystem permissions.

For multi-user or networked deployments, additional encryption and access control would be needed (planned for future versions).

## Running Tests

```bash
pip install -e ".[dev]"
pytest
```

89 tests covering: content addressing, signatures, DAG traversal, revocation waterfall, cycle detection, effective confidence, inflated confidence audit, CLI, dashboard API, and runtime monitoring.

## Examples

See [`examples/`](examples/) for:
- `basic_usage.py` -- Minimal two-agent demo
- `osint_investigation.py` -- Full three-agent OSINT pipeline

## Benchmarks

```bash
PYTHONPATH=. python3 benchmarks/run_benchmarks.py
```

Six experiments: scalability curves, operation profiling, revocation waterfall performance, effective confidence scaling, instrumentation overhead, and OSINT pipeline case study. Results saved to `benchmarks/results.json`.

## Research

LATTICE formalizes concepts from:
- **W3C PROV** -- Data provenance standard
- **Structured Analytic Techniques** -- Intelligence community tradecraft
- **Content-addressed storage** -- Git, IPFS, Merkle DAGs
- **Runtime verification** -- Lightweight monitoring of multi-agent behavior

To our knowledge, no existing tool combines content-addressing + cryptographic signatures + effective confidence propagation + revocation waterfall + agent attribution in a single protocol for AI systems.

## License

MIT -- see [LICENSE](LICENSE).

## Author

**Ali Murtaza Bhutto** -- [@thunderstornX](https://github.com/thunderstornX) -- [ORCID: 0009-0007-2787-943X](https://orcid.org/0009-0007-2787-943X)
