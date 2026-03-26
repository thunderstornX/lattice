#!/usr/bin/env python3
"""Basic LATTICE usage — minimal example."""

from __future__ import annotations

import lattice


def main() -> None:
    store = lattice.init(":memory:")

    # Register agents
    harvester = store.agent("harvester", role="collector", description="DNS lookups")
    analyzer = store.agent("analyzer", role="analyst", description="Correlates findings")

    # Store raw evidence
    eid = store.evidence("nslookup example.com → 93.184.216.34")

    # Create a claim backed by evidence
    dns_claim = harvester.claim(
        assertion="example.com resolves to 93.184.216.34",
        evidence=[eid],
        confidence=0.99,
        method="tool:nslookup",
        metadata={"ip": "93.184.216.34"},
    )
    print(f"DNS claim: {dns_claim.claim_id[:16]}…")

    # Derived conclusion
    conclusion = analyzer.claim(
        assertion="example.com is hosted on Edgecast infrastructure",
        evidence=[dns_claim.claim_id],
        confidence=0.85,
        method="llm:analysis",
    )
    print(f"Conclusion: {conclusion.claim_id[:16]}…")

    # Trace backward
    chain = store.trace(conclusion.claim_id)
    print(f"\nTrace ({len(chain)} claims):")
    for c in chain:
        print(f"  → [{c.agent_id}] {c.assertion}")

    # Audit
    issues = store.audit()
    print(f"\nAudit issues: {len(issues)}")

    # Verify signatures
    results = store.verify()
    for r in results:
        print(f"  {'✓' if r.valid else '✗'} {r.claim_id[:16]}…")

    store.close()
    print("\nDone!")


if __name__ == "__main__":
    main()
