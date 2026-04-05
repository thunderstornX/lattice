"""Local Observability Dashboard — FastAPI server + D3.js frontend.

Serves a single-file HTML dashboard that visualizes the LATTICE claim DAG.
All assets are inlined — no CDN dependencies, no external network calls.

Usage::

    lattice dashboard -d ./my-investigation     # CLI
    lattice dashboard --port 8080               # custom port

Programmatic::

    from lattice.dashboard import create_app
    app = create_app("/path/to/.lattice/lattice.db")
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from lattice.agent import verify_signature
from lattice.models import Claim
from lattice.revocation import get_claim_status, get_revocation, list_revocations
from lattice.store import LatticeStore

# ---------------------------------------------------------------------------
# FastAPI app factory
# ---------------------------------------------------------------------------


def create_app(db_path: str) -> FastAPI:
    """Create a FastAPI app bound to a specific LATTICE store.

    Args:
        db_path: Path to the SQLite database file (.lattice/lattice.db).

    Returns:
        A configured FastAPI application.
    """
    app = FastAPI(title="LATTICE Dashboard", version="1.0.0")

    def _store() -> LatticeStore:
        """Open a fresh connection per request (SQLite is fast for reads)."""
        return LatticeStore(db_path)

    # -- HTML frontend -----------------------------------------------------

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        """Serve the single-file D3.js dashboard."""
        return _DASHBOARD_HTML

    # -- API endpoints -----------------------------------------------------

    @app.get("/api/agents")
    async def api_agents() -> List[Dict[str, Any]]:
        """List all registered agents."""
        store = _store()
        agents = store.list_agents()
        store.close()
        return agents

    @app.get("/api/claims")
    async def api_claims(limit: int = 10000) -> List[Dict[str, Any]]:
        """List all claims with revocation status."""
        store = _store()
        claims = store.list_claims(limit=limit)
        result = []
        for c in claims:
            d = c.to_dict()
            d["status"] = get_claim_status(store._conn, c.claim_id)
            result.append(d)
        store.close()
        return result

    @app.get("/api/claims/{claim_id}")
    async def api_claim_detail(claim_id: str) -> Dict[str, Any]:
        """Get a single claim with full details and verification."""
        store = _store()
        try:
            # Resolve partial IDs
            resolved = _resolve_partial(store, claim_id)
            claim = store.get_claim(resolved)
        except Exception:
            store.close()
            raise HTTPException(status_code=404, detail=f"Claim '{claim_id}' not found")

        d = claim.to_dict()
        d["status"] = get_claim_status(store._conn, claim.claim_id)

        # Verify signature
        try:
            agent = store.get_agent(claim.agent_id)
            d["signature_valid"] = verify_signature(
                agent.public_key, claim.claim_id, claim.signature
            )
        except Exception:
            d["signature_valid"] = False

        # Revocation info
        rev = get_revocation(store._conn, claim.claim_id)
        if rev:
            d["revocation"] = {
                "revoked_by": rev.revoked_by,
                "revoked_at": rev.revoked_at,
                "reason": rev.reason,
            }

        store.close()
        return d

    @app.get("/api/claims/{claim_id}/trace")
    async def api_trace(claim_id: str) -> List[Dict[str, Any]]:
        """Trace a claim backward through its evidence chain."""
        store = _store()
        try:
            resolved = _resolve_partial(store, claim_id)
            chain = store.trace(resolved)
        except Exception:
            store.close()
            raise HTTPException(status_code=404, detail=f"Claim '{claim_id}' not found")
        result = []
        for c in chain:
            d = c.to_dict()
            d["status"] = get_claim_status(store._conn, c.claim_id)
            result.append(d)
        store.close()
        return result

    @app.get("/api/claims/{claim_id}/verify")
    async def api_verify_claim(claim_id: str) -> Dict[str, Any]:
        """Verify signature and content integrity of a single claim."""
        store = _store()
        try:
            resolved = _resolve_partial(store, claim_id)
            claim = store.get_claim(resolved)
        except Exception:
            store.close()
            raise HTTPException(status_code=404, detail=f"Claim '{claim_id}' not found")

        from lattice.models import compute_claim_id

        recomputed = compute_claim_id(
            claim.agent_id, claim.assertion, claim.evidence,
            claim.method, claim.timestamp, claim.metadata,
        )
        content_valid = recomputed == claim.claim_id

        sig_valid = False
        try:
            agent = store.get_agent(claim.agent_id)
            sig_valid = verify_signature(agent.public_key, claim.claim_id, claim.signature)
        except Exception:
            pass

        status = get_claim_status(store._conn, claim.claim_id) if content_valid else "TAMPERED"
        store.close()
        return {
            "claim_id": claim.claim_id,
            "content_integrity": content_valid,
            "signature_valid": sig_valid,
            "status": status,
        }

    @app.get("/api/revocations")
    async def api_revocations() -> List[Dict[str, Any]]:
        """List all revocation records."""
        store = _store()
        revs = list_revocations(store._conn)
        store.close()
        return [
            {
                "revoked_claim_id": r.revoked_claim_id,
                "revoked_by": r.revoked_by,
                "revoked_at": r.revoked_at,
                "reason": r.reason,
            }
            for r in revs
        ]

    @app.get("/api/graph")
    async def api_graph(limit: int = 10000) -> Dict[str, Any]:
        """Return the full DAG as nodes + edges for D3.js visualization."""
        store = _store()
        claims = store.list_claims(limit=limit)
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []

        claim_ids = {c.claim_id for c in claims}

        for c in claims:
            status = get_claim_status(store._conn, c.claim_id)
            nodes.append({
                "id": c.claim_id,
                "label": c.assertion[:60],
                "agent_id": c.agent_id,
                "confidence": c.confidence,
                "method": c.method,
                "status": status,
                "type": "claim",
            })
            for ref in c.evidence:
                edges.append({"source": c.claim_id, "target": ref})
                # Add evidence leaf nodes if not already a claim
                if ref not in claim_ids:
                    nodes.append({
                        "id": ref,
                        "label": f"Evidence {ref[:8]}…",
                        "agent_id": "",
                        "confidence": 1.0,
                        "method": "raw",
                        "status": "EVIDENCE",
                        "type": "evidence",
                    })
                    claim_ids.add(ref)  # prevent duplicates

        store.close()
        return {"nodes": nodes, "edges": edges}

    @app.get("/api/stats")
    async def api_stats() -> Dict[str, Any]:
        """Investigation summary statistics."""
        from lattice.dag import stats as dag_stats
        store = _store()
        s = dag_stats(store)
        s["total_revocations"] = len(list_revocations(store._conn))
        store.close()
        return s

    return app


def _resolve_partial(store: LatticeStore, partial: str) -> str:
    """Resolve a partial claim ID to the full ID."""
    if len(partial) == 64:
        return partial
    claims = store.list_claims(limit=100_000)
    matches = [c for c in claims if c.claim_id.startswith(partial)]
    if len(matches) == 1:
        return matches[0].claim_id
    return partial


# ---------------------------------------------------------------------------
# Inlined HTML/JS/CSS dashboard — no external dependencies
# ---------------------------------------------------------------------------

_DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>LATTICE Dashboard</title>
<style>
  :root {
    --bg: #0f172a; --surface: #1e293b; --border: #334155;
    --text: #e2e8f0; --muted: #94a3b8; --accent: #60a5fa;
    --green: #34d399; --yellow: #fbbf24; --red: #f87171; --purple: #a78bfa;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: 'SF Mono', 'Fira Code', monospace; background: var(--bg); color: var(--text); overflow: hidden; }
  #header { display: flex; align-items: center; justify-content: space-between; padding: 12px 20px; background: var(--surface); border-bottom: 1px solid var(--border); }
  #header h1 { font-size: 16px; color: var(--accent); }
  #header .stats { font-size: 12px; color: var(--muted); }
  #graph-container { width: 100vw; height: calc(100vh - 48px); }
  svg { width: 100%; height: 100%; }

  /* Modal */
  #modal-overlay { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.6); z-index: 100; }
  #modal { position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%); background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 24px; max-width: 640px; width: 90%; max-height: 80vh; overflow-y: auto; z-index: 101; }
  #modal h2 { font-size: 14px; color: var(--accent); margin-bottom: 16px; }
  #modal .field { margin-bottom: 10px; }
  #modal .field label { display: block; font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 2px; }
  #modal .field .value { font-size: 13px; word-break: break-all; }
  #modal .close-btn { position: absolute; top: 12px; right: 16px; background: none; border: none; color: var(--muted); font-size: 18px; cursor: pointer; }
  #modal .close-btn:hover { color: var(--text); }
  .status-VALID { color: var(--green); }
  .status-REVOKED { color: var(--red); }
  .status-COMPROMISED { color: var(--yellow); }
  .status-EVIDENCE { color: var(--purple); }
  .sig-valid { color: var(--green); }
  .sig-invalid { color: var(--red); }

  /* Legend */
  #legend { position: fixed; bottom: 16px; left: 16px; background: var(--surface); border: 1px solid var(--border); border-radius: 6px; padding: 10px 14px; font-size: 11px; z-index: 50; }
  #legend div { display: flex; align-items: center; margin: 3px 0; }
  #legend .dot { width: 10px; height: 10px; border-radius: 50%; margin-right: 8px; display: inline-block; }
</style>
</head>
<body>
<div id="header">
  <h1>🔗 LATTICE Dashboard</h1>
  <div class="stats" id="stats-bar">Loading…</div>
</div>
<div id="graph-container"><svg id="dag-svg"></svg></div>

<div id="legend">
  <div><span class="dot" style="background:#34d399"></span> Valid</div>
  <div><span class="dot" style="background:#f87171"></span> Revoked</div>
  <div><span class="dot" style="background:#fbbf24"></span> Compromised</div>
  <div><span class="dot" style="background:#a78bfa"></span> Evidence</div>
</div>

<div id="modal-overlay" onclick="closeModal()">
  <div id="modal" onclick="event.stopPropagation()">
    <button class="close-btn" onclick="closeModal()">✕</button>
    <h2 id="modal-title">Claim Details</h2>
    <div id="modal-body"></div>
  </div>
</div>

<script>
// Minimal D3-like force simulation — no external library needed
// We use the browser's requestAnimationFrame + basic physics

const STATE = { nodes: [], edges: [], nodeMap: {} };
const COLORS = { VALID: '#34d399', REVOKED: '#f87171', COMPROMISED: '#fbbf24', EVIDENCE: '#a78bfa', TAMPERED: '#f87171' };

async function init() {
  const [graphResp, statsResp] = await Promise.all([
    fetch('/api/graph'), fetch('/api/stats')
  ]);
  const graph = await graphResp.json();
  const stats = await statsResp.json();

  document.getElementById('stats-bar').textContent =
    `${stats.total_agents} agents · ${stats.total_claims} claims · ${stats.total_evidence} evidence · ${stats.total_revocations || 0} revocations`;

  STATE.nodes = graph.nodes.map((n, i) => ({
    ...n, x: 400 + Math.random() * 600, y: 300 + Math.random() * 400,
    vx: 0, vy: 0, radius: n.type === 'evidence' ? 6 : 10
  }));
  STATE.edges = graph.edges;
  STATE.nodeMap = {};
  STATE.nodes.forEach(n => STATE.nodeMap[n.id] = n);

  render();
  simulate();
}

function simulate() {
  const alpha = 0.3, repulsion = 800, linkDist = 120, damping = 0.85;
  const cx = window.innerWidth / 2, cy = (window.innerHeight - 48) / 2;

  function tick() {
    // Center gravity
    STATE.nodes.forEach(n => {
      n.vx += (cx - n.x) * 0.001;
      n.vy += (cy - n.y) * 0.001;
    });

    // Repulsion
    for (let i = 0; i < STATE.nodes.length; i++) {
      for (let j = i + 1; j < STATE.nodes.length; j++) {
        const a = STATE.nodes[i], b = STATE.nodes[j];
        let dx = b.x - a.x, dy = b.y - a.y;
        let dist = Math.sqrt(dx*dx + dy*dy) || 1;
        let force = repulsion / (dist * dist);
        a.vx -= dx / dist * force; a.vy -= dy / dist * force;
        b.vx += dx / dist * force; b.vy += dy / dist * force;
      }
    }

    // Link attraction
    STATE.edges.forEach(e => {
      const s = STATE.nodeMap[e.source], t = STATE.nodeMap[e.target];
      if (!s || !t) return;
      let dx = t.x - s.x, dy = t.y - s.y;
      let dist = Math.sqrt(dx*dx + dy*dy) || 1;
      let force = (dist - linkDist) * 0.005;
      s.vx += dx / dist * force; s.vy += dy / dist * force;
      t.vx -= dx / dist * force; t.vy -= dy / dist * force;
    });

    // Apply velocity
    STATE.nodes.forEach(n => {
      n.vx *= damping; n.vy *= damping;
      n.x += n.vx; n.y += n.vy;
    });

    render();
    requestAnimationFrame(tick);
  }
  tick();
}

function render() {
  const svg = document.getElementById('dag-svg');
  // Clear and rebuild (simple approach — fast enough for <1000 nodes)
  svg.innerHTML = '';

  const defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
  const marker = document.createElementNS('http://www.w3.org/2000/svg', 'marker');
  marker.setAttribute('id', 'arrow');
  marker.setAttribute('viewBox', '0 0 10 10');
  marker.setAttribute('refX', '20'); marker.setAttribute('refY', '5');
  marker.setAttribute('markerWidth', '6'); marker.setAttribute('markerHeight', '6');
  marker.setAttribute('orient', 'auto-start-reverse');
  const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  path.setAttribute('d', 'M 0 0 L 10 5 L 0 10 z');
  path.setAttribute('fill', '#475569');
  marker.appendChild(path);
  defs.appendChild(marker);
  svg.appendChild(defs);

  // Edges
  STATE.edges.forEach(e => {
    const s = STATE.nodeMap[e.source], t = STATE.nodeMap[e.target];
    if (!s || !t) return;
    const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    line.setAttribute('x1', s.x); line.setAttribute('y1', s.y);
    line.setAttribute('x2', t.x); line.setAttribute('y2', t.y);
    line.setAttribute('stroke', '#475569'); line.setAttribute('stroke-width', '1.5');
    line.setAttribute('marker-end', 'url(#arrow)');
    svg.appendChild(line);
  });

  // Nodes
  STATE.nodes.forEach(n => {
    const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    g.style.cursor = 'pointer';
    g.onclick = () => showDetail(n.id);

    const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    circle.setAttribute('cx', n.x); circle.setAttribute('cy', n.y);
    circle.setAttribute('r', n.radius);
    circle.setAttribute('fill', COLORS[n.status] || '#64748b');
    circle.setAttribute('stroke', '#0f172a'); circle.setAttribute('stroke-width', '2');
    g.appendChild(circle);

    // Label
    const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    text.setAttribute('x', n.x); text.setAttribute('y', n.y + n.radius + 14);
    text.setAttribute('text-anchor', 'middle');
    text.setAttribute('font-size', '9'); text.setAttribute('fill', '#94a3b8');
    text.textContent = n.id.substring(0, 8) + '…';
    g.appendChild(text);

    svg.appendChild(g);
  });
}

async function showDetail(claimId) {
  try {
    const resp = await fetch(`/api/claims/${claimId}`);
    if (!resp.ok) return;
    const data = await resp.json();

    document.getElementById('modal-title').textContent = `Claim ${data.claim_id.substring(0, 12)}…`;

    const fields = [
      ['Claim ID', data.claim_id],
      ['Agent', data.agent_id],
      ['Assertion', data.assertion],
      ['Confidence', data.confidence.toFixed(2)],
      ['Method', data.method],
      ['Timestamp', new Date(data.timestamp * 1000).toISOString()],
      ['Evidence Refs', (data.evidence || []).map(e => e.substring(0, 12) + '…').join(', ') || 'None'],
      ['Metadata', JSON.stringify(data.metadata || {}, null, 2)],
      ['Signature', data.signature ? data.signature.substring(0, 32) + '…' : 'None'],
      ['Signature Valid', data.signature_valid !== undefined
        ? `<span class="${data.signature_valid ? 'sig-valid' : 'sig-invalid'}">${data.signature_valid ? '✓ Valid' : '✗ Invalid'}</span>`
        : 'Unknown'],
      ['Status', `<span class="status-${data.status}">${data.status}</span>`],
    ];

    if (data.revocation) {
      fields.push(['Revoked By', data.revocation.revoked_by]);
      fields.push(['Revoked At', new Date(data.revocation.revoked_at * 1000).toISOString()]);
      fields.push(['Reason', data.revocation.reason || '—']);
    }

    document.getElementById('modal-body').innerHTML = fields.map(([label, value]) =>
      `<div class="field"><label>${label}</label><div class="value">${value}</div></div>`
    ).join('');

    document.getElementById('modal-overlay').style.display = 'block';
  } catch (e) { console.error(e); }
}

function closeModal() { document.getElementById('modal-overlay').style.display = 'none'; }
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

init();
</script>
</body>
</html>"""
