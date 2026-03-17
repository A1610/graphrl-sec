"""
Neo4j Import — replays Kafka events into Neo4j graph database.

Reads all normalized events from the Kafka topic and writes every graph
window to Neo4j using batched MERGE operations.  Does NOT regenerate
.pt snapshot files (those already exist in data/graphs/).

Usage:
    python scripts/neo4j_import.py
    python scripts/neo4j_import.py --servers localhost:9092 --topic normalized-events
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# ── project root on path ────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent))

import structlog
from rich.console import Console
from rich.live import Live
from rich.table import Table

from src.graph.neo4j_writer import Neo4jWriter
from src.graph.pyg_converter import ConversionStats
from src.graph.temporal import WindowResult
from src.ingestion.consumer import ConsumerConfig, GraphConsumer

console = Console()
log     = structlog.get_logger(__name__)


def _make_stats_table(
    windows: int,
    nodes_total: int,
    edges_total: int,
    errors: int,
    elapsed: float,
    lag: int,
) -> Table:
    table = Table(title="Neo4j Import — Live Progress", show_header=True)
    table.add_column("Metric",  style="cyan")
    table.add_column("Value",   style="bold green")
    table.add_row("Windows written",  f"{windows:,}")
    table.add_row("Nodes merged",     f"{nodes_total:,}")
    table.add_row("Edges merged",     f"{edges_total:,}")
    table.add_row("Errors",           str(errors))
    table.add_row("Elapsed",          f"{elapsed:.0f}s")
    table.add_row("Kafka lag",        f"{lag:,}" if lag >= 0 else "—")
    return table


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Kafka events into Neo4j.")
    parser.add_argument("--servers",    default="localhost:9092",   help="Kafka bootstrap servers.")
    parser.add_argument("--topic",      default="normalized-events", help="Kafka topic.")
    parser.add_argument("--group-id",   default="neo4j-import-v1",  help="Consumer group ID.")
    parser.add_argument("--min-events", type=int, default=5,         help="Min events per window.")
    args = parser.parse_args()

    console.rule("[bold cyan]GraphRL-Sec — Neo4j Import")
    console.print(f"  [bold]Servers:[/bold]   {args.servers}")
    console.print(f"  [bold]Topic:[/bold]     {args.topic}")
    console.print(f"  [bold]Group ID:[/bold]  {args.group_id}")
    console.print()

    # Verify Neo4j is up
    writer = Neo4jWriter()
    if not writer.ping():
        console.print("[bold red]ERROR:[/bold red] Neo4j unreachable. Is Docker running?")
        sys.exit(1)
    writer.ensure_constraints()
    console.print("[green]Neo4j connected.[/green]\n")
    console.print("[yellow]Press Ctrl+C to stop gracefully.[/yellow]\n")

    # Counters for live display
    windows_written = 0
    nodes_total     = 0
    edges_total     = 0
    t0              = time.monotonic()

    def on_window(result: WindowResult, stats: ConversionStats) -> None:
        nonlocal windows_written, nodes_total, edges_total
        try:
            writer.write_window(result)
            windows_written += 1
            nodes_total     += stats.num_nodes
            edges_total     += stats.num_edges
        except Exception as exc:  # noqa: BLE001
            log.error("neo4j_write_error", window_id=result.window.window_id, error=str(exc))

    cfg = ConsumerConfig(
        bootstrap_servers = args.servers,
        topic             = args.topic,
        group_id          = args.group_id,
        write_neo4j       = False,   # we handle Neo4j via on_window callback
        snapshot_dir      = None,    # don't regenerate .pt files
        min_snapshot_events = args.min_events,
    )

    with Live(console=console, refresh_per_second=1) as live:
        consumer = GraphConsumer(config=cfg, on_window_ready=on_window)

        import threading
        stop = threading.Event()

        def _refresh() -> None:
            while not stop.wait(1.0):
                elapsed = time.monotonic() - t0
                live.update(_make_stats_table(
                    windows_written, nodes_total, edges_total,
                    consumer.metrics.processing_errors,
                    elapsed, -1,
                ))

        t = threading.Thread(target=_refresh, daemon=True)
        t.start()

        try:
            consumer.run()
        finally:
            stop.set()
            writer.close()

    elapsed = time.monotonic() - t0
    console.print()
    console.rule("[bold green]Import Complete")
    console.print(f"  Windows written : {windows_written:,}")
    console.print(f"  Nodes merged    : {nodes_total:,}")
    console.print(f"  Edges merged    : {edges_total:,}")
    console.print(f"  Elapsed         : {elapsed:.0f}s  ({elapsed/60:.1f} min)")


if __name__ == "__main__":
    main()
