# LATTICE v1.0 Enterprise Expansion - PRD

## Overview
LATTICE provides a lightweight accountability layer for multi-agent AI systems. Every agent action produces a Claim: a content-addressed (SHA-256), cryptographically signed (Ed25519) assertion that references its supporting evidence through a local SQLite Directed Acyclic Graph (DAG). This expansion adds enterprise-grade features for local execution only, with zero budget for cloud resources.

## Goals
1. **Zero-Friction Middleware**: Provide a Python decorator (`@lattice_monitor`) that invisibly intercepts agent output, generates the SHA-256 hash, signs it with the agent's Ed25519 key, and writes the Claim to the LATTICE SQLite store. This enables integration with frameworks like LangGraph or CrewAI without rewriting agent logic.
2. **Revocation Waterfall**: Implement a `revoke_claim(target_claim_id, agent_id)` method that uses recursive SQL CTEs to flag all downstream conclusions that relied on revoked evidence as STATUS: COMPROMISED, addressing the "Ephemeral Evidence" problem in OSINT.
3. **Local Observability Dashboard**: Deliver a lightweight FastAPI server that reads the local LATTICE SQLite store and serves a clean, single-file HTML/JS/D3.js frontend. Clicking a node displays the Ed25519 signature, confidence score, and verification status, solving the "Glass" problem for compliance officers.

## Non-Goals
- No cloud dependencies or external services.
- No web dashboard requiring internet access.
- No framework adapters for LangGraph/CrewAI/AutoGen in v1 (decorator is framework-agnostic).
- No Bayesian confidence propagation or network/P2P features.
- No real-time streaming.

## Functional Requirements
### 1. Zero-Friction Middleware
- A decorator `@lattice_monitor(agent, method_desc=None)` that:
  - Wraps any function (tool or LLM call) associated with a registered LATTICE agent.
  - Automatically captures the return value as evidence.
  - Creates a Claim with:
    - `assertion`: function name + args (or provided method_desc)
    - `evidence`: list containing the evidence ID of the return value
    - `confidence`: default 1.0 for tool calls, configurable for LLM
    - `method`: "tool:<function_name>" or "llm:<model_name>"
    - `metadata`: function return value and any additional context
  - Signs the claim with the agent's Ed25519 private key.
  - Writes the claim to the LATTICE SQLite store.
  - Returns the original function output unchanged.

### 2. Revocation Waterfall
- A method `revoke_claim(target_claim_id, agent_id)` that:
  - Verifies the `agent_id` matches the signer of `target_claim_id` (or has governance rights).
  - Inserts a revocation record into a new `revocations` table.
  - Uses a recursive CTE to traverse the DAG downstream from `target_claim_id` to find all claims that have a dependency path (direct or indirect) from the revoked claim.
  - Marks these downstream claims as `STATUS: COMPROMISED` in query results (without altering the original claim).
  - Returns the list of compromised claim IDs.

### 3. Local Observability Dashboard
- A FastAPI server serving:
  - A single HTML page with embedded JS/D3.js (or Cytoscape.js) for DAG visualization.
  - API endpoints to:
    - Retrieve all claims, evidence, and agents.
    - Retrieve the revocation status of any claim.
    - Verify the Ed25519 signature of a claim.
    - Trace a claim upstream to evidence.
  - The frontend must:
    - Display the DAG with nodes for claims and leaves for evidence.
    - On node click, show a modal with: claim_id, assertion, agent_id, timestamp, confidence, method, metadata, signature, verification status, and revocation status.
    - Use color-coding to distinguish normal, compromised, and revoked claims.

## Non-Functional Requirements
- **Local Execution Only**: All code must run locally with no external network calls (except for optional LLM inference via provided NVIDIA API key, which is local to the machine).
- **Technology Stack**: 
  - Backend: Pure Python 3.11+ with standard libraries + `cryptography`, `fastapi`, `uvicorn`.
  - Database: SQLite (WAL mode for concurrent reads).
  - Frontend: HTML, vanilla JS, and D3.js (or Cytoscape.js) — no external CDN dependencies; all assets bundled.
- **Cryptographic Integrity**: 
  - Claims remain immutable and content-addressed.
  - Revocation status is stored separately and does not alter the original claim or its signature.
  - All signatures are Ed25519 and verifiable.
- **Performance**: 
  - Claim creation and signing must complete in <10ms for typical use.
  - Revocation waterfall traversal must complete in <100ms for graphs up to 10k claims.
  - Dashboard must load and render a 100-claim graph in <2s.
- **Reliability**: 
  - All public functions must be type-hinted and have docstrings.
  - Comprehensive error handling with custom exceptions.
  - Must handle edge cases: revoking a claim you didn't sign, revoking an already revoked claim, circular dependencies (though DAG should prevent this).

## Success Criteria
A user should be able to:
1. `pip install .` (or develop in place) and have a working LATTICE v1.0 enterprise package.
2. Register agents and instrument 3 Python functions (tool or LLM calls) with `@lattice_monitor`.
3. Run those functions to generate a claim DAG.
4. Use `lattice revoke <claim_id>` (via CLI or API) to revoke a claim and see downstream claims flagged as compromised.
5. Start the dashboard (`lattice dashboard`) and view the DAG locally in a browser, with clickable nodes showing full claim details and verification status.
6. Run the test suite (`pytest`) and see all tests pass, including:
   - Cryptographic signature verification.
   - Revocation waterfall correctness (graph traversal).
   - Middleware integration (tool and LLM functions).
   - Dashboard API endpoints.

## References
- Original LATTICE PRD and architecture: see existing `docs/` and `lattice/` directory.
- Cryptography: Ed25519 via `cryptography` library.
- SQLite: Recursive CTE for graph traversal.
- FastAPI: For local web server.
- D3.js/Cytoscape.js: For DAG visualization.