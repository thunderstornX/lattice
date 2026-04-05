"""LATTICE CLI — lattice init/agents/claims/trace/audit/verify/stats/export."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from lattice import dag
from lattice.store import DB_FILENAME, LATTICE_DIR_NAME, LatticeStore, init_store

console = Console()


def _find_store(directory: str | None = None) -> LatticeStore:
    """Open .lattice/lattice.db in directory or cwd."""
    base = Path(directory) if directory else Path.cwd()
    db_path = base / LATTICE_DIR_NAME / DB_FILENAME
    if not db_path.exists():
        console.print(f"[red]No LATTICE store at {db_path}[/red]\nRun: lattice init <dir>")
        sys.exit(1)
    return LatticeStore(str(db_path))


def _short(full_id: str, n: int = 12) -> str:
    return full_id[:n]


@click.group()
@click.version_option(version="1.0.0", prog_name="lattice")
def cli() -> None:
    """LATTICE — Accountability layer for multi-agent AI systems."""


@cli.command()
@click.argument("directory", default=".")
def init(directory: str) -> None:
    """Initialize a new LATTICE investigation."""
    store = init_store(directory)
    store.close()
    console.print(f"[green]✓[/green] Initialized LATTICE at {Path(directory) / LATTICE_DIR_NAME}")


@cli.command()
@click.option("-d", "--directory", default=None)
def agents(directory: str | None) -> None:
    """List registered agents."""
    store = _find_store(directory)
    rows = store.list_agents()
    store.close()
    if not rows:
        console.print("[dim]No agents registered.[/dim]")
        return
    table = Table(title="Agents")
    table.add_column("ID", style="cyan")
    table.add_column("Role", style="green")
    table.add_column("Description")
    for a in rows:
        table.add_row(a["agent_id"], a["role"], a["description"])
    console.print(table)


@cli.command()
@click.option("-d", "--directory", default=None)
@click.option("--agent", default=None, help="Filter by agent ID.")
@click.option("--limit", default=50)
def claims(directory: str | None, agent: str | None, limit: int) -> None:
    """List claims."""
    store = _find_store(directory)
    rows = store.list_claims(agent_id=agent, limit=limit)
    store.close()
    if not rows:
        console.print("[dim]No claims.[/dim]")
        return
    table = Table(title=f"Claims ({len(rows)})")
    table.add_column("ID", style="cyan", max_width=12)
    table.add_column("Agent", style="green")
    table.add_column("Conf", justify="right")
    table.add_column("Method", style="yellow")
    table.add_column("Assertion", max_width=50)
    for c in rows:
        color = "green" if c.confidence >= 0.7 else "yellow" if c.confidence >= 0.3 else "red"
        table.add_row(_short(c.claim_id), c.agent_id, f"[{color}]{c.confidence:.2f}[/{color}]", c.method, c.assertion[:50])
    console.print(table)


@cli.command()
@click.argument("claim_id")
@click.option("-d", "--directory", default=None)
def trace(claim_id: str, directory: str | None) -> None:
    """Trace a claim backward through its evidence chain."""
    store = _find_store(directory)
    resolved = _resolve_id(store, claim_id)
    chain = dag.trace(store, resolved)
    store.close()
    console.print(f"\n[bold]Trace: [cyan]{_short(resolved)}[/cyan][/bold]\n")
    for i, c in enumerate(chain):
        indent = "  " * i
        color = "green" if c.confidence >= 0.7 else "yellow" if c.confidence >= 0.3 else "red"
        prefix = "●" if i == 0 else "└─"
        console.print(f"{indent}{prefix} [{color}]{c.confidence:.2f}[/{color}] [cyan]{_short(c.claim_id)}[/cyan] [dim]({c.agent_id}/{c.method})[/dim] {c.assertion[:70]}")


@cli.command()
@click.option("-d", "--directory", default=None)
@click.option("--threshold", default=0.3)
def audit(directory: str | None, threshold: float) -> None:
    """Audit for issues (unsupported claims, low confidence, broken refs)."""
    store = _find_store(directory)
    issues = dag.audit(store, confidence_threshold=threshold)
    store.close()
    if not issues:
        console.print("[green]✓ No issues found.[/green]")
        return
    table = Table(title=f"Issues ({len(issues)})")
    table.add_column("Claim", style="cyan", max_width=12)
    table.add_column("Type", style="red")
    table.add_column("Description")
    for i in issues:
        table.add_row(_short(i.claim_id), i.issue_type, i.description)
    console.print(table)


@cli.command()
@click.option("-d", "--directory", default=None)
def verify(directory: str | None) -> None:
    """Verify cryptographic signatures on all claims."""
    store = _find_store(directory)
    results = dag.verify_all(store)
    store.close()
    valid = sum(1 for r in results if r.valid)
    table = Table(title=f"Signatures ({valid}/{len(results)} valid)")
    table.add_column("Claim", style="cyan", max_width=12)
    table.add_column("Agent", style="green")
    table.add_column("Status")
    for r in results:
        s = "[green]✓[/green]" if r.valid else f"[red]✗ {r.error}[/red]"
        table.add_row(_short(r.claim_id), r.agent_id, s)
    console.print(table)


@cli.command()
@click.option("-d", "--directory", default=None)
def stats(directory: str | None) -> None:
    """Show investigation statistics."""
    store = _find_store(directory)
    s = dag.stats(store)
    store.close()
    console.print("\n[bold]Investigation Stats[/bold]\n")
    console.print(f"  Agents:     [cyan]{s['total_agents']}[/cyan]")
    console.print(f"  Claims:     [cyan]{s['total_claims']}[/cyan]")
    console.print(f"  Evidence:   [cyan]{s['total_evidence']}[/cyan]")
    if s['total_claims']:
        console.print(f"  Confidence: [green]{s['avg_confidence']:.2f}[/green] avg ({s['min_confidence']:.2f}–{s['max_confidence']:.2f})")
    if s.get("methods"):
        console.print("\n  [bold]Methods:[/bold]")
        for m, c in sorted(s["methods"].items(), key=lambda x: -x[1]):
            console.print(f"    {m}: {c}")


@cli.command()
@click.argument("output", default="investigation.json")
@click.option("-d", "--directory", default=None)
def export(output: str, directory: str | None) -> None:
    """Export investigation as JSON."""
    store = _find_store(directory)
    data = store.export_json()
    store.close()
    with open(output, "w") as f:
        json.dump(data, f, indent=2)
    console.print(f"[green]✓[/green] Exported to [bold]{output}[/bold]")


@cli.command()
@click.argument("claim_id")
@click.option("-d", "--directory", default=None)
@click.option("--agent", required=True, help="Agent ID performing the revocation.")
@click.option("--reason", default="", help="Reason for revocation.")
@click.option("--governance", is_flag=True, help="Override signer check (governance mode).")
def revoke(claim_id: str, directory: str | None, agent: str, reason: str, governance: bool) -> None:
    """Revoke a claim and flag downstream dependents as COMPROMISED."""
    store = _find_store(directory)
    resolved = _resolve_id(store, claim_id)
    try:
        result = store.revoke_claim(resolved, agent, reason, governance=governance)
    except Exception as exc:
        console.print(f"[red]✗ {exc}[/red]")
        store.close()
        sys.exit(1)

    console.print(f"\n[red]✗[/red] Revoked: [cyan]{_short(result.revoked_claim_id)}[/cyan]")
    if result.compromised_claim_ids:
        console.print(f"[yellow]⚠ {len(result.compromised_claim_ids)} downstream claims compromised:[/yellow]")
        for cid in result.compromised_claim_ids:
            console.print(f"  └─ [yellow]{_short(cid)}[/yellow]")
    else:
        console.print("[dim]No downstream claims affected.[/dim]")
    console.print(f"\n[bold]Total affected: {result.total_affected}[/bold]")
    store.close()


@cli.command()
@click.option("-d", "--directory", default=None)
def revocations(directory: str | None) -> None:
    """List all revocations."""
    store = _find_store(directory)
    revs = store.list_revocations()
    store.close()
    if not revs:
        console.print("[dim]No revocations.[/dim]")
        return
    table = Table(title=f"Revocations ({len(revs)})")
    table.add_column("Claim", style="cyan", max_width=12)
    table.add_column("Revoked By", style="red")
    table.add_column("Reason")
    for r in revs:
        table.add_row(_short(r.revoked_claim_id), r.revoked_by, r.reason or "—")
    console.print(table)


@cli.command(name="dashboard")
@click.option("-d", "--directory", default=None)
@click.option("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1).")
@click.option("--port", default=8420, type=int, help="Port (default: 8420).")
def dashboard_cmd(directory: str | None, host: str, port: int) -> None:
    """Launch the local observability dashboard."""
    import uvicorn

    from lattice.dashboard import create_app
    from lattice.store import DB_FILENAME, LATTICE_DIR_NAME

    base = Path(directory) if directory else Path.cwd()
    db_path = str(base / LATTICE_DIR_NAME / DB_FILENAME)
    if not Path(db_path).exists():
        console.print(f"[red]No LATTICE store at {db_path}[/red]\nRun: lattice init <dir>")
        sys.exit(1)

    console.print(f"[green]✓[/green] Dashboard at [bold]http://{host}:{port}[/bold]")
    console.print("[dim]Press Ctrl+C to stop.[/dim]\n")
    app = create_app(db_path)
    uvicorn.run(app, host=host, port=port, log_level="warning")


def _resolve_id(store: LatticeStore, partial: str) -> str:
    """Resolve partial claim ID."""
    all_claims = store.list_claims(limit=100_000)
    matches = [c for c in all_claims if c.claim_id.startswith(partial)]
    if len(matches) == 1:
        return matches[0].claim_id
    if len(matches) > 1:
        console.print(f"[yellow]Ambiguous: '{partial}' matches {len(matches)} claims[/yellow]")
        sys.exit(1)
    return partial
