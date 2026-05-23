#!/usr/bin/env python3
"""LATTICE demo: run an OSINT investigation end-to-end + capture Rich SVGs.

Produces a file-backed investigation at /tmp/lattice_demo_workspace/
(so the dashboard can read it) and writes SVG snapshots of every CLI-style
view to /tmp/lattice_screenshots/.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import lattice
from lattice import dag
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

WORKSPACE = Path("/tmp/lattice_demo_workspace")
OUT = Path("/tmp/lattice_screenshots")

OUT.mkdir(parents=True, exist_ok=True)
if WORKSPACE.exists():
    shutil.rmtree(WORKSPACE)
WORKSPACE.mkdir(parents=True)

DNS_OUTPUT = "Name: suspicious-domain.example\nAddress: 198.51.100.42"
WHOIS_OUTPUT = "Registrar: ShadyRegistrar Inc.\nCountry: PA\nNS: ns1.bulletproof-hosting.example"
HTTP_HEADERS = "Server: nginx/1.18.0\nX-Powered-By: PHP/7.4\nSet-Cookie: tracking=abc123"


def build_investigation() -> lattice.LatticeStore:
    store = lattice.init(str(WORKSPACE))

    # Agents
    harvester = store.agent("harvester", role="collector", description="DNS/WHOIS/HTTP")
    analyzer = store.agent("analyzer", role="analyst", description="Cross-reference")
    reporter = store.agent("reporter", role="reporter", description="Final assessment")

    # Phase 1: collection
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

    # Phase 2: analysis
    infra_claim = analyzer.claim(
        assertion="198.51.100.42 sits on bulletproof hosting (ns1.bulletproof-hosting.example)",
        evidence=[dns_claim.claim_id, whois_claim.claim_id],
        confidence=0.80, method="llm:correlation",
    )
    actor_claim = analyzer.claim(
        assertion="Operator uses Panama shell entity + bulletproof hosting, threat-actor TTP",
        evidence=[whois_claim.claim_id, infra_claim.claim_id],
        confidence=0.75, method="llm:ttp-analysis",
    )

    # Intentionally inflated claim to demo the audit pass
    over_claim = analyzer.claim(
        assertion="The domain is operated by APT-99 with high certainty",
        evidence=[actor_claim.claim_id],
        confidence=0.98, method="llm:speculation",
    )

    # Phase 3: reporting
    final = reporter.claim(
        assertion="suspicious-domain.example is malicious infrastructure",
        evidence=[actor_claim.claim_id, http_claim.claim_id, over_claim.claim_id],
        confidence=0.85, method="report:final",
    )

    # Cache ids on the store for later use
    store._demo = {
        "dns": dns_claim.claim_id, "whois": whois_claim.claim_id,
        "http": http_claim.claim_id, "infra": infra_claim.claim_id,
        "actor": actor_claim.claim_id, "over": over_claim.claim_id,
        "final": final.claim_id,
    }
    return store


def short(cid: str, n: int = 12) -> str:
    return cid[:n]


def render_stats(store: lattice.LatticeStore) -> Console:
    console = Console(record=True, width=88)
    s = dag.stats(store)
    t = Table(title="Investigation Statistics", title_style="bold cyan")
    t.add_column("Metric", style="cyan")
    t.add_column("Value", justify="right", style="white")
    t.add_row("Agents", str(s.get("total_agents", 0)))
    t.add_row("Evidence items", str(s.get("total_evidence", 0)))
    t.add_row("Claims", str(s.get("total_claims", 0)))
    if "avg_confidence" in s:
        t.add_row("Average confidence", f"{s['avg_confidence']:.3f}")
    if "avg_effective_confidence" in s:
        t.add_row("Avg effective confidence", f"{s['avg_effective_confidence']:.3f}")
    if "min_effective_confidence" in s:
        t.add_row("Min effective confidence", f"{s['min_effective_confidence']:.3f}")
    if "max_confidence" in s:
        t.add_row("Max confidence", f"{s['max_confidence']:.3f}")
    methods = s.get("methods", {})
    if methods:
        top = sorted(methods.items(), key=lambda kv: kv[1], reverse=True)[:3]
        t.add_row("Top methods", ", ".join(f"{k} ({v})" for k, v in top))
    cpa = s.get("claims_per_agent", {})
    if cpa:
        t.add_row("Claims per agent", ", ".join(f"{k}={v}" for k, v in cpa.items()))
    console.print(t)
    return console


def render_claims(store: lattice.LatticeStore) -> Console:
    console = Console(record=True, width=130)
    rows = store.list_claims()
    t = Table(title="All Claims (most recent first)", title_style="bold cyan")
    t.add_column("ID", style="dim")
    t.add_column("Agent", style="magenta")
    t.add_column("Conf", justify="right", style="yellow")
    t.add_column("Eff", justify="right", style="green")
    t.add_column("Status", style="white")
    t.add_column("Assertion", style="white")
    for c in sorted(rows, key=lambda x: x.timestamp, reverse=True):
        eff = store.effective_confidence(c.claim_id)
        status = store.get_claim_status(c.claim_id)
        t.add_row(short(c.claim_id), c.agent_id, f"{c.confidence:.2f}", f"{eff:.2f}",
                  status,
                  c.assertion[:70] + ("..." if len(c.assertion) > 70 else ""))
    console.print(t)
    return console


def render_audit(store: lattice.LatticeStore) -> Console:
    console = Console(record=True, width=130)
    issues = store.audit()
    t = Table(title=f"Audit: {len(issues)} issue(s) flagged", title_style="bold red")
    t.add_column("Type", style="yellow")
    t.add_column("Claim", style="dim")
    t.add_column("Severity", style="cyan")
    t.add_column("Detail", style="white")
    for i in issues:
        sev = getattr(i, "severity", "")
        msg = getattr(i, "message", getattr(i, "description", ""))
        t.add_row(i.issue_type, short(i.claim_id), str(sev), str(msg)[:80])
    console.print(t)
    return console


def render_trace(store: lattice.LatticeStore, root_id: str) -> Console:
    console = Console(record=True, width=130)
    chain = store.trace(root_id)
    t = Table(title=f"Trace from {short(root_id)} backward to raw evidence",
              title_style="bold cyan")
    t.add_column("Step", justify="right", style="dim")
    t.add_column("Claim ID", style="dim")
    t.add_column("Agent", style="magenta")
    t.add_column("Confidence", justify="right", style="yellow")
    t.add_column("Assertion", style="white")
    for i, c in enumerate(chain, start=1):
        t.add_row(str(i), short(c.claim_id), c.agent_id, f"{c.confidence:.2f}",
                  c.assertion[:75] + ("..." if len(c.assertion) > 75 else ""))
    console.print(t)
    return console


def render_revocation_demo(store: lattice.LatticeStore) -> Console:
    """Show revocation cascade: revoke the inflated 'over_claim' and watch downstream go COMPROMISED."""
    console = Console(record=True, width=110)
    target = store._demo["over"]
    result = store.revoke_claim(target, agent_id="analyzer", reason="Speculative attribution, not evidence-backed.")
    t = Table(title="Revocation Waterfall", title_style="bold red")
    t.add_column("Field", style="cyan")
    t.add_column("Value", style="white")
    t.add_row("Revoked claim", short(result.revoked_claim_id))
    t.add_row("Reason", "Speculative attribution, not evidence-backed.")
    t.add_row("Compromised dependents", ", ".join(short(c) for c in result.compromised_claim_ids) or "(none)")
    t.add_row("Total affected", str(result.total_affected))
    console.print(t)
    return console


def main() -> None:
    store = build_investigation()
    print(f"OK investigation built at {WORKSPACE}/.lattice/lattice.db")

    captures = [
        ("01_stats.svg", "lattice stats", lambda s: render_stats(s)),
        ("02_claims.svg", "lattice claims", lambda s: render_claims(s)),
        ("03_audit.svg", "lattice audit", lambda s: render_audit(s)),
        ("04_trace.svg", "lattice trace <final>", lambda s: render_trace(s, store._demo["final"])),
        ("05_revoke.svg", "lattice revoke (waterfall)", lambda s: render_revocation_demo(s)),
    ]

    for filename, title, fn in captures:
        c = fn(store)
        c.save_svg(str(OUT / filename), title=title)
        size = (OUT / filename).stat().st_size
        print(f"OK {filename} ({size // 1024} KB)")


if __name__ == "__main__":
    main()
