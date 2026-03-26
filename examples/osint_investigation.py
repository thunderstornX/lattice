#!/usr/bin/env python3
"""Full OSINT investigation demo with three agents.

Simulates: harvester → analyzer → reporter pipeline.
Every step is captured in the LATTICE DAG.
"""

from __future__ import annotations

import lattice

DNS_OUTPUT = "Name: suspicious-domain.example\nAddress: 198.51.100.42"
WHOIS_OUTPUT = "Registrar: ShadyRegistrar Inc.\nCountry: PA\nNS: ns1.bulletproof-hosting.example"
HTTP_HEADERS = "Server: nginx/1.18.0\nX-Powered-By: PHP/7.4\nSet-Cookie: tracking=abc123"


def main() -> None:
    store = lattice.init(":memory:")

    # Register agents
    harvester = store.agent("harvester", role="collector", description="DNS/WHOIS/HTTP")
    analyzer = store.agent("analyzer", role="analyst", description="Cross-reference")
    reporter = store.agent("reporter", role="reporter", description="Final assessment")

    # Phase 1: Collection
    dns_eid = store.evidence(DNS_OUTPUT)
    whois_eid = store.evidence(WHOIS_OUTPUT)
    http_eid = store.evidence(HTTP_HEADERS)

    dns_claim = harvester.claim(
        assertion="suspicious-domain.example resolves to 198.51.100.42",
        evidence=[dns_eid], confidence=0.99, method="tool:nslookup",
    )
    whois_claim = harvester.claim(
        assertion="Domain registered via ShadyRegistrar, Panama",
        evidence=[whois_eid], confidence=0.95, method="tool:whois",
    )
    http_claim = harvester.claim(
        assertion="Runs nginx/1.18 + PHP/7.4 with tracking cookie",
        evidence=[http_eid], confidence=0.99, method="tool:curl",
    )

    # Phase 2: Analysis
    infra_claim = analyzer.claim(
        assertion="198.51.100.42 on bulletproof hosting (ns1.bulletproof-hosting.example)",
        evidence=[dns_claim.claim_id, whois_claim.claim_id],
        confidence=0.80, method="llm:correlation",
    )
    actor_claim = analyzer.claim(
        assertion="Operator uses Panama shell entity + bulletproof hosting — threat actor TTP",
        evidence=[whois_claim.claim_id, http_claim.claim_id, infra_claim.claim_id],
        confidence=0.70, method="llm:analysis",
    )

    # Phase 3: Report
    report = reporter.claim(
        assertion="ASSESSMENT: suspicious-domain.example likely operated by threat actor. Recommend blocking.",
        evidence=[infra_claim.claim_id, actor_claim.claim_id],
        confidence=0.75, method="human:assessment",
    )

    # Results
    print("=" * 60)
    print("LATTICE OSINT Investigation")
    print("=" * 60)

    all_claims = store.list_claims()
    print(f"\nTotal claims: {len(all_claims)}")
    for c in all_claims:
        print(f"  [{c.agent_id:>10}] ({c.confidence:.2f}) {c.assertion[:65]}")

    # Trace from report
    chain = store.trace(report.claim_id)
    print(f"\nTrace from final report ({len(chain)} claims):")
    for i, c in enumerate(chain):
        print(f"  {'  ' * i}↳ [{c.agent_id}] {c.assertion[:55]}")

    # Verify
    print("\nSignatures:")
    for r in store.verify():
        print(f"  {'✓' if r.valid else '✗'} {r.claim_id[:16]}…")

    # Audit
    issues = store.audit()
    print(f"\nAudit issues: {len(issues)}")
    for iss in issues:
        print(f"  [{iss.issue_type}] {iss.description}")

    store.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
