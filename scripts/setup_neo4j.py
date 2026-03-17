"""
GraphRL-Sec Neo4j Schema Setup Script.

Creates all required constraints and indexes in Neo4j.
Safe to re-run — all DDL uses IF NOT EXISTS.

Usage:
    python scripts/setup_neo4j.py             # setup schema (constraints + indexes)
    python scripts/setup_neo4j.py --list      # list existing constraints/indexes
    python scripts/setup_neo4j.py --drop      # drop all GraphRL schema (dev only)
    python scripts/setup_neo4j.py --ping      # check Neo4j connectivity
"""

from __future__ import annotations

import sys

import click
import structlog
from rich.console import Console
from rich.table import Table

from src.graph.config import graph_settings
from src.graph.neo4j_schema import _CONSTRAINTS, _NODE_INDEXES, _REL_INDEXES, SchemaManager

console = Console()
log = structlog.get_logger(__name__)


@click.group(invoke_without_command=True)
@click.option("--uri",      default=None, help="Neo4j bolt URI (default from .env).")
@click.option("--user",     default=None, help="Neo4j username (default from .env).")
@click.option("--password", default=None, help="Neo4j password (default from .env).")
@click.pass_context
def cli(ctx: click.Context, uri: str | None, user: str | None, password: str | None) -> None:
    """GraphRL-Sec Neo4j schema management."""
    ctx.ensure_object(dict)
    ctx.obj["uri"]      = uri      or graph_settings.neo4j_uri
    ctx.obj["user"]     = user     or graph_settings.neo4j_user
    ctx.obj["password"] = password or graph_settings.neo4j_password
    if ctx.invoked_subcommand is None:
        ctx.invoke(setup)


@cli.command()
@click.pass_context
def setup(ctx: click.Context) -> None:
    """Create all constraints and indexes (idempotent)."""
    uri: str      = ctx.obj["uri"]
    user: str     = ctx.obj["user"]
    password: str = ctx.obj["password"]

    console.rule("[bold cyan]GraphRL-Sec — Neo4j Schema Setup")
    console.print(f"  [bold]URI:[/bold]         {uri}")
    console.print(f"  [bold]User:[/bold]        {user}")
    console.print(f"  [bold]Constraints:[/bold] {len(_CONSTRAINTS)}")
    console.print(f"  [bold]Indexes:[/bold]     {len(_NODE_INDEXES) + len(_REL_INDEXES)}\n")

    mgr = _build_manager(uri, user, password)
    with mgr:
        if not mgr.ping():
            console.print(f"[bold red]✗ Cannot reach Neo4j at {uri}[/bold red]")
            console.print("  Make sure Docker is running: [bold]make start[/bold]")
            sys.exit(1)

        status = mgr.setup()

    table = Table(title="Schema Setup Result", show_header=True)
    table.add_column("Category",  style="cyan")
    table.add_column("Applied",   justify="right", style="green")

    table.add_row("Constraints",       str(status.constraints_applied))
    table.add_row("Node indexes",      str(status.node_indexes_applied))
    table.add_row("Relationship indexes", str(status.rel_indexes_applied))
    table.add_row("Total",             str(status.total_applied))

    console.print(table)

    if status.errors > 0:
        console.print(f"\n[bold yellow]⚠ {status.errors} DDL error(s) — check logs.[/bold yellow]")
    else:
        console.print(
            f"\n[bold green]✓ Schema ready — {status.total_applied} DDL statements applied.[/bold green]"
        )


@cli.command()
@click.pass_context
def ping(ctx: click.Context) -> None:
    """Check Neo4j connectivity."""
    uri: str = ctx.obj["uri"]
    mgr = _build_manager(uri, ctx.obj["user"], ctx.obj["password"])
    with mgr:
        reachable = mgr.ping()

    if reachable:
        console.print(f"[bold green]✓ Neo4j reachable at {uri}[/bold green]")
    else:
        console.print(f"[bold red]✗ Neo4j unreachable at {uri}[/bold red]")
        sys.exit(1)


@cli.command(name="list")
@click.pass_context
def list_schema(ctx: click.Context) -> None:
    """List existing constraints and indexes in Neo4j."""
    mgr = _build_manager(ctx.obj["uri"], ctx.obj["user"], ctx.obj["password"])
    with mgr:
        if not mgr.ping():
            console.print("[bold red]✗ Cannot reach Neo4j.[/bold red]")
            sys.exit(1)

        constraints = mgr.list_constraints()
        indexes     = mgr.list_indexes()

    # Constraints table
    c_table = Table(title=f"Constraints ({len(constraints)})", show_header=True)
    c_table.add_column("Name",      style="cyan")
    c_table.add_column("Type",      style="white")
    c_table.add_column("Entity",    style="green")
    for c in constraints:
        c_table.add_row(
            str(c.get("name", "?")),
            str(c.get("type", "?")),
            str(c.get("labelsOrTypes", ["?"])[0] if c.get("labelsOrTypes") else "?"),
        )
    console.print(c_table)

    # Indexes table (exclude constraint-backing indexes)
    visible = [ix for ix in indexes if ix.get("type") != "LOOKUP"]
    i_table = Table(title=f"Indexes ({len(visible)})", show_header=True)
    i_table.add_column("Name",   style="cyan")
    i_table.add_column("State",  style="white")
    i_table.add_column("Label",  style="green")
    i_table.add_column("Property", style="yellow")
    for ix in visible:
        i_table.add_row(
            str(ix.get("name", "?")),
            str(ix.get("state", "?")),
            str(ix.get("labelsOrTypes", ["?"])[0] if ix.get("labelsOrTypes") else "?"),
            str(ix.get("properties", ["?"])[0] if ix.get("properties") else "?"),
        )
    console.print(i_table)


@cli.command()
@click.option("--yes", is_flag=True, help="Skip confirmation prompt.")
@click.pass_context
def drop(ctx: click.Context, yes: bool) -> None:
    """
    Drop all GraphRL-Sec constraints and indexes.

    WARNING: Irreversible. Only use during development / test teardown.
    """
    total = len(_CONSTRAINTS) + len(_NODE_INDEXES) + len(_REL_INDEXES)
    if not yes:
        console.print(f"[bold red]WARNING:[/bold red] This will drop {total} constraints/indexes.")
        if not click.confirm("Continue?"):
            console.print("[yellow]Aborted.[/yellow]")
            return

    mgr = _build_manager(ctx.obj["uri"], ctx.obj["user"], ctx.obj["password"])
    with mgr:
        mgr.drop_all()

    console.print(f"[green]✓ Dropped {total} schema objects.[/green]")


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _build_manager(uri: str, user: str, password: str) -> SchemaManager:
    """Build a SchemaManager with explicit credentials."""
    from src.graph.config import GraphConfig
    cfg = GraphConfig(
        neo4j_uri=uri,
        neo4j_user=user,
        neo4j_password=password,
    )
    return SchemaManager(config=cfg)


if __name__ == "__main__":
    cli(obj={})
