# 🔗 LATTICE

**Ledgered Agent Traces for Transparent, Inspectable Collaborative Execution**

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

> Accountability layer for multi-agent AI systems. Every agent decision becomes a content-addressed, cryptographically signed claim in a DAG you can trace backward from any conclusion to raw evidence.

**LATTICE is not an agent framework.** It's the accountability layer that sits *underneath* any agent framework — or raw Python functions.

## The Problem

Multi-agent AI systems produce conclusions, but can't explain *why*. When Agent X says "this domain is malicious," there's no audit trail showing what evidence it used, how confident it was, or whether that conclusion survives scrutiny.

In OSINT, security research, and regulated industries — an unverifiable claim is worse than no claim.

## The Solution

```
Conclusion → "domain is malicious" (conf: 0.75, agent: reporter)
    └─ "bulletproof hosting detected" (conf: 0.80, agent: analyzer)
        ├─ "resolves to 198.51.100.42" (conf: 0.99, agent: harvester)
        │   └─ [evidence: nslookup output]
        └─ "registered via ShadyRegistrar, Panama" (conf: 0.95, agent: harvester)
            └─ [evidence: WHOIS record]
```

Every node is content-addressed (SHA-256), cryptographically signed (Ed25519), and stored in SQLite. Walk backward from any conclusion to raw evidence. Verify nothing was tampered with.

## Install

```bash
git clone https://github.com/alibhutto69/lattice.git
cd lattice
pip install cryptography click rich
```

PyPI package (`pip install lattice-core`) coming soon.

## Quick Start

```python
import lattice

# Initialize (use ":memory:" for testing, or a directory path)
store = lattice.init(":memory:")

# Register agents
harvester = store.agent("harvester", role="collector")
analyzer = store.agent("analyzer", role="analyst")

# Store raw evidence
eid = store.evidence("nslookup example.com → 93.184.216.34")

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

# Audit for unsupported claims, low confidence, broken references
issues = store.audit()

# Verify all cryptographic signatures
results = store.verify()
```

## Auto-Instrumentation

Wrap any function with `@track` to auto-generate claims:

```python
from lattice import track

@track(agent=harvester, method="tool:nslookup")
def dns_lookup(domain: str) -> dict:
    """DNS lookup for {domain}"""
    result = subprocess.run(["nslookup", domain], capture_output=True, text=True)
    return {"output": result.stdout}

# Calling dns_lookup("example.com") automatically:
# 1. Runs the function
# 2. Captures args + return value as metadata
# 3. Creates a signed Claim with "DNS lookup for example.com"
# 4. Stores it in the DAG
```

## CLI

```bash
# Initialize an investigation
lattice init ./my-investigation

# List agents and claims
lattice agents -d ./my-investigation
lattice claims -d ./my-investigation

# Trace a conclusion backward
lattice trace <claim_id> -d ./my-investigation

# Audit for issues
lattice audit -d ./my-investigation

# Verify all signatures
lattice verify -d ./my-investigation

# Show stats
lattice stats -d ./my-investigation

# Export to JSON
lattice export output.json -d ./my-investigation
```

## Architecture

```
┌─────────────────────────────────────────────────┐
│         YOUR AGENTS (any framework)             │
│  CrewAI / LangGraph / raw Python / shell scripts│
└──────────────────────┬──────────────────────────┘
                       │  store.agent() / .claim()
                       ▼
┌─────────────────────────────────────────────────┐
│              LATTICE CORE                       │
│                                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │
│  │Claim DAG │  │ Evidence  │  │   Agent      │  │
│  │ (SQLite) │  │  Store    │  │  Registry    │  │
│  └──────────┘  └──────────┘  └──────────────┘  │
│                                                 │
│  ┌──────────────┐  ┌───────────────────────┐   │
│  │ DAG Traversal│  │ Signature Verification│   │
│  │ + Audit      │  │ (Ed25519)             │   │
│  └──────────────┘  └───────────────────────┘   │
└──────────────────────┬──────────────────────────┘
                       │
          ┌────────────┴────────────┐
          ▼                         ▼
┌──────────────────┐    ┌────────────────────┐
│ CLI (Rich)       │    │ JSON Export         │
│ trace/audit/     │    │ (investigation.json)│
│ verify/stats     │    │                     │
└──────────────────┘    └────────────────────┘
```

## Core Concepts

### Claim

The fundamental unit. Content-addressed (SHA-256), cryptographically signed (Ed25519):

```python
Claim(
    claim_id="a1b2c3...",     # SHA-256 of content (deterministic)
    agent_id="harvester",     # Who made this claim
    assertion="domain → IP",  # What is claimed
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

## Dependencies

Minimal by design:

- **Python 3.11+**
- **cryptography** — Ed25519 signatures
- **click** — CLI
- **rich** — Pretty terminal output
- **SQLite** — Storage (stdlib)

## Security Notes

LATTICE is designed for **single-user, local investigations**. Be aware of:

- **Private keys are stored in plaintext** in the SQLite database. This is acceptable for local use where the `.lattice/` directory has appropriate file permissions. Do not share the database file with untrusted parties.
- **No key rotation** in v0.1. If an agent keypair is compromised, register a new agent.
- **The database is a local file** with no access control beyond filesystem permissions. Treat it like any other sensitive local file (similar to `.git/`).

For multi-user or networked deployments, additional encryption and access control would be needed (planned for future versions).

## Running Tests

```bash
pip install -e ".[dev]"
pytest
```

## Examples

See [`examples/`](examples/) for:
- `basic_usage.py` — Minimal two-agent demo
- `osint_investigation.py` — Full three-agent OSINT pipeline

## Research

LATTICE formalizes concepts from:
- **W3C PROV** — Data provenance standard
- **Structured Analytic Techniques** — Intelligence community tradecraft
- **Content-addressed storage** — Git, IPFS, Merkle DAGs

To our knowledge, no existing tool combines content-addressing + cryptographic signatures + uncertainty tracking + agent attribution in a single open protocol for AI systems.

## License

MIT — see [LICENSE](LICENSE).

## Author

**Ali Murtaza Bhutto** — [@alibhutto69](https://github.com/alibhutto69)
