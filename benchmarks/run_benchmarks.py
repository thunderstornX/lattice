#!/usr/bin/env python3
"""LATTICE performance benchmarks for the research paper.

Produces:
  1. Scalability curves (claim creation time vs DAG size)
  2. Operation overhead breakdown
  3. Revocation waterfall performance vs chain length
  4. Effective confidence computation cost vs DAG size
  5. Baseline comparison (with vs without LATTICE instrumentation)
  6. Case study: synthetic OSINT pipeline
"""

from __future__ import annotations

import json
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import lattice
from lattice.dag import (
    audit,
    effective_confidence,
    effective_confidence_bulk,
    stats,
    trace,
    verify_all,
)
from lattice.monitor import lattice_monitor


def timeit(fn, *args, repeats=10, **kwargs):
    """Run fn repeats times, return (mean_ms, std_ms, all_times_ms)."""
    times = []
    for _ in range(repeats):
        start = time.perf_counter()
        result = fn(*args, **kwargs)
        elapsed = (time.perf_counter() - start) * 1000
        times.append(elapsed)
    return statistics.mean(times), statistics.stdev(times) if len(times) > 1 else 0.0, times, result


def benchmark_scalability():
    """Experiment 1: Claim creation time vs DAG size."""
    print("\n" + "=" * 70)
    print("EXPERIMENT 1: Scalability - Claim Creation Time vs DAG Size")
    print("=" * 70)

    sizes = [10, 50, 100, 500, 1000, 2000]
    results = []

    for n in sizes:
        store = lattice.init(":memory:")
        agent = store.agent("bench", role="benchmarker")

        # Pre-populate with n-1 claims in a chain
        prev_id = None
        for i in range(n - 1):
            evidence = [prev_id] if prev_id else []
            c = agent.claim(f"claim {i}", evidence=evidence, confidence=0.8, method="bench")
            prev_id = c.claim_id

        # Measure the cost of adding one more claim to a DAG of size n
        evidence = [prev_id] if prev_id else []
        mean_ms, std_ms, _, _ = timeit(
            agent.claim, f"final claim", evidence=evidence,
            confidence=0.8, method="bench", repeats=50
        )

        results.append({"dag_size": n, "mean_ms": round(mean_ms, 4), "std_ms": round(std_ms, 4)})
        print(f"  DAG size {n:>6}: {mean_ms:.4f} ms (+/- {std_ms:.4f})")
        store.close()

    return results


def benchmark_operations():
    """Experiment 2: Individual operation costs."""
    print("\n" + "=" * 70)
    print("EXPERIMENT 2: Operation Overhead Breakdown")
    print("=" * 70)

    store = lattice.init(":memory:")
    agent = store.agent("bench", role="benchmarker")

    # Build a 100-claim chain
    prev_id = None
    all_ids = []
    for i in range(100):
        evidence = [prev_id] if prev_id else []
        c = agent.claim(f"claim {i}", evidence=evidence, confidence=0.5 + (i % 5) * 0.1, method="bench")
        prev_id = c.claim_id
        all_ids.append(c.claim_id)

    results = {}

    # Evidence storage
    mean_ms, std_ms, _, _ = timeit(store.evidence, "benchmark data blob", repeats=100)
    results["evidence_storage"] = {"mean_ms": round(mean_ms, 4), "std_ms": round(std_ms, 4)}
    print(f"  Evidence storage:      {mean_ms:.4f} ms (+/- {std_ms:.4f})")

    # Claim creation + signing
    mean_ms, std_ms, _, _ = timeit(
        agent.claim, "bench claim", evidence=[all_ids[-1]],
        confidence=0.8, method="bench", repeats=100
    )
    results["claim_creation"] = {"mean_ms": round(mean_ms, 4), "std_ms": round(std_ms, 4)}
    print(f"  Claim creation+sign:   {mean_ms:.4f} ms (+/- {std_ms:.4f})")

    # Signature verification (all 100+)
    mean_ms, std_ms, _, _ = timeit(verify_all, store, repeats=10)
    results["verify_all_100"] = {"mean_ms": round(mean_ms, 4), "std_ms": round(std_ms, 4)}
    print(f"  Verify all (100+):     {mean_ms:.4f} ms (+/- {std_ms:.4f})")

    # Trace (full chain)
    mean_ms, std_ms, _, _ = timeit(trace, store, all_ids[-1], repeats=50)
    results["trace_100_chain"] = {"mean_ms": round(mean_ms, 4), "std_ms": round(std_ms, 4)}
    print(f"  Trace (100 chain):     {mean_ms:.4f} ms (+/- {std_ms:.4f})")

    # Audit
    mean_ms, std_ms, _, _ = timeit(audit, store, repeats=20)
    results["audit_100"] = {"mean_ms": round(mean_ms, 4), "std_ms": round(std_ms, 4)}
    print(f"  Audit (100 claims):    {mean_ms:.4f} ms (+/- {std_ms:.4f})")

    # Effective confidence (single)
    mean_ms, std_ms, _, _ = timeit(effective_confidence, store, all_ids[-1], repeats=50)
    results["eff_conf_single"] = {"mean_ms": round(mean_ms, 4), "std_ms": round(std_ms, 4)}
    print(f"  Eff. confidence (1):   {mean_ms:.4f} ms (+/- {std_ms:.4f})")

    # Effective confidence bulk
    mean_ms, std_ms, _, _ = timeit(effective_confidence_bulk, store, repeats=20)
    results["eff_conf_bulk_100"] = {"mean_ms": round(mean_ms, 4), "std_ms": round(std_ms, 4)}
    print(f"  Eff. confidence bulk:  {mean_ms:.4f} ms (+/- {std_ms:.4f})")

    # Stats
    mean_ms, std_ms, _, _ = timeit(stats, store, repeats=20)
    results["stats_100"] = {"mean_ms": round(mean_ms, 4), "std_ms": round(std_ms, 4)}
    print(f"  Stats:                 {mean_ms:.4f} ms (+/- {std_ms:.4f})")

    store.close()
    return results


def benchmark_revocation():
    """Experiment 3: Revocation waterfall cost vs chain length."""
    print("\n" + "=" * 70)
    print("EXPERIMENT 3: Revocation Waterfall Performance")
    print("=" * 70)

    sizes = [10, 50, 100, 500, 1000, 2000]
    results = []

    for n in sizes:
        store = lattice.init(":memory:")
        agent = store.agent("bench", role="benchmarker")

        # Build a chain of n claims
        prev_id = None
        first_id = None
        for i in range(n):
            evidence = [prev_id] if prev_id else []
            c = agent.claim(f"claim {i}", evidence=evidence, confidence=0.8, method="bench")
            if first_id is None:
                first_id = c.claim_id
            prev_id = c.claim_id

        # Measure revocation of the root (maximum waterfall)
        mean_ms, std_ms, _, result = timeit(
            store.revoke_claim, first_id, "bench", "benchmark revocation",
            repeats=1  # can only revoke once
        )
        affected = result.total_affected

        results.append({
            "chain_length": n,
            "mean_ms": round(mean_ms, 4),
            "affected": affected,
        })
        print(f"  Chain {n:>5}: {mean_ms:.4f} ms, {affected} claims affected")
        store.close()

    return results


def benchmark_effective_confidence_scaling():
    """Experiment 4: Effective confidence cost vs DAG size."""
    print("\n" + "=" * 70)
    print("EXPERIMENT 4: Effective Confidence Scaling")
    print("=" * 70)

    sizes = [10, 50, 100, 500, 1000, 2000]
    results = []

    for n in sizes:
        store = lattice.init(":memory:")
        agent = store.agent("bench", role="benchmarker")

        # Build a chain
        prev_id = None
        last_id = None
        for i in range(n):
            evidence = [prev_id] if prev_id else []
            c = agent.claim(f"claim {i}", evidence=evidence, confidence=0.5 + (i % 5) * 0.1, method="bench")
            prev_id = c.claim_id
            last_id = c.claim_id

        # Single effective confidence on the tip
        mean_single, std_single, _, _ = timeit(effective_confidence, store, last_id, repeats=20)

        # Bulk effective confidence
        mean_bulk, std_bulk, _, _ = timeit(effective_confidence_bulk, store, repeats=10)

        results.append({
            "dag_size": n,
            "single_mean_ms": round(mean_single, 4),
            "single_std_ms": round(std_single, 4),
            "bulk_mean_ms": round(mean_bulk, 4),
            "bulk_std_ms": round(std_bulk, 4),
        })
        print(f"  DAG {n:>6}: single {mean_single:.4f} ms, bulk {mean_bulk:.4f} ms")
        store.close()

    return results


def benchmark_baseline_comparison():
    """Experiment 5: Overhead of LATTICE instrumentation vs bare function."""
    print("\n" + "=" * 70)
    print("EXPERIMENT 5: Instrumentation Overhead (With vs Without LATTICE)")
    print("=" * 70)

    # Bare function
    def bare_dns_lookup(domain: str) -> dict:
        """DNS lookup for {domain}"""
        return {"domain": domain, "ip": "93.184.216.34", "ttl": 3600}

    # Measure bare
    bare_times = []
    for _ in range(1000):
        start = time.perf_counter()
        bare_dns_lookup("example.com")
        bare_times.append((time.perf_counter() - start) * 1000)
    bare_mean = statistics.mean(bare_times)
    bare_std = statistics.stdev(bare_times)

    # Instrumented
    store = lattice.init(":memory:")
    agent = store.agent("harvester", role="collector")

    @lattice_monitor(agent, method="tool:dns")
    def instrumented_dns_lookup(domain: str) -> dict:
        """DNS lookup for {domain}"""
        return {"domain": domain, "ip": "93.184.216.34", "ttl": 3600}

    inst_times = []
    for _ in range(1000):
        start = time.perf_counter()
        instrumented_dns_lookup("example.com")
        inst_times.append((time.perf_counter() - start) * 1000)
    inst_mean = statistics.mean(inst_times)
    inst_std = statistics.stdev(inst_times)

    overhead = inst_mean - bare_mean
    overhead_pct = (overhead / bare_mean * 100) if bare_mean > 0 else float("inf")

    results = {
        "bare_mean_ms": round(bare_mean, 6),
        "bare_std_ms": round(bare_std, 6),
        "instrumented_mean_ms": round(inst_mean, 4),
        "instrumented_std_ms": round(inst_std, 4),
        "overhead_ms": round(overhead, 4),
        "overhead_pct": round(overhead_pct, 1),
        "iterations": 1000,
    }

    print(f"  Bare function:     {bare_mean:.6f} ms (+/- {bare_std:.6f})")
    print(f"  With @lattice_monitor: {inst_mean:.4f} ms (+/- {inst_std:.4f})")
    print(f"  Overhead:          {overhead:.4f} ms ({overhead_pct:.1f}%)")

    store.close()
    return results


def benchmark_case_study():
    """Experiment 6: Synthetic OSINT pipeline case study.

    Simulates a realistic 3-agent investigation pipeline:
    - Harvester: collects data from 5 sources
    - Analyzer: correlates findings, produces intermediate assessments
    - Reporter: synthesizes final report

    Measures end-to-end cost and DAG characteristics.
    """
    print("\n" + "=" * 70)
    print("EXPERIMENT 6: Case Study - Synthetic OSINT Pipeline")
    print("=" * 70)

    store = lattice.init(":memory:")
    harvester = store.agent("harvester", role="collector", description="Data collection")
    analyzer = store.agent("analyzer", role="analyst", description="Correlation and analysis")
    reporter = store.agent("reporter", role="reporter", description="Final assessment")

    start_total = time.perf_counter()

    # Phase 1: Collection (harvester gathers from 5 sources)
    collection_start = time.perf_counter()

    sources = [
        ("DNS resolution", "nslookup suspicious.example -> 198.51.100.42", 0.99, "tool:nslookup"),
        ("WHOIS lookup", "Registrar: ShadyRegistrar, Panama; Created: 2024-01-15", 0.95, "tool:whois"),
        ("HTTP fingerprint", "Server: nginx/1.18, PHP/7.4, tracking cookie present", 0.99, "tool:httpx"),
        ("Certificate transparency", "Let's Encrypt cert issued 2024-01-14, alt names: cdn.suspicious.example", 0.98, "tool:crt.sh"),
        ("Passive DNS history", "IP 198.51.100.42 seen hosting 12 other suspicious domains since 2023", 0.85, "tool:passivedns"),
    ]

    evidence_ids = []
    collection_claims = []
    for name, data, conf, method in sources:
        eid = store.evidence(data)
        evidence_ids.append(eid)
        c = harvester.claim(
            assertion=f"{name}: {data[:60]}",
            evidence=[eid],
            confidence=conf,
            method=method,
        )
        collection_claims.append(c)

    collection_time = (time.perf_counter() - collection_start) * 1000

    # Phase 2: Analysis (analyzer correlates findings)
    analysis_start = time.perf_counter()

    infra_claim = analyzer.claim(
        assertion="198.51.100.42 is on bulletproof hosting (ns1.bulletproof.example)",
        evidence=[collection_claims[0].claim_id, collection_claims[4].claim_id],
        confidence=0.80,
        method="llm:analysis",
    )

    attribution_claim = analyzer.claim(
        assertion="Operator uses Panama shell entity with bulletproof hosting pattern",
        evidence=[collection_claims[1].claim_id, infra_claim.claim_id],
        confidence=0.70,
        method="llm:analysis",
    )

    tech_claim = analyzer.claim(
        assertion="Infrastructure consistent with phishing kit deployment (nginx+PHP+tracking)",
        evidence=[collection_claims[2].claim_id, collection_claims[3].claim_id],
        confidence=0.75,
        method="llm:analysis",
    )

    analysis_time = (time.perf_counter() - analysis_start) * 1000

    # Phase 3: Reporting (reporter synthesizes)
    report_start = time.perf_counter()

    final_report = reporter.claim(
        assertion="ASSESSMENT: suspicious.example is likely a phishing operation "
                  "run by a threat actor using Panama-registered infrastructure "
                  "on bulletproof hosting, deploying nginx/PHP phishing kits",
        evidence=[
            infra_claim.claim_id,
            attribution_claim.claim_id,
            tech_claim.claim_id,
        ],
        confidence=0.75,
        method="analyst:synthesis",
    )

    report_time = (time.perf_counter() - report_start) * 1000
    total_time = (time.perf_counter() - start_total) * 1000

    # Measure analysis operations
    trace_result = trace(store, final_report.claim_id)
    audit_result = audit(store)
    verify_result = verify_all(store)
    eff_conf = effective_confidence(store, final_report.claim_id)
    eff_bulk = effective_confidence_bulk(store)
    stat_result = stats(store)

    # Count inflated
    inflated = [i for i in audit_result if i.issue_type == "inflated_confidence"]

    results = {
        "pipeline": {
            "total_agents": 3,
            "total_claims": store.claim_count(),
            "total_evidence": store.evidence_count(),
            "dag_depth": len(trace_result),
            "collection_time_ms": round(collection_time, 4),
            "analysis_time_ms": round(analysis_time, 4),
            "report_time_ms": round(report_time, 4),
            "total_pipeline_time_ms": round(total_time, 4),
        },
        "verification": {
            "all_signatures_valid": all(r.valid for r in verify_result),
            "audit_issues_total": len(audit_result),
            "inflated_confidence_flags": len(inflated),
        },
        "confidence_analysis": {
            "final_report_stated": final_report.confidence,
            "final_report_effective": eff_conf,
            "min_effective_in_dag": min(eff_bulk.values()),
            "avg_effective_in_dag": round(statistics.mean(eff_bulk.values()), 4),
            "claims_with_inflation": len(inflated),
        },
        "stats": stat_result,
    }

    print(f"\n  Pipeline:")
    print(f"    Agents: {results['pipeline']['total_agents']}")
    print(f"    Claims: {results['pipeline']['total_claims']}")
    print(f"    Evidence blobs: {results['pipeline']['total_evidence']}")
    print(f"    DAG depth: {results['pipeline']['dag_depth']}")
    print(f"    Collection: {collection_time:.4f} ms")
    print(f"    Analysis:   {analysis_time:.4f} ms")
    print(f"    Reporting:  {report_time:.4f} ms")
    print(f"    Total:      {total_time:.4f} ms")
    print(f"\n  Verification:")
    print(f"    All signatures valid: {results['verification']['all_signatures_valid']}")
    print(f"    Audit issues: {results['verification']['audit_issues_total']}")
    print(f"    Inflated confidence flags: {results['verification']['inflated_confidence_flags']}")
    print(f"\n  Confidence Analysis:")
    print(f"    Final report stated:    {final_report.confidence:.2f}")
    print(f"    Final report effective: {eff_conf:.2f}")
    print(f"    Min effective in DAG:   {min(eff_bulk.values()):.2f}")
    print(f"    Avg effective in DAG:   {statistics.mean(eff_bulk.values()):.2f}")

    # Show the trace
    print(f"\n  Trace from final report:")
    for i, c in enumerate(trace_result):
        ec = eff_bulk.get(c.claim_id, c.confidence)
        flag = " [INFLATED]" if c.confidence - ec > 0.01 and c.evidence else ""
        indent = "    " + "  " * i
        print(f"{indent}[{c.agent_id}] {c.confidence:.2f} (eff:{ec:.2f}){flag} {c.assertion[:55]}")

    store.close()
    return results


def main():
    print("LATTICE Performance Benchmarks")
    print(f"Python {sys.version}")
    print(f"LATTICE v{lattice.__version__}")

    all_results = {}

    all_results["scalability"] = benchmark_scalability()
    all_results["operations"] = benchmark_operations()
    all_results["revocation"] = benchmark_revocation()
    all_results["effective_confidence_scaling"] = benchmark_effective_confidence_scaling()
    all_results["baseline_comparison"] = benchmark_baseline_comparison()
    all_results["case_study"] = benchmark_case_study()

    # Save results
    out_path = os.path.join(os.path.dirname(__file__), "results.json")
    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\n{'=' * 70}")
    print(f"Results saved to {out_path}")


if __name__ == "__main__":
    main()
