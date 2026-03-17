"""
GraphRL-Sec Kafka Topic Setup Script.

Creates all required Kafka topics with production-grade configurations.
Safe to re-run — topics that already exist are skipped.

Usage:
    python scripts/setup_kafka.py             # create all topics
    python scripts/setup_kafka.py --list      # list existing topics
    python scripts/setup_kafka.py --delete    # delete all GraphRL topics (dev only)
    python scripts/setup_kafka.py --brokers localhost:9092
"""

from __future__ import annotations

import sys

import click
import structlog
from rich.console import Console
from rich.table import Table

from src.ingestion.config import settings
from src.ingestion.topics import TOPIC_SPECS, KafkaTopicManager

console = Console()
log = structlog.get_logger(__name__)


@click.group(invoke_without_command=True)
@click.option(
    "--brokers", "-b",
    default=None,
    help="Kafka bootstrap servers (default from .env / KAFKA_BOOTSTRAP_SERVERS).",
)
@click.pass_context
def cli(ctx: click.Context, brokers: str | None) -> None:
    """GraphRL-Sec Kafka topic management."""
    ctx.ensure_object(dict)
    ctx.obj["brokers"] = brokers or settings.kafka_bootstrap_servers
    if ctx.invoked_subcommand is None:
        # Default: create all topics
        ctx.invoke(create)


@cli.command()
@click.pass_context
def create(ctx: click.Context) -> None:
    """Create all required Kafka topics (idempotent)."""
    brokers: str = ctx.obj["brokers"]
    _override_brokers(brokers)

    console.rule("[bold cyan]GraphRL-Sec — Kafka Topic Setup")
    console.print(f"  [bold]Brokers:[/bold]  {brokers}")
    console.print(f"  [bold]Topics:[/bold]   {len(TOPIC_SPECS)} required\n")

    mgr = KafkaTopicManager()

    if not mgr.ping():
        console.print(f"[bold red]✗ Cannot reach Kafka brokers at {brokers}[/bold red]")
        console.print("  Make sure Docker is running: [bold]make start[/bold]")
        sys.exit(1)

    result = mgr.ensure_topics()

    table = Table(title="Topic Setup Result", show_header=True)
    table.add_column("Topic", style="cyan")
    table.add_column("Status", style="bold")

    for name in result.created:
        table.add_row(name, "[green]✓ Created[/green]")
    for name in result.already_exist:
        table.add_row(name, "[yellow]⚡ Already exists[/yellow]")
    for name in result.failed:
        table.add_row(name, "[red]✗ Failed[/red]")

    console.print(table)

    if result.failed:
        console.print(f"\n[bold red]✗ {len(result.failed)} topic(s) failed to create.[/bold red]")
        sys.exit(1)
    else:
        console.print(
            f"\n[bold green]✓ All {len(TOPIC_SPECS)} topics ready.[/bold green]"
        )


@cli.command(name="list")
@click.pass_context
def list_topics(ctx: click.Context) -> None:
    """List all existing Kafka topics."""
    brokers: str = ctx.obj["brokers"]
    _override_brokers(brokers)

    mgr = KafkaTopicManager()

    if not mgr.ping():
        console.print(f"[bold red]✗ Cannot reach Kafka at {brokers}[/bold red]")
        sys.exit(1)

    topics = mgr.list_topics()
    if not topics:
        console.print("[yellow]No topics found.[/yellow]")
        return

    table = Table(title=f"Kafka Topics ({len(topics)})", show_header=True)
    table.add_column("Topic",        style="cyan")
    table.add_column("Partitions",   justify="right")
    table.add_column("Replication",  justify="right")
    table.add_column("GraphRL?",     justify="center")

    graphrl_names = {s.name for s in TOPIC_SPECS}
    for t in topics:
        is_graphrl = "✓" if t.name in graphrl_names else "—"
        table.add_row(t.name, str(t.num_partitions), str(t.replication_factor), is_graphrl)

    console.print(table)


@cli.command()
@click.option("--yes", is_flag=True, help="Skip confirmation prompt.")
@click.pass_context
def delete(ctx: click.Context, yes: bool) -> None:
    """
    Delete all GraphRL-Sec topics.

    WARNING: Irreversible — all data in these topics will be lost.
    Only use during development / test teardown.
    """
    brokers: str = ctx.obj["brokers"]
    _override_brokers(brokers)

    names = [s.name for s in TOPIC_SPECS]

    if not yes:
        console.print(f"[bold red]WARNING:[/bold red] This will delete {len(names)} topics:")
        for n in names:
            console.print(f"  - {n}")
        if not click.confirm("\nContinue?"):
            console.print("[yellow]Aborted.[/yellow]")
            return

    mgr = KafkaTopicManager()
    results = mgr.delete_topics(names)

    for name, ok in results.items():
        status = "[green]✓ Deleted[/green]" if ok else "[red]✗ Failed[/red]"
        console.print(f"  {name}: {status}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _override_brokers(brokers: str) -> None:
    """Temporarily override the bootstrap servers in the config singleton."""
    settings.kafka_bootstrap_servers = brokers  # type: ignore[misc]


if __name__ == "__main__":
    cli(obj={})
