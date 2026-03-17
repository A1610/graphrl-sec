"""
GraphRL-Sec Data Ingestion CLI.

Usage:
    python -m src.ingestion.cli ingest --dataset cicids --path data/raw/cicids/ --rate 1000
    python -m src.ingestion.cli ingest --dataset unsw   --path data/raw/unsw/   --rate 500
    python -m src.ingestion.cli verify --dataset cicids --path data/raw/cicids/
    python -m src.ingestion.cli stats  --dataset cicids --path data/raw/cicids/
"""

from __future__ import annotations

import io
import sys
import time
from pathlib import Path

# Windows cp1252 terminals cannot encode UTF-8 characters emitted by
# structlog / rich.  Force UTF-8 output so the pipeline never crashes on
# non-ASCII log messages (e.g. Unicode arrows in progress spinners).
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import click
import structlog
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table

from src.ingestion.config import settings
from src.ingestion.consumer import ConsumerConfig, GraphConsumer
from src.ingestion.normalizer import EventNormalizer
from src.ingestion.parsers.cicids import CICIDSParser
from src.ingestion.parsers.unsw import UNSWParser
from src.ingestion.producer import EventProducer
from src.ingestion.schemas import CollectorMode, DatasetSource

console = Console()
log = structlog.get_logger(__name__)

# Dataset name -> (DatasetSource enum, parser class)
_DATASET_MAP = {
    "cicids":  (DatasetSource.CICIDS2017, CICIDSParser),
    "unsw":    (DatasetSource.UNSW_NB15,  UNSWParser),
}


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------


@click.group()
@click.option("--log-level", default="INFO", type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]))
def cli(log_level: str) -> None:
    """GraphRL-Sec Data Ingestion Pipeline."""
    import logging

    import structlog

    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level)
        ),
    )


# ---------------------------------------------------------------------------
# ingest command — parse + normalize + publish to Kafka
# ---------------------------------------------------------------------------


@cli.command()
@click.option(
    "--dataset", "-d",
    required=True,
    type=click.Choice(["cicids", "unsw"]),
    help="Dataset to ingest.",
)
@click.option(
    "--path", "-p",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to dataset file or directory.",
)
@click.option(
    "--rate", "-r",
    default=1000,
    show_default=True,
    type=click.IntRange(1, 100_000),
    help="Maximum events per second published to Kafka.",
)
@click.option(
    "--chunk-size",
    default=50_000,
    show_default=True,
    type=click.IntRange(1_000, 1_000_000),
    help="Rows read per chunk from CSV.",
)
@click.option(
    "--topic",
    default=None,
    help="Kafka topic override (default from config).",
)
@click.option(
    "--no-dedup",
    is_flag=True,
    default=False,
    help="Disable deduplication (faster but may produce duplicates).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Parse and normalize only — do not publish to Kafka.",
)
def ingest(
    dataset: str,
    path: Path,
    rate: int,
    chunk_size: int,
    topic: str | None,
    no_dedup: bool,
    dry_run: bool,
) -> None:
    """Parse a dataset and publish normalized events to Kafka."""
    ds, parser_cls = _DATASET_MAP[dataset]
    parser = parser_cls()
    normalizer = EventNormalizer(
        collector=CollectorMode.BATCH,
        deduplicate=not no_dedup,
    )

    console.rule(f"[bold cyan]GraphRL-Sec Ingestion — {ds.value}")
    console.print(f"  [bold]Path:[/bold]      {path}")
    console.print(f"  [bold]Rate:[/bold]      {rate:,} events/s")
    console.print(f"  [bold]Chunk:[/bold]     {chunk_size:,} rows")
    console.print(f"  [bold]Dedup:[/bold]     {not no_dedup}")
    console.print(f"  [bold]Dry run:[/bold]   {dry_run}")
    console.print()

    t0 = time.monotonic()

    # Build raw row iterator
    if path.is_dir():
        raw_iter = parser.parse_directory(path, chunk_size=chunk_size)
    else:
        raw_iter = parser.parse_file(path, chunk_size=chunk_size)

    normalized_iter = normalizer.normalize_batch(raw_iter)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
        refresh_per_second=4,
    ) as progress:
        task = progress.add_task(f"[cyan]Ingesting {ds.value}...", total=None)
        count = 0

        if dry_run:
            for count, _event in enumerate(normalized_iter, 1):
                progress.update(task, advance=1, description=f"[cyan]{count:,} events normalized")
        else:
            with EventProducer(
                topic=topic or settings.kafka_topic_normalized_events,
                rate_limit=rate,
            ) as producer:
                for event in normalized_iter:
                    producer.publish(event)
                    count += 1
                    progress.update(task, advance=1, description=f"[cyan]{count:,} events published")

                progress.update(task, description="[yellow]Flushing Kafka buffer...")
                remaining = producer.flush(timeout=60.0)
                if remaining > 0:
                    console.print(f"[red]WARNING: {remaining} messages not delivered!")

        progress.update(task, description="[green]Done!")

    elapsed = time.monotonic() - t0
    _print_summary(normalizer.stats, count, elapsed, dry_run)


# ---------------------------------------------------------------------------
# verify command — validate dataset files without publishing
# ---------------------------------------------------------------------------


@cli.command()
@click.option("--dataset", "-d", required=True, type=click.Choice(["cicids", "unsw"]))
@click.option("--path", "-p", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--sample", default=1000, show_default=True, help="Rows to sample for verification.")
def verify(dataset: str, path: Path, sample: int) -> None:
    """Verify dataset files are readable and parseable (sample check)."""
    ds, parser_cls = _DATASET_MAP[dataset]
    parser = parser_cls()
    normalizer = EventNormalizer(deduplicate=False)

    console.rule(f"[bold yellow]Verifying {ds.value}")

    if path.is_dir():
        raw_iter = parser.parse_directory(path, chunk_size=sample)
    else:
        raw_iter = parser.parse_file(path, chunk_size=sample)

    events = []
    for i, row in enumerate(raw_iter):
        event = normalizer.normalize(row)
        if event:
            events.append(event)
        if i >= sample - 1:
            break

    stats = normalizer.stats
    table = Table(title=f"{ds.value} — Sample Verification ({sample} rows)", show_header=True)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Rows sampled",          str(stats["total"]))
    table.add_row("Events normalized",     str(stats["normalized"]))
    table.add_row("Skipped (validation)",  str(stats["skipped_validation"]))
    table.add_row("Skipped (duplicate)",   str(stats["skipped_duplicate"]))
    table.add_row("Normalization rate",    f"{stats['normalized'] / max(stats['total'], 1) * 100:.1f}%")

    if events:
        sample_event = events[0]
        table.add_row("Sample src_ip",  sample_event.source.ip)
        table.add_row("Sample dst_ip",  sample_event.destination.ip)
        table.add_row("Sample label",   sample_event.metadata.attack_label.value)
        table.add_row("Sample ts",      sample_event.timestamp.isoformat())

    console.print(table)

    ok = stats["normalized"] > 0
    if ok:
        console.print("[bold green]✓ Dataset verified successfully.[/bold green]")
    else:
        console.print("[bold red]✗ No events could be normalized. Check dataset format.[/bold red]")
        sys.exit(1)


# ---------------------------------------------------------------------------
# stats command — count rows and attack distribution
# ---------------------------------------------------------------------------


@cli.command()
@click.option("--dataset", "-d", required=True, type=click.Choice(["cicids", "unsw"]))
@click.option("--path", "-p", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--chunk-size", default=50_000, show_default=True)
def stats(dataset: str, path: Path, chunk_size: int) -> None:
    """Scan full dataset and print attack label distribution."""
    ds, parser_cls = _DATASET_MAP[dataset]
    parser = parser_cls()
    normalizer = EventNormalizer(deduplicate=False)

    console.rule(f"[bold magenta]Dataset Stats — {ds.value}")

    label_counts: dict[str, int] = {}
    total = 0

    if path.is_dir():
        raw_iter = parser.parse_directory(path, chunk_size=chunk_size)
    else:
        raw_iter = parser.parse_file(path, chunk_size=chunk_size)

    with Progress(SpinnerColumn(), TextColumn("{task.description}"), TimeElapsedColumn(), console=console) as p:
        t = p.add_task("[magenta]Scanning...", total=None)
        for event in normalizer.normalize_batch(raw_iter):
            label = event.metadata.attack_label.value
            label_counts[label] = label_counts.get(label, 0) + 1
            total += 1
            if total % 100_000 == 0:
                p.update(t, description=f"[magenta]{total:,} events scanned...")

    table = Table(title=f"{ds.value} — Label Distribution ({total:,} events)", show_header=True)
    table.add_column("Label", style="cyan")
    table.add_column("Count", style="white", justify="right")
    table.add_column("Percentage", style="green", justify="right")

    for label, count in sorted(label_counts.items(), key=lambda x: -x[1]):
        table.add_row(label, f"{count:,}", f"{count / total * 100:.2f}%")

    console.print(table)
    console.print(f"\n[bold]Total events:[/bold] {total:,}")
    console.print(f"[bold]Attack events:[/bold] {total - label_counts.get('BENIGN', 0):,}")


# ---------------------------------------------------------------------------
# consume command — run Kafka consumer, build graphs, save .pt snapshots
# ---------------------------------------------------------------------------


@cli.command()
@click.option(
    "--snapshot-dir", "-s",
    default="data/graphs",
    show_default=True,
    type=click.Path(path_type=Path),
    help="Directory to save PyG .pt snapshot files for pre-training.",
)
@click.option(
    "--write-neo4j/--no-neo4j",
    default=True,
    show_default=True,
    help="Write graph windows to Neo4j (default: on).",
)
@click.option(
    "--min-events",
    default=5,
    show_default=True,
    type=click.IntRange(1, 100_000),
    help="Minimum events per window to save a snapshot (skip near-empty windows).",
)
@click.option(
    "--topic",
    default=None,
    help="Kafka topic override (default from config).",
)
@click.option(
    "--group-id",
    default="graph-constructor-group",
    show_default=True,
    help="Kafka consumer group ID.",
)
@click.option(
    "--servers",
    default="localhost:9092",
    show_default=True,
    help="Kafka bootstrap servers.",
)
def consume(
    snapshot_dir: Path,
    write_neo4j: bool,
    min_events: int,
    topic: str | None,
    group_id: str,
    servers: str,
) -> None:
    """
    Start Kafka graph consumer.

    Consumes normalized events from Kafka, builds temporal graph windows,
    saves PyG HeteroData .pt snapshots (for pre-training), and optionally
    writes to Neo4j.

    Run AFTER: python -m src.ingestion.cli ingest --dataset ...
    """
    cfg = ConsumerConfig(
        bootstrap_servers=servers,
        topic=topic or settings.kafka_topic_normalized_events,
        group_id=group_id,
        write_neo4j=write_neo4j,
        snapshot_dir=snapshot_dir,
        min_snapshot_events=min_events,
    )

    console.rule("[bold cyan]GraphRL-Sec Graph Consumer")
    console.print(f"  [bold]Topic:[/bold]        {cfg.topic}")
    console.print(f"  [bold]Servers:[/bold]      {cfg.bootstrap_servers}")
    console.print(f"  [bold]Snapshot dir:[/bold] {snapshot_dir}")
    console.print(f"  [bold]Write Neo4j:[/bold]  {write_neo4j}")
    console.print(f"  [bold]Min events:[/bold]   {min_events}")
    console.print()
    console.print("[yellow]Press Ctrl+C to stop gracefully.[/yellow]")
    console.print()

    with GraphConsumer(config=cfg) as consumer:
        metrics = consumer.run()

    m = metrics.snapshot()
    table = Table(title="Consumer Summary", show_header=True)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="bold green")
    table.add_row("Messages consumed",   f"{m['messages_consumed']:,}")
    table.add_row("Windows constructed", f"{m['windows_constructed']:,}")
    table.add_row("Neo4j writes",        f"{m['neo4j_writes']:,}")
    table.add_row("Processing errors",   str(m["processing_errors"]))
    table.add_row("Events / second",     f"{m['events_per_second']:,.0f}")
    table.add_row("Elapsed",             f"{m['elapsed_s']:.1f}s")
    console.print(table)

    snapshots = list(snapshot_dir.glob("window_*.pt")) if snapshot_dir.exists() else []
    console.print(f"\n[bold green]Snapshots saved:[/bold green] {len(snapshots):,} files → {snapshot_dir}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _print_summary(
    stats: dict[str, int],
    count: int,
    elapsed: float,
    dry_run: bool,
) -> None:
    rate = count / elapsed if elapsed > 0 else 0
    table = Table(title="Ingestion Summary", show_header=True)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="bold green")
    table.add_row("Events normalized",    f"{stats['normalized']:,}")
    table.add_row("Events published",     f"{count:,}" if not dry_run else "N/A (dry run)")
    table.add_row("Skipped (validation)", f"{stats['skipped_validation']:,}")
    table.add_row("Skipped (duplicate)",  f"{stats['skipped_duplicate']:,}")
    table.add_row("Elapsed",              f"{elapsed:.1f}s")
    table.add_row("Rate",                 f"{rate:,.0f} events/s")
    console.print(table)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    cli()
