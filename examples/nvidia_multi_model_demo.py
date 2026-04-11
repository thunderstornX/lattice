#!/usr/bin/env python3
"""
LATTICE Multi-Model OSINT Demo (NVIDIA NIM API)

Demonstrates LATTICE accountability on a real multi-agent pipeline where
different LLM models act as specialized agents:

  - Harvester (Llama 3.3 70B): Extracts raw intelligence from a scenario
  - Analyzer (DeepSeek V3.2): Correlates findings, assesses confidence
  - Reporter (Mistral Large 3): Synthesizes final assessment

Every LLM call is captured as a signed, content-addressed claim in the
LATTICE DAG with full traceability, effective confidence, and audit.

Usage:
    export NVIDIA_API_KEY="nvapi-..."
    python3 examples/nvidia_multi_model_demo.py

Requires: pip install lattice-core requests
"""

import json
import os
import sys
import time
import requests

# Add parent dir to path for local dev
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import lattice


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY", "")
NVIDIA_API_URL = "https://integrate.api.nvidia.com/v1/chat/completions"

MODELS = {
    "harvester": "meta/llama-3.3-70b-instruct",
    "analyzer": "nvidia/llama-3.3-nemotron-super-49b-v1.5",
    "reporter": "mistralai/mistral-medium-3-instruct",
}

# The investigation scenario (simulated OSINT target)
SCENARIO = """You are investigating a suspicious domain: darkflow-services.net

Known facts gathered from public sources:
- Domain registered 2024-01-15 via NameSilo (privacy-protected WHOIS)
- DNS A record: 185.220.101.42 (AS60729, Stormwall s.r.o., Czech Republic)
- Same IP hosts 12 other domains, 8 of which are flagged on abuse databases
- SSL certificate: Lets Encrypt, issued 2024-01-15, CN=darkflow-services.net
- Reverse DNS: no PTR record configured
- Shodan: ports 22 (OpenSSH 8.9), 80 (nginx 1.24), 443 (nginx 1.24), 8443 (unknown service)
- HTTP response on port 8443: JSON API with status active and version 2.1.4
- VirusTotal: 3/90 vendors flag the domain as malicious (phishing)
- URLhaus: no entries
- The domain appears in 2 Telegram channels known for distributing infostealers
- Certificate transparency logs show no other certificates for this domain"""


def call_nvidia(model: str, system_prompt: str, user_prompt: str) -> str:
    """Call NVIDIA NIM API and return the response text."""
    headers = {
        "Authorization": f"Bearer {NVIDIA_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 1024,
    }
    for attempt in range(3):
        try:
            resp = requests.post(NVIDIA_API_URL, headers=headers, json=payload, timeout=90)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError) as e:
            if attempt < 2:
                print(f"    Retry {attempt + 1}/2 ({model})...")
                time.sleep(2)
            else:
                raise


def extract_json(text: str, expect_type="array"):
    """Robustly extract JSON from LLM response (handles code blocks, preamble)."""
    raw = text.strip()

    # Try extracting from markdown code blocks first
    if "```" in raw:
        parts = raw.split("```")
        for i in range(1, len(parts), 2):  # odd-indexed parts are inside blocks
            block = parts[i].strip()
            if block.startswith("json"):
                block = block[4:].strip()
            try:
                return json.loads(block)
            except json.JSONDecodeError:
                continue

    # Try finding raw JSON
    if expect_type == "array":
        start, end = raw.find('['), raw.rfind(']')
    else:
        start, end = raw.find('{'), raw.rfind('}')

    if start >= 0 and end > start:
        try:
            return json.loads(raw[start:end + 1])
        except json.JSONDecodeError:
            pass

    # Last resort: try the whole thing
    return json.loads(raw)


def main():
    if not NVIDIA_API_KEY:
        print("Error: Set NVIDIA_API_KEY environment variable")
        sys.exit(1)

    print("=" * 70)
    print("LATTICE Multi-Model OSINT Demo")
    print("=" * 70)
    print()

    # Initialize LATTICE
    store = lattice.init(":memory:")

    harvester = store.agent("harvester", role="collector")
    analyzer = store.agent("analyzer", role="analyst")
    reporter = store.agent("reporter", role="reporter")

    print(f"[+] Agents registered:")
    print(f"    Harvester: {MODELS['harvester']}")
    print(f"    Analyzer:  {MODELS['analyzer']}")
    print(f"    Reporter:  {MODELS['reporter']}")
    print()

    # -----------------------------------------------------------------------
    # Phase 1: Harvester extracts structured intelligence
    # -----------------------------------------------------------------------
    print("[Phase 1] Harvester extracting intelligence...")
    t0 = time.perf_counter()

    harvester_prompt = """You are an OSINT data extraction agent. Extract exactly 5 findings from the input as valid JSON.

Rules:
- Output a JSON array of 5 objects
- Each object has keys: "finding" (string), "confidence" (number 0-1), "source" (string), "indicators" (array of strings)
- All string values MUST be in double quotes
- Output ONLY valid JSON, no explanation

Example format:
[{"finding": "Example finding text", "confidence": 0.9, "source": "DNS records", "indicators": ["1.2.3.4"]}]"""

    harvester_raw = call_nvidia(MODELS["harvester"], harvester_prompt, SCENARIO)
    t_harvest = time.perf_counter() - t0
    print(f"    Harvester responded in {t_harvest:.1f}s")

    # Store the raw scenario as evidence
    scenario_eid = store.evidence(SCENARIO)

    # Store harvester's raw output as evidence
    harvest_eid = store.evidence(harvester_raw)

    # Create harvester claim
    harvest_claim = harvester.claim(
        assertion=f"Extracted structured intelligence from darkflow-services.net investigation using {MODELS['harvester']}",
        evidence=[scenario_eid, harvest_eid],
        confidence=0.85,
        method=f"llm:{MODELS['harvester']}",
        metadata={"model": MODELS["harvester"], "latency_s": round(t_harvest, 2)},
    )
    print(f"    Claim: {harvest_claim.claim_id[:16]}...")
    print()

    # Parse individual findings and create sub-claims
    finding_claims = []
    try:
        # Try to extract JSON from the response
        findings = extract_json(harvester_raw, expect_type="array")

        for i, f in enumerate(findings[:5]):
            f_eid = store.evidence(json.dumps(f))
            f_claim = harvester.claim(
                assertion=f["finding"],
                evidence=[harvest_eid, f_eid],
                confidence=f.get("confidence", 0.7),
                method=f"llm:{MODELS['harvester']}:extraction",
                metadata={"source": f.get("source", "unknown"), "finding_index": i},
            )
            finding_claims.append(f_claim)
            print(f"    Finding {i+1}: [{f.get('confidence', 0.7):.2f}] {f['finding'][:80]}...")
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        print(f"    Warning: Could not parse structured findings ({e}), using raw output")
        f_claim = harvester.claim(
            assertion="Raw intelligence extraction (unstructured)",
            evidence=[harvest_eid],
            confidence=0.6,
            method=f"llm:{MODELS['harvester']}:raw",
        )
        finding_claims.append(f_claim)

    print()

    # -----------------------------------------------------------------------
    # Phase 2: Analyzer correlates and assesses
    # -----------------------------------------------------------------------
    print("[Phase 2] Analyzer correlating findings...")
    t0 = time.perf_counter()

    analyzer_prompt = """You are a threat intelligence analyst. Given a set of OSINT findings 
about a suspicious domain, provide a correlation analysis.

Your response must be a JSON object with:
- "threat_assessment": overall assessment (one paragraph)
- "threat_level": one of "critical", "high", "medium", "low", "benign"
- "confidence": float 0.0-1.0 for your overall assessment
- "correlations": list of strings describing connections between findings
- "gaps": list of strings describing what intelligence is missing
- "recommended_actions": list of next investigative steps

Return ONLY the JSON object, no other text."""

    analyzer_input = f"SCENARIO:\n{SCENARIO}\n\nHARVESTER FINDINGS:\n{harvester_raw}"
    analyzer_raw = call_nvidia(MODELS["analyzer"], analyzer_prompt, analyzer_input)
    t_analyze = time.perf_counter() - t0
    print(f"    Analyzer responded in {t_analyze:.1f}s")

    # Store analyzer output as evidence
    analyze_eid = store.evidence(analyzer_raw)

    # Analyzer claim references all harvester finding claims
    finding_ids = [fc.claim_id for fc in finding_claims]
    analyze_claim = analyzer.claim(
        assertion=f"Threat correlation analysis of darkflow-services.net using {MODELS['analyzer']}",
        evidence=finding_ids + [analyze_eid],
        confidence=0.75,
        method=f"llm:{MODELS['analyzer']}",
        metadata={"model": MODELS["analyzer"], "latency_s": round(t_analyze, 2)},
    )
    print(f"    Claim: {analyze_claim.claim_id[:16]}...")

    try:
        analysis = extract_json(analyzer_raw, expect_type="object")
        print(f"    Threat level: {analysis.get('threat_level', 'unknown')}")
        print(f"    Confidence: {analysis.get('confidence', 'N/A')}")
        if analysis.get("gaps"):
            print(f"    Intelligence gaps: {len(analysis['gaps'])}")
    except (json.JSONDecodeError, KeyError):
        print("    (Could not parse structured analysis)")

    print()

    # -----------------------------------------------------------------------
    # Phase 3: Reporter synthesizes final assessment
    # -----------------------------------------------------------------------
    print("[Phase 3] Reporter synthesizing final assessment...")
    t0 = time.perf_counter()

    reporter_prompt = """You are a senior threat intelligence reporter. Given raw findings and 
a correlation analysis, write a concise executive summary (3-4 paragraphs).

Include:
1. Key finding and threat level
2. Evidence quality assessment (what is solid vs. circumstantial)
3. Confidence level with explicit caveats about what you DON'T know
4. Recommended immediate actions

Write in professional threat intelligence report style. Be precise about 
uncertainty -- state clearly where evidence is strong and where it is weak."""

    reporter_input = f"SCENARIO:\n{SCENARIO}\n\nFINDINGS:\n{harvester_raw}\n\nANALYSIS:\n{analyzer_raw}"
    reporter_raw = call_nvidia(MODELS["reporter"], reporter_prompt, reporter_input)
    t_report = time.perf_counter() - t0
    print(f"    Reporter responded in {t_report:.1f}s")

    # Store reporter output
    report_eid = store.evidence(reporter_raw)

    # Final report claim references analyzer claim
    report_claim = reporter.claim(
        assertion=f"Executive threat assessment of darkflow-services.net using {MODELS['reporter']}",
        evidence=[analyze_claim.claim_id, report_eid],
        confidence=0.70,
        method=f"llm:{MODELS['reporter']}",
        metadata={"model": MODELS["reporter"], "latency_s": round(t_report, 2)},
    )
    print(f"    Claim: {report_claim.claim_id[:16]}...")
    print()

    # -----------------------------------------------------------------------
    # LATTICE Accountability
    # -----------------------------------------------------------------------
    print("=" * 70)
    print("LATTICE Accountability Report")
    print("=" * 70)
    print()

    # Stats
    print(f"[Stats]")
    print(f"  Agents: {store.agent_count()}")
    print(f"  Claims: {store.claim_count()}")
    print(f"  Evidence blobs: {store.evidence_count()}")
    print()

    # Trace from final report back to raw evidence
    print(f"[Trace] Walking backward from final report:")
    chain = store.trace(report_claim.claim_id)
    for i, c in enumerate(chain):
        eff = store.effective_confidence(c.claim_id)
        marker = " <-- INFLATED" if c.confidence - eff > 0.01 else ""
        print(f"  {'  ' * i}[{c.agent_id}] conf={c.confidence:.2f} eff={eff:.2f}{marker}")
        print(f"  {'  ' * i}  {c.assertion[:70]}...")
    print()

    # Effective confidence
    print(f"[Effective Confidence]")
    from lattice.dag import effective_confidence_bulk
    bulk_eff = effective_confidence_bulk(store)
    for cid, eff in sorted(bulk_eff.items(), key=lambda x: x[1]):
        claim = store.get_claim(cid)
        if claim:
            flag = " ** INFLATED **" if claim.confidence - eff > 0.01 else ""
            print(f"  {cid[:12]}... stated={claim.confidence:.2f} effective={eff:.2f} [{claim.agent_id}]{flag}")
    print()

    # Audit
    print(f"[Audit]")
    issues = store.audit()
    if issues:
        for issue in issues:
            print(f"  [{issue.issue_type}] {issue.claim_id[:12]}... {issue.description}")
    else:
        print("  No issues found.")
    print()

    # Verify signatures
    print(f"[Signature Verification]")
    results = store.verify()
    valid = sum(1 for r in results if r.valid)
    print(f"  {valid}/{len(results)} signatures valid")
    print()

    # Revocation demo
    print(f"[Revocation Demo]")
    print(f"  Simulating: one harvester finding is later discovered to be wrong...")
    if finding_claims:
        target = finding_claims[0]
        rev = store.revoke_claim(target.claim_id, agent_id="harvester", reason="Source retracted data")
        print(f"  Revoked: {target.claim_id[:12]}...")
        print(f"  Downstream compromised: {len(rev.compromised_claim_ids)} claims")
        for cid in rev.compromised_claim_ids:
            c = store.get_claim(cid)
            status = store.get_claim_status(cid)
            if c:
                print(f"    {cid[:12]}... [{c.agent_id}] -> {status}")
    print()

    # Print the actual report
    print("=" * 70)
    print("FINAL REPORT (generated by", MODELS["reporter"] + ")")
    print("=" * 70)
    print()
    print(reporter_raw)
    print()

    # Timing summary
    total = t_harvest + t_analyze + t_report
    print(f"[Timing] Harvest: {t_harvest:.1f}s | Analyze: {t_analyze:.1f}s | Report: {t_report:.1f}s | Total: {total:.1f}s")


if __name__ == "__main__":
    main()
