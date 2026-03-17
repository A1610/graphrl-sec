"""
LANL Unified Host and Network Dataset Parser.

Dataset: Los Alamos National Laboratory Cyber Security Dataset
URL:     https://csr.lanl.gov/data/cyber1/
Size:    ~12GB compressed (58 days, includes red team events)

Phase 3 implementation — stub only for now.
Full implementation will cover:
  - auth.txt.gz: authentication events
  - proc.txt.gz: process events
  - flows.txt.gz: network flows
  - dns.txt.gz: DNS events
  - redteam.txt.gz: labeled red team (attack) events
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import structlog

from src.ingestion.parsers.base import BaseParser

logger = structlog.get_logger(__name__)


class LANLParser(BaseParser):
    """
    Parser for LANL Cyber Security Dataset.

    Phase 3 — not yet implemented.
    Raises NotImplementedError until Phase 3 implementation.
    """

    dataset_name = "LANL"
    supported_extensions = (".txt", ".gz", ".csv")

    def parse_file(
        self,
        filepath: Path,
        chunk_size: int = 50_000,
    ) -> Iterator[dict[str, Any]]:
        raise NotImplementedError(
            "LANL parser is scheduled for Phase 3 (Module 12). "
            "Use CICIDS2017 or UNSW-NB15 parsers for Phase 1 & 2."
        )

    def parse_directory(
        self,
        directory: Path,
        chunk_size: int = 50_000,
        glob_pattern: str = "*.txt",
    ) -> Iterator[dict[str, Any]]:
        raise NotImplementedError(
            "LANL parser is scheduled for Phase 3 (Module 12). "
            "Use CICIDS2017 or UNSW-NB15 parsers for Phase 1 & 2."
        )
