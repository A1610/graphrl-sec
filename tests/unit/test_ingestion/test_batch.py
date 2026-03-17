"""
Unit tests for src/ingestion/batch.py
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.ingestion.batch import BatchIngestor, load_cicids, load_unsw, stream_dataset
from src.ingestion.schemas import DatasetSource, UnifiedEvent

FIXTURE_CICIDS = Path("tests/fixtures/sample_cicids.csv")
FIXTURE_UNSW   = Path("tests/fixtures/sample_unsw.csv")


class TestBatchIngestor:

    @pytest.fixture()
    def ingestor(self) -> BatchIngestor:
        return BatchIngestor(deduplicate=True)

    # ------------------------------------------------------------------
    # CICIDS2017
    # ------------------------------------------------------------------

    def test_ingest_cicids_returns_result(self, ingestor: BatchIngestor) -> None:
        result = ingestor.ingest(DatasetSource.CICIDS2017, FIXTURE_CICIDS)
        assert result is not None
        assert len(result.events) > 0

    def test_ingest_cicids_events_are_unified(self, ingestor: BatchIngestor) -> None:
        result = ingestor.ingest(DatasetSource.CICIDS2017, FIXTURE_CICIDS)
        for event in result.events:
            assert isinstance(event, UnifiedEvent)

    def test_ingest_cicids_max_events_cap(self, ingestor: BatchIngestor) -> None:
        result = ingestor.ingest(DatasetSource.CICIDS2017, FIXTURE_CICIDS, max_events=3)
        assert len(result.events) == 3

    # ------------------------------------------------------------------
    # UNSW-NB15
    # ------------------------------------------------------------------

    def test_ingest_unsw_returns_result(self, ingestor: BatchIngestor) -> None:
        result = ingestor.ingest(DatasetSource.UNSW_NB15, FIXTURE_UNSW)
        assert len(result.events) > 0

    def test_ingest_unsw_events_have_timestamps(self, ingestor: BatchIngestor) -> None:
        result = ingestor.ingest(DatasetSource.UNSW_NB15, FIXTURE_UNSW)
        for event in result.events:
            assert event.timestamp is not None
            assert event.timestamp.tzinfo is not None

    # ------------------------------------------------------------------
    # Unsupported dataset
    # ------------------------------------------------------------------

    def test_unsupported_dataset_raises(self, ingestor: BatchIngestor) -> None:
        with pytest.raises(ValueError, match="No parser registered"):
            list(ingestor.ingest_iter(DatasetSource.LANL, FIXTURE_CICIDS))

    # ------------------------------------------------------------------
    # ingest_iter streaming
    # ------------------------------------------------------------------

    def test_ingest_iter_yields_events(self, ingestor: BatchIngestor) -> None:
        events = list(ingestor.ingest_iter(DatasetSource.CICIDS2017, FIXTURE_CICIDS))
        assert len(events) > 0

    def test_ingest_iter_all_events_valid(self, ingestor: BatchIngestor) -> None:
        for event in ingestor.ingest_iter(DatasetSource.CICIDS2017, FIXTURE_CICIDS):
            assert isinstance(event, UnifiedEvent)
            assert event.source.ip
            assert event.destination.ip

    def test_ingest_iter_no_invalid_ips(self, ingestor: BatchIngestor) -> None:
        for event in ingestor.ingest_iter(DatasetSource.CICIDS2017, FIXTURE_CICIDS):
            assert event.source.ip != "999.999.999.999"
            assert event.destination.ip != "999.999.999.999"

    # ------------------------------------------------------------------
    # Deduplication in batch
    # ------------------------------------------------------------------

    def test_dedup_reduces_count(self) -> None:
        dedup_ingestor    = BatchIngestor(deduplicate=True)
        no_dedup_ingestor = BatchIngestor(deduplicate=False)
        dedup_events    = list(dedup_ingestor.ingest_iter(DatasetSource.CICIDS2017, FIXTURE_CICIDS))
        no_dedup_events = list(no_dedup_ingestor.ingest_iter(DatasetSource.CICIDS2017, FIXTURE_CICIDS))
        # With dedup, count should be <= without dedup
        assert len(dedup_events) <= len(no_dedup_events)


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------


class TestConvenienceFunctions:
    def test_load_cicids_returns_list(self) -> None:
        events = load_cicids(FIXTURE_CICIDS)
        assert isinstance(events, list)
        assert len(events) > 0

    def test_load_cicids_max_events(self) -> None:
        events = load_cicids(FIXTURE_CICIDS, max_events=2)
        assert len(events) == 2

    def test_load_unsw_returns_list(self) -> None:
        events = load_unsw(FIXTURE_UNSW)
        assert isinstance(events, list)
        assert len(events) > 0

    def test_stream_dataset_cicids(self) -> None:
        events = list(stream_dataset(DatasetSource.CICIDS2017, FIXTURE_CICIDS))
        assert len(events) > 0

    def test_stream_dataset_unsw(self) -> None:
        events = list(stream_dataset(DatasetSource.UNSW_NB15, FIXTURE_UNSW))
        assert len(events) > 0

    def test_stream_dataset_all_unified_events(self) -> None:
        for event in stream_dataset(DatasetSource.CICIDS2017, FIXTURE_CICIDS):
            assert isinstance(event, UnifiedEvent)
