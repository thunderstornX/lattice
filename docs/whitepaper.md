# LATTICE: A Content-Addressed Accountability Protocol for Multi-Agent Intelligence Systems

**Ali Murtaza Bhutto**
ORCID: 0009-0007-2787-943X

March 2026

---

## Abstract

Multi-agent AI systems increasingly drive investigative workflows in cybersecurity, OSINT, and threat intelligence. These systems produce conclusions, but cannot explain how they reached them. When an automated pipeline flags a domain as malicious or attributes a campaign to a threat actor, there is no standardized mechanism to trace that conclusion backward through the chain of evidence, verify that no step was fabricated, or assess how sensitive the result is to the removal of any single data point.

This paper introduces LATTICE (Ledgered Agent Traces for Transparent, Inspectable Collaborative Execution), an open-source Python library that addresses this gap. LATTICE provides a lightweight accountability layer that sits beneath any agent framework. Every agent action produces a Claim: a content-addressed, cryptographically signed assertion that references its supporting evidence through a Directed Acyclic Graph. The result is a complete, tamper-evident reasoning chain from final conclusions down to raw tool output.

We describe the architecture, demonstrate its application in an OSINT investigation pipeline, and argue that accountability infrastructure is a prerequisite for trustworthy multi-agent systems in security-critical domains.

**Keywords:** multi-agent systems, provenance, OSINT, accountability, content-addressing, digital forensics

---

## 1. Introduction

The adoption of multi-agent AI architectures in cybersecurity and intelligence work has accelerated rapidly. Frameworks like LangGraph, CrewAI, and AutoGen allow practitioners to decompose complex investigative tasks across specialized agents: one for data collection, another for analysis, a third for report synthesis. The appeal is clear. Complex investigations involve heterogeneous data sources, require multiple analytical perspectives, and benefit from parallelized execution.

But these frameworks share a fundamental limitation. They are built around orchestration (how agents communicate) rather than accountability (why agents concluded what they did). The output of a multi-agent pipeline is typically a final report or a structured summary. The intermediate reasoning, the evidence that was considered and discarded, the confidence levels at each step, and the identity of the agent responsible for each assertion are lost or buried in unstructured logs.

This matters. In security consulting, handing a client a report that says "our AI found this vulnerability" without an auditable reasoning chain is professionally inadequate. In OSINT and investigative journalism, an unverifiable claim is worse than no claim at all, because it carries the false authority of a technical system. In regulated industries governed by the EU AI Act or similar legislation, explainability is not optional.

LATTICE addresses this by treating accountability as a system-level property rather than an afterthought. The core idea is simple: every agent decision is recorded as a content-addressed, signed Claim in a DAG. You can walk backward from any conclusion to the raw evidence that supports it, verify that nothing was tampered with, and identify exactly which agent made each assertion and how confident it was.

The contribution is not algorithmic novelty. Content-addressing has existed since Merkle trees in the 1970s. Ed25519 signatures are standard. SQLite is ubiquitous. What appears to be new is the application of these primitives as a coherent accountability protocol specifically designed for multi-agent AI reasoning chains. To our knowledge, no existing tool combines content-addressing, cryptographic signatures, confidence tracking, and agent attribution in a single open protocol for AI systems.

---

## 2. Related Work

### 2.1 Agent Observability Platforms

LangSmith (LangChain), LangFuse, Arize Phoenix, and Weights & Biases Prompts provide monitoring and tracing for LLM-based applications. These platforms focus on operational observability: latency, token counts, error rates, prompt/response pairs. They answer "what happened?" but not "why should we believe this conclusion?"

More critically, they are cloud-hosted proprietary services. In security consulting and intelligence work, sending client data and investigation artifacts to third-party APIs is often prohibited by contract, regulation, or basic operational security.

### 2.2 Data Provenance Standards

The W3C PROV specification (Moreau & Missier, 2013) provides a general data model for provenance. PROV defines entities, activities, and agents, along with relationships like "wasGeneratedBy" and "wasDerivedFrom." The model is mature and well-specified, but it was designed for data lineage in scientific workflows, not for reasoning chains in adversarial contexts. It does not natively handle confidence distributions, cryptographic verification, or the specific needs of multi-agent AI pipelines.

### 2.3 Structured Analytic Techniques

The intelligence community has developed Structured Analytic Techniques (SATs) such as Analysis of Competing Hypotheses (ACH), Devil's Advocacy, and Red Team/Blue Team analysis (Heuer & Pherson, 2010). These techniques formalize aspects of reasoning that are relevant to any multi-agent system: maintaining competing hypotheses, challenging assumptions, documenting alternative explanations. However, these techniques exist as human-oriented methodologies, not as machine-enforceable protocols.

### 2.4 Content-Addressed Storage

Git, IPFS, and Merkle DAGs more broadly demonstrate that content-addressing is a viable foundation for tamper-evident, distributed data structures. Git's object model (blobs, trees, commits identified by SHA-1 hashes) provides an existence proof that content-addressed DAGs can scale to millions of objects while remaining verifiable. LATTICE applies this principle to reasoning chains rather than source code.

### 2.5 The Gap

To our knowledge, no existing system combines all four properties that accountability in multi-agent AI requires:

1. **Content-addressed immutability.** Claims and evidence are identified by their content hash, making them tamper-evident.
2. **Cryptographic agent attribution.** Each claim is signed by the agent that produced it, using a verifiable keypair.
3. **Confidence as a first-class primitive.** Every assertion carries a calibrated confidence value, not a binary true/false label.
4. **DAG-structured reasoning chains.** Claims reference their supporting evidence, forming a traversable graph from conclusions to raw data.

LATTICE fills this gap.

---

## 3. Architecture

### 3.1 Design Principles

LATTICE is built on four principles:

**Minimality.** The library should be easy to integrate into existing workflows. It depends only on Python's standard library plus three packages (cryptography, click, rich). Storage is SQLite. There is no external service, no cloud dependency, no daemon to manage.

**Framework agnosticism.** LATTICE is not an agent framework. It does not orchestrate agents, manage conversations, or handle tool calls. It records what agents did and why. This means it can sit underneath LangGraph, CrewAI, AutoGen, or raw Python scripts without requiring changes to the agent logic itself.

**Verifiability by default.** Every Claim is content-addressed (SHA-256) and signed (Ed25519) at creation time. Verification is a single function call. There is no "opt-in" to accountability; it is the default behavior.

**Offline-first.** The entire system runs locally. Investigation data, agent keys, and the reasoning DAG never leave the machine unless the user explicitly exports them. This is a hard requirement for security work.

### 3.2 Core Primitives

**Evidence** is a content-addressed blob of raw data: tool output, API responses, DNS records, WHOIS results, or any other artifact. Evidence is identified by the SHA-256 hash of its content. Storing the same data twice is idempotent.

**Claim** is the fundamental unit of the DAG. A Claim represents an assertion made by a specific agent, supported by specific evidence. Its fields are:

| Field | Type | Description |
|-------|------|-------------|
| `claim_id` | string | SHA-256 hash of canonical JSON of all content fields |
| `agent_id` | string | Identifier of the originating agent |
| `assertion` | string | Human-readable statement of what is claimed |
| `evidence` | list[string] | Claim IDs or Evidence IDs this depends on |
| `confidence` | float | Value in [0.0, 1.0] |
| `method` | string | How the claim was derived (e.g., `tool:nslookup`, `llm:gpt-4`) |
| `timestamp` | float | Unix timestamp |
| `metadata` | dict | Arbitrary key-value pairs |
| `signature` | string | Hex-encoded Ed25519 signature over `claim_id` |

The `claim_id` is computed deterministically from the content fields using canonical JSON serialization (sorted keys, no whitespace). This means the same assertion with the same evidence at the same timestamp will always produce the same ID. It also means that any modification to a stored claim will produce a different hash, making tampering detectable.

**Agent** is a registered entity with an Ed25519 keypair. When a claim is created through an agent handle, the private key signs the `claim_id`. Any party with access to the agent's public key can later verify that the claim was produced by that specific agent and has not been modified.

### 3.3 The Claim DAG

Claims reference other claims and evidence through the `evidence` field, forming a Directed Acyclic Graph:

- **Leaf nodes** are raw Evidence blobs (tool output, API responses).
- **Intermediate nodes** are derived Claims (analysis, correlation, cross-referencing).
- **Root nodes** are final conclusions (assessment, report summary).

Walking backward from any root node traverses the complete reasoning chain. At each node, the investigator can see who made the claim, what evidence it rests on, how confident the agent was, and what method was used.

### 3.4 Storage

All data is stored in a single SQLite database with three tables: `agents`, `claims`, and `evidence`. SQLite was chosen because it requires no server, supports WAL mode for concurrent reads, and is available on every platform where Python runs. The database lives in a `.lattice/` directory inside the investigation project folder.

### 3.5 Operations

LATTICE provides five core operations:

**Trace** performs a breadth-first backward traversal from a given claim, returning all ancestor claims in dependency order. This is the primary accountability operation: given a conclusion, show everything that led to it.

**Audit** scans the DAG for structural issues: claims with no evidence references (unsupported assertions), claims below a confidence threshold, and broken references (evidence IDs that don't resolve to any stored object).

**Verify** checks Ed25519 signatures on all claims against the registered public keys of their respective agents. This confirms that no claim has been modified after creation and that each claim was produced by the agent it attributes.

**Stats** computes summary metrics: claim count, evidence count, confidence distribution, method breakdown, and per-agent contribution.

**Export** serializes the entire investigation (agents, claims, metadata) as a JSON document for archival, sharing, or integration with other tools.

---

## 4. Demonstration: OSINT Investigation Pipeline

To illustrate LATTICE in practice, we instrument a three-agent OSINT investigation targeting a suspicious domain.

### 4.1 Agent Roles

| Agent | Role | Methods |
|-------|------|---------|
| Harvester | Collector | DNS lookup, WHOIS query, HTTP header inspection |
| Analyzer | Analyst | Cross-reference infrastructure, correlate indicators |
| Reporter | Reporter | Synthesize findings into a risk assessment |

### 4.2 Investigation Flow

**Phase 1: Collection.** The Harvester agent performs DNS resolution, WHOIS lookup, and HTTP header inspection on the target domain. Each tool output is stored as Evidence. Each finding is recorded as a signed Claim referencing the corresponding evidence.

**Phase 2: Analysis.** The Analyzer agent creates derived Claims by cross-referencing the Harvester's findings. For example, it correlates the IP address from DNS with the nameserver from WHOIS to assert that the domain uses bulletproof hosting infrastructure. Each derived Claim references the source Claims it depends on and carries its own confidence level.

**Phase 3: Reporting.** The Reporter agent produces a final assessment Claim that references the Analyzer's findings. The assessment includes a risk rating and a recommendation.

### 4.3 Result

The resulting DAG contains 6 claims across 3 agents, with 3 evidence blobs at the leaves. Running `lattice trace` on the final assessment produces a complete chain:

```
ASSESSMENT: likely threat actor (conf: 0.75, reporter)
  └─ bulletproof hosting detected (conf: 0.80, analyzer)
  │   ├─ resolves to 198.51.100.42 (conf: 0.99, harvester) → [evidence: DNS]
  │   └─ registered via ShadyRegistrar, Panama (conf: 0.95, harvester) → [evidence: WHOIS]
  └─ threat actor TTP pattern (conf: 0.70, analyzer)
      ├─ registered via ShadyRegistrar, Panama (conf: 0.95, harvester) → [evidence: WHOIS]
      ├─ nginx/1.18 + PHP/7.4 with tracking (conf: 0.99, harvester) → [evidence: HTTP]
      └─ bulletproof hosting detected (conf: 0.80, analyzer) → [see above]
```

Running `lattice verify` confirms all 6 signatures are valid. Running `lattice audit` reports no unsupported claims.

---

## 5. Discussion

### 5.1 What LATTICE Solves

LATTICE addresses a specific and well-defined problem: the absence of standardized accountability infrastructure for multi-agent AI reasoning. By making every decision content-addressed, signed, and connected in a DAG, it enables three capabilities that are currently missing from the multi-agent ecosystem:

**Backward traceability.** Any conclusion can be traced to its supporting evidence. This is essential for client-facing security reports, journalistic fact-checking, and regulatory compliance.

**Tamper evidence.** Content-addressing and cryptographic signatures make it computationally infeasible to modify a claim without detection. This provides a basic level of integrity assurance without requiring blockchain or distributed consensus.

**Agent attribution.** Each claim is tied to a specific agent identity. When a conclusion is wrong, it is possible to identify which agent introduced the error and at what step in the reasoning chain.

### 5.2 Limitations and Honest Scoping

LATTICE does not solve several related problems, and it is important to be explicit about these boundaries.

**Confidence propagation.** In v0.1, confidence values are metadata. They are set by agents and displayed during audit, but they do not automatically propagate through the DAG. Bayesian belief propagation through a claim graph is mathematically well-defined, but the choice of priors and conditional dependencies is a research question, not an engineering one. We plan to add pluggable propagation models in a future version, clearly marked as experimental.

**Deterministic replay.** LATTICE records what agents concluded, not the exact computational state that led to the conclusion. Because LLM outputs are non-deterministic, "replaying" an investigation by re-running the same agents with the same evidence will generally produce different results. What LATTICE can do is show that removing a specific piece of evidence eliminates the support for downstream claims (static graph analysis). This is useful, but it is not true replay.

**Trust in agents.** LATTICE verifies that claims were signed by the agents that claim to have produced them, and that the claims have not been modified. It does not verify that the agents themselves are trustworthy or that their reasoning is sound. A compromised agent can sign false claims that will pass signature verification. Adversarial agent monitoring is a separate problem.

### 5.3 Connection to Broader Research

LATTICE relates to ongoing work in several areas:

**Auditable hyper-investigation.** Le Deuff's concept of hyper-investigation (2019) foregrounds the epistemic and civic dimensions of open-source inquiry. LATTICE provides technical infrastructure for one of the core requirements of hyper-investigation: that investigative conclusions be traceable, challengeable, and ultimately defensible.

**AI transparency and the EU AI Act.** The EU AI Act (Regulation 2024/1689) requires that high-risk AI systems provide explanations of their outputs. A claim DAG with full provenance and confidence metadata is a natural format for meeting this requirement.

**Structured Analytic Techniques.** The Claim/Evidence/Confidence structure maps naturally to SATs like Analysis of Competing Hypotheses. A future extension could formalize SATs as inter-agent communication protocols, enabling automated devil's advocacy and red-teaming.

---

## 6. Future Work

**v0.2: Framework adapters.** Integration plugins for LangGraph, CrewAI, and AutoGen, allowing users to add accountability to existing pipelines with minimal code changes.

**v0.3: Confidence propagation.** Pluggable Bayesian propagation modules for experimental uncertainty flow through the DAG.

**v0.4: Web dashboard.** Interactive visualization of the claim DAG with filtering by agent, confidence, and method.

**Research track: SATs as agent protocols.** Formalization of Analysis of Competing Hypotheses, Devil's Advocacy, and Team A/Team B as JSON-defined inter-agent communication schemas. This is the most academically novel extension and a natural target for a conference paper.

---

## 7. Conclusion

Multi-agent AI systems in cybersecurity and intelligence need accountability infrastructure the same way software development needs version control. The ability to trace conclusions backward, verify integrity, and attribute decisions to specific agents is not a nice-to-have feature. It is a prerequisite for professional use.

LATTICE provides this infrastructure in a minimal, framework-agnostic, offline-first Python library. It is not a research prototype. It is a working tool, available under an MIT license, that can be integrated into existing investigative workflows today.

The source code is available at https://github.com/thunderstornX/lattice.

---

## References

Cresci, S. (2020). A decade of social bot detection. *Communications of the ACM*, 63(10), 72-83.

Heuer, R. J., & Pherson, R. H. (2010). *Structured Analytic Techniques for Intelligence Analysis*. CQ Press.

Le Deuff, O., & Perret, A. (2019). Hyperdocumentation: origin and evolution of a concept. *Journal of Documentation*, 75(6), 1463-1474.

Le Deuff, O., & Roumanos, R. (2022). Enjeux définitionnels et scientifiques de la littératie algorithmique. *Communication & langages*, 211, 133-150.

Moreau, L., & Missier, P. (2013). PROV-DM: The PROV Data Model. W3C Recommendation.

Pacheco, D., et al. (2021). Uncovering coordinated networks on social media. *Proceedings of the International AAAI Conference on Web and Social Media*.

---

## Appendix A: Technical Specifications

| Component | Implementation |
|-----------|---------------|
| Language | Python 3.8+ |
| Storage | SQLite (WAL mode) |
| Hashing | SHA-256 |
| Signatures | Ed25519 (via `cryptography` library) |
| CLI | Click + Rich |
| Dependencies | 3 external packages |
| Lines of code | ~1,850 |
| License | MIT |
