# Architecture

## Overview

LATTICE is a recording layer, not an orchestration framework. It does not tell agents what to do. It records what they did, why, and with what confidence. This distinction is deliberate: accountability and orchestration are separate concerns, and coupling them produces systems that are harder to adopt and harder to trust.

## Data Flow

```
Agent calls harvester.claim(...)
        │
        ▼
┌────────────────────┐
│ Claim.create()     │  Compute content-addressed ID (SHA-256 of canonical JSON)
└────────┬───────────┘
         │
         ▼
┌────────────────────┐
│ sign_claim_id()    │  Ed25519 signature over the claim ID
└────────┬───────────┘
         │
         ▼
┌────────────────────┐
│ store.put_claim()  │  Persist to SQLite (claims table)
└────────┬───────────┘
         │
         ▼
   Claim returned to caller
```

Every claim goes through the same pipeline: hash, sign, store, return. There is no shortcut that skips signing or hashing. Accountability is not opt-in.

## Content Addressing

A claim's ID is the SHA-256 hash of its canonical JSON representation:

```json
{"agent_id":"harvester","assertion":"example.com resolves to 93.184.216.34","evidence":["a1b2c3..."],"metadata":{},"method":"tool:nslookup","timestamp":1711000000.0}
```

Keys are sorted. Separators are compact (no spaces). Evidence references are sorted. This ensures that the same logical claim always produces the same ID, regardless of the order in which fields were specified or evidence was listed.

Changing any field, even a single character in the assertion, produces a completely different hash. This is what makes claims tamper-evident: you cannot modify a stored claim without changing its ID, which would break all references from downstream claims.

## The DAG

Claims reference other claims and evidence blobs through the `evidence` field. This naturally forms a Directed Acyclic Graph where information flows upward from raw data to derived conclusions.

```
[Final Assessment]  conf: 0.75  agent: reporter
        │
        ├── [Infrastructure Analysis]  conf: 0.80  agent: analyzer
        │       ├── [DNS Result]  conf: 0.99  agent: harvester
        │       │       └── (evidence: nslookup output)
        │       └── [WHOIS Result]  conf: 0.95  agent: harvester
        │               └── (evidence: WHOIS record)
        │
        └── [Threat Actor TTP Match]  conf: 0.70  agent: analyzer
                ├── [WHOIS Result]  (shared reference)
                └── [HTTP Headers]  conf: 0.99  agent: harvester
                        └── (evidence: curl output)
```

Note that claims can share references. The WHOIS Result claim is referenced by both the Infrastructure Analysis and the Threat Actor TTP Match. This is not duplication; it reflects the fact that the same evidence can support multiple conclusions.

## Agents and Keys

Each agent is registered with a unique ID and an automatically generated Ed25519 keypair. The private key is stored in the SQLite database alongside the agent record. The public key is stored separately for verification.

When an agent creates a claim, the private key signs the claim ID (the content hash). This creates a binding between the agent identity and the specific content of the claim. To verify, you need only the public key and the signature.

This design means:
- You can verify claims without access to the private key.
- A compromised agent can be identified by checking which claims it signed.
- Agent keys can be rotated by registering a new agent and retiring the old one.

## Storage Model

```
┌──────────────────┐
│     agents       │
│ agent_id (PK)    │
│ role             │
│ description      │
│ public_key       │
│ private_key      │
│ created_at       │
└──────────────────┘

┌──────────────────┐
│    evidence      │
│ evidence_id (PK) │  ← SHA-256 of content
│ data             │
│ content_type     │
│ created_at       │
└──────────────────┘

┌──────────────────┐
│     claims       │
│ claim_id (PK)    │  ← SHA-256 of canonical JSON
│ agent_id (FK)    │
│ assertion        │
│ evidence (JSON)  │  ← list of claim_id or evidence_id references
│ confidence       │
│ method           │
│ timestamp        │
│ metadata (JSON)  │
│ signature        │
└──────────────────┘
```

Evidence references in claims are stored as a JSON array of IDs. These IDs may refer to other claim IDs or evidence IDs. The system does not enforce referential integrity at the database level (a claim can reference an ID that does not exist yet or that belongs to an external system). The `audit` operation catches broken references at the application level.

## Module Responsibilities

| Module | Responsibility |
|--------|---------------|
| `models.py` | Claim and Evidence dataclasses, hashing functions |
| `agent.py` | Ed25519 key generation, signing, verification, AgentHandle |
| `store.py` | SQLite persistence, CRUD operations, LatticeStore class |
| `dag.py` | Trace, audit, verify, stats (all read-only graph operations) |
| `tracker.py` | `@track` decorator for auto-instrumentation |
| `evidence.py` | Convenience re-exports for evidence hashing |
| `cli.py` | Command-line interface (Click + Rich) |
| `exceptions.py` | Custom exception hierarchy |

The separation is deliberate: `store.py` handles persistence, `dag.py` handles graph analysis, and `agent.py` handles cryptography. No module reaches into another module's domain.
