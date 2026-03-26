# LATTICE — Ledgered Agent Traces for Transparent, Inspectable Collaborative Execution

## Product Requirements Document (v1.0)

### Overview

LATTICE is a lightweight Python library that provides **accountability and provenance tracking for multi-agent AI systems**. It captures every agent decision as a content-addressed, cryptographically signed "Claim" that forms a Directed Acyclic Graph (DAG). This allows full backward traversal from any conclusion to raw evidence.

It is **not** an agent framework. It's an accountability layer that sits underneath any agent framework (or raw Python functions).

### Target Users

- OSINT analysts who need auditable investigation trails
- Security researchers building multi-agent tools
- Anyone using LLM agents who needs to explain *why* the system concluded X

### Core Concepts

#### Claim

The fundamental unit. Every agent action produces a Claim.

```python
@dataclass
class Claim:
    claim_id: str           # SHA-256 hash of (agent_id + assertion + evidence + method + timestamp)
    agent_id: str           # Which agent made this claim
    assertion: str          # What is being claimed (human-readable)
    evidence: list[str]     # List of claim_ids or raw evidence hashes this depends on
    confidence: float       # 0.0 to 1.0
    method: str             # How it was derived: "tool:nslookup", "llm:gpt-4", "human:manual"
    timestamp: float        # Unix timestamp
    metadata: dict          # Arbitrary key-value pairs (tool output, raw data, etc.)
    signature: str          # Ed25519 signature by the agent's private key
```

**Content-addressing:** `claim_id` is deterministic from the content. Same inputs = same hash. This makes claims immutable and verifiable.

**Signatures:** Each agent has an Ed25519 keypair. Claims are signed so you can verify no tampering.

#### Evidence Store

Raw evidence (DNS records, WHOIS output, screenshots, API responses) is stored as content-addressed blobs. Claims reference these by hash.

#### Claim DAG

Claims reference other claims via the `evidence` field. This forms a DAG where:
- **Leaf nodes** = raw evidence (tool outputs, API responses)
- **Intermediate nodes** = derived claims (analysis, correlation)
- **Root nodes** = final conclusions

### Architecture

```
lattice/
├── lattice/
│   ├── __init__.py         # Public API: init(), claim(), track(), agent()
│   ├── models.py           # Claim dataclass, Evidence dataclass
│   ├── store.py            # SQLite-backed DAG store
│   ├── evidence.py         # Content-addressed evidence blob store
│   ├── agent.py            # Agent registry + Ed25519 key management
│   ├── tracker.py          # @track decorator for auto-instrumentation
│   ├── dag.py              # DAG traversal, trace, audit operations
│   ├── cli.py              # CLI: lattice trace, audit, agents, export
│   └── exceptions.py       # Custom exceptions
├── examples/
│   ├── basic_usage.py      # Minimal example
│   └── osint_investigation.py  # Full OSINT demo with 3 agents
├── tests/
│   ├── test_models.py
│   ├── test_store.py
│   ├── test_dag.py
│   ├── test_tracker.py
│   └── test_cli.py
├── pyproject.toml
├── LICENSE                  # MIT
└── README.md
```

### Public API

#### Initialization

```python
import lattice

# Initialize with a project directory (creates .lattice/ inside it)
db = lattice.init("./my_investigation")

# Or use in-memory for testing
db = lattice.init(":memory:")
```

#### Agent Registration

```python
# Register an agent (generates Ed25519 keypair automatically)
harvester = db.agent("harvester", role="collector", description="DNS and WHOIS lookups")
analyzer = db.agent("analyzer", role="analyst", description="Correlates findings")
```

#### Making Claims

```python
# Store raw evidence
evidence_id = db.evidence("nslookup example.com output...", content_type="text/plain")

# Make a claim referencing evidence
claim = harvester.claim(
    assertion="example.com resolves to 93.184.216.34",
    evidence=[evidence_id],
    confidence=0.99,
    method="tool:nslookup",
    metadata={"ip": "93.184.216.34", "ttl": 3600}
)

# Make a derived claim referencing other claims
conclusion = analyzer.claim(
    assertion="example.com and example.org are hosted by the same entity",
    evidence=[claim1.claim_id, claim2.claim_id, whois_claim.claim_id],
    confidence=0.85,
    method="llm:analysis",
)
```

#### Decorator-Based Tracking

```python
@db.track(agent=harvester)
def dns_lookup(domain: str) -> dict:
    """Tracked function. Return value becomes claim metadata.
    Docstring becomes the assertion template."""
    result = subprocess.run(["nslookup", domain], capture_output=True, text=True)
    return {"domain": domain, "output": result.stdout}
```

When `dns_lookup("example.com")` is called, LATTICE automatically:
1. Captures the return value as evidence
2. Creates a Claim with the function name + args as assertion
3. Signs it with the agent's key
4. Stores it in the DAG

#### DAG Operations

```python
# Trace backward from a conclusion to all supporting evidence
chain = db.trace(conclusion.claim_id)
# Returns: list of Claims in dependency order (conclusion → intermediate → evidence)

# Audit: find unsupported claims (claims with no evidence)
unsupported = db.audit()

# Find all claims by a specific agent
harvester_claims = db.claims(agent_id="harvester")

# Find all claims above/below a confidence threshold
low_confidence = db.claims(max_confidence=0.5)

# Export full investigation as JSON
db.export_json("investigation.json")

# Verify all signatures
results = db.verify()
# Returns: list of (claim_id, valid: bool) tuples
```

### CLI

```bash
# Initialize a new investigation
lattice init ./my-investigation

# List registered agents
lattice agents

# Show all claims (compact table)
lattice claims

# Trace a specific conclusion backward
lattice trace <claim_id>

# Audit for unsupported or low-confidence claims
lattice audit

# Verify all signatures
lattice verify

# Export to JSON
lattice export investigation.json

# Show DAG stats
lattice stats
```

### Storage

**SQLite** with three tables:
- `agents` — id, role, description, public_key, created_at
- `claims` — all Claim fields, indexed on claim_id, agent_id, timestamp
- `evidence` — hash, content_type, data (blob), created_at
- `claim_evidence` — many-to-many linking claims to their evidence references

**Location:** `.lattice/lattice.db` inside the project directory.

### Dependencies (minimal)

**Required:**
- Python 3.11+
- `cryptography` (Ed25519 signatures)
- `click` (CLI)
- `rich` (CLI output formatting)

**No other dependencies.** SQLite is stdlib. JSON is stdlib. hashlib is stdlib.

### Non-Goals (v1)

- No web dashboard (v2)
- No framework adapters for LangGraph/CrewAI (v2)
- No Bayesian confidence propagation (v2, research module)
- No network/P2P features
- No real-time streaming

### Quality Requirements

- 100% type-hinted
- Every public function has a docstring
- Tests for: claim creation, hashing determinism, signature verification, DAG traversal, audit detection, CLI commands
- All exceptions are custom (no bare raises)

### Success Criteria

A user should be able to `pip install lattice-core`, instrument 3 Python functions with `@track`, run them, and then use `lattice trace` to walk backward from the final conclusion to raw evidence — all in under 10 minutes.
