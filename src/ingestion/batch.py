"""
Batch ingestion — CSV files → List[UnifiedEvent], no Kafka dependency.

Used by:
  - Graph constructor (Module 1.2) during early development
  - Unit tests
  - Offline model training pipelines

For production streaming, use producer.py instead.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path

import structlog

from src.ingestion.config import IngestionConfig, settings
from src.ingestion.normalizer import EventNormalizer
from src.ingestion.parsers.cicids import CICIDSParser
from src.ingestion.parsers.unsw import UNSWParser
from src.ingestion.schemas import CollectorMode, DatasetSource, UnifiedEvent

logger = structlog.get_logger(__name__)

# Registry of available parsers keyed by DatasetSource
_PARSER_REGISTRY = {
    DatasetSource.CICIDS2017: CICIDSParser,
    DatasetSource.UNSW_NB15:  UNSWParser,
}


class BatchIngestionResult:
    """Result container returned by BatchIngestor after processing."""

    __slots__ = (
        "dataset",
        "source_path",
        "events",
        "total_parsed",
        "total_normalized",
        "total_skipped",
        "elapsed_seconds",
        "events_per_second",
    )

    def __init__(
        self,
        dataset: DatasetSource,
        source_path: Path,
        events: list[UnifiedEvent],
        total_parsed: int,
        total_normalized: int,
        total_skipped: int,
        elapsed_seconds: float,
    ) -> None:
        self.dataset = dataset
        self.source_path = source_path
        self.events = events
        self.total_parsed = total_parsed
        self.total_normalized = total_normalized
        self.total_skipped = total_skipped
        self.elapsed_seconds = elapsed_seconds
        self.events_per_second = (
            total_normalized / elapsed_seconds if elapsed_seconds > 0 else 0.0
        )

    def __repr__(self) -> str:
        return (
            f"BatchIngestionResult("
            f"dataset={self.dataset.value!r}, "
            f"normalized={self.total_normalized:,}, "
            f"skipped={self.total_skipped:,}, "
            f"rate={self.events_per_second:,.0f} ev/s)"
        )


class BatchIngestor:
    """
    Reads a dataset file or directory and returns normalized UnifiedEvents.

    No Kafka required — events are held in memory or streamed via iterator.
    Designed for datasets that fit in memory after normalization.

    For full CICIDS2017 (~7GB raw → ~500k events after dedup),
    use ingest_iter() to avoid loading everything into RAM at once.
    """

    def __init__(
        self,
        config: IngestionConfig | None = None,
        deduplicate: bool = True,
        drop_benign_ratio: float = 0.0,
    ) -> None:
        self._config = config or settings
        self._deduplicate = deduplicate
        self._drop_benign_ratio = drop_benign_ratio

    def ingest(
        self,
        dataset: DatasetSource,
        path: Path,
        chunk_size: int | None = None,
        max_events: int | None = None,
    ) -> BatchIngestionResult:
        """
        Ingest an entire dataset file or directory into memory.

        Args:
            dataset:    Which dataset to parse (CICIDS2017 or UNSW_NB15).
            path:       Path to file or directory.
            chunk_size: Rows per read chunk. Defaults to config value.
            max_events: Cap the number of normalized events returned.
                        Useful for development / smoke tests.

        Returns:
            BatchIngestionResult with events list and statistics.
        """
        parser_cls = _PARSER_REGISTRY.get(dataset)
        if parser_cls is None:
            raise ValueError(
                f"No parser registered for dataset {dataset.value!r}. "
                f"Available: {[d.value for d in _PARSER_REGISTRY]}"
            )

        effective_chunk = chunk_size or self._config.ingestion_chunk_size
        parser = parser_cls()
        normalizer = EventNormalizer(
            collector=CollectorMode.BATCH,
            deduplicate=self._deduplicate,
            drop_benign_ratio=self._drop_benign_ratio,
        )

        log = logger.bind(dataset=dataset.value, path=str(path))
        log.info("batch_ingest_start", chunk_size=effective_chunk)
        t0 = time.monotonic()

        if path.is_dir():
            raw_iter = parser.parse_directory(path, chunk_size=effective_chunk)
        else:
            raw_iter = parser.parse_file(path, chunk_size=effective_chunk)

        events: list[UnifiedEvent] = []
        for event in normalizer.normalize_batch(raw_iter):
            events.append(event)
            if max_events is not None and len(events) >= max_events:
                break

        elapsed = time.monotonic() - t0
        stats = normalizer.stats
        log.info(
            "batch_ingest_complete",
            normalized=stats["normalized"],
            skipped_validation=stats["skipped_validation"],
            skipped_duplicate=stats["skipped_duplicate"],
            elapsed_s=round(elapsed, 2),
        )
        return BatchIngestionResult(
            dataset=dataset,
            source_path=path,
            events=events,
            total_parsed=stats["total"],
            total_normalized=stats["normalized"],
            total_skipped=stats["skipped_validation"] + stats["skipped_duplicate"],
            elapsed_seconds=elapsed,
        )

    def ingest_iter(
        self,
        dataset: DatasetSource,
        path: Path,
        chunk_size: int | None = None,
    ) -> Iterator[UnifiedEvent]:
        """
        Stream normalized events from a dataset without loading all into RAM.

        Args:
            dataset:    Which dataset to parse.
            path:       Path to file or directory.
            chunk_size: Rows per read chunk.

        Yields:
            Validated UnifiedEvent objects.
        """
        parser_cls = _PARSER_REGISTRY.get(dataset)
        if parser_cls is None:
            raise ValueError(
                f"No parser registered for dataset {dataset.value!r}. "
                f"Available: {[d.value for d in _PARSER_REGISTRY]}"
            )

        effective_chunk = chunk_size or self._config.ingestion_chunk_size
        parser = parser_cls()
        normalizer = EventNormalizer(
            collector=CollectorMode.BATCH,
            deduplicate=self._deduplicate,
            drop_benign_ratio=self._drop_benign_ratio,
        )

        log = logger.bind(dataset=dataset.value, path=str(path))
        log.info("batch_ingest_start", chunk_size=effective_chunk)
        t0 = time.monotonic()

        if path.is_dir():
            raw_iter = parser.parse_directory(path, chunk_size=effective_chunk)
        else:
            raw_iter = parser.parse_file(path, chunk_size=effective_chunk)

        yield from normalizer.normalize_batch(raw_iter)

        elapsed = time.monotonic() - t0
        stats = normalizer.stats
        log.info(
            "batch_ingest_complete",
            normalized=stats["normalized"],
            skipped_validation=stats["skipped_validation"],
            skipped_duplicate=stats["skipped_duplicate"],
            elapsed_seconds=round(elapsed, 2),
            events_per_second=round(stats["normalized"] / elapsed, 0) if elapsed > 0 else 0,
        )


# ---------------------------------------------------------------------------
# Module-level convenience functions
# ---------------------------------------------------------------------------


def load_cicids(
    path: Path,
    max_events: int | None = None,
    deduplicate: bool = True,
) -> list[UnifiedEvent]:
    """
    Load CICIDS2017 dataset from file or directory into a list.

    Args:
        path:       File or directory containing CICIDS CSV files.
        max_events: Optional cap on number of events returned.
        deduplicate: Remove duplicate flows.

    Returns:
        List of UnifiedEvent objects.
    """
    ingestor = BatchIngestor(deduplicate=deduplicate)
    result = ingestor.ingest(DatasetSource.CICIDS2017, path, max_events=max_events)
    return result.events


def load_unsw(
    path: Path,
    max_events: int | None = None,
    deduplicate: bool = True,
) -> list[UnifiedEvent]:
    """
    Load UNSW-NB15 dataset from file or directory into a list.

    Args:
        path:       File or directory containing UNSW CSV files.
        max_events: Optional cap on number of events returned.
        deduplicate: Remove duplicate flows.

    Returns:
        List of UnifiedEvent objects.
    """
    ingestor = BatchIngestor(deduplicate=deduplicate)
    result = ingestor.ingest(DatasetSource.UNSW_NB15, path, max_events=max_events)
    return result.events


def stream_dataset(
    dataset: DatasetSource,
    path: Path,
    chunk_size: int = 50_000,
) -> Iterator[UnifiedEvent]:
    """
    Memory-efficient streaming iterator over a full dataset.

    Use this for large datasets (CICIDS2017 ~7GB) to avoid OOM.

    Example:
        for event in stream_dataset(DatasetSource.CICIDS2017, Path('data/raw/cicids')):
            graph_builder.add_event(event)
    """
    ingestor = BatchIngestor()
    yield from ingestor.ingest_iter(dataset, path, chunk_size=chunk_size)
