"""
Abstract base class for all dataset parsers.

Every parser (CICIDS, UNSW-NB15, LANL) must implement this interface.
This ensures all parsers are interchangeable in the pipeline.
"""

from __future__ import annotations

import abc
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    pass

logger = structlog.get_logger(__name__)


class BaseParser(abc.ABC):
    """
    Abstract base for all dataset parsers.

    Parsers are responsible for:
    - Reading raw dataset files (CSV, TSV, JSON, etc.)
    - Yielding raw row dicts that the normalizer can process
    - Handling file-level errors (missing files, encoding issues)

    Parsers do NOT normalize — that is the normalizer's job.
    Parsers do NOT validate IPs or timestamps — that is the schema's job.
    """

    # Each subclass must declare what dataset it handles
    dataset_name: str
    # Expected file extension(s) this parser can read
    supported_extensions: tuple[str, ...] = (".csv",)

    @abc.abstractmethod
    def parse_file(
        self,
        filepath: Path,
        chunk_size: int = 50_000,
    ) -> Iterator[dict[str, object]]:
        """
        Yield raw row dicts from a dataset file.

        Args:
            filepath:   Path to the dataset file.
            chunk_size: Number of rows to read at once (memory control).

        Yields:
            Raw row as a dict with string keys and untyped values.
            The normalizer will clean and type-cast these values.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError:        If the file format is unrecognized.
        """
        ...

    @abc.abstractmethod
    def parse_directory(
        self,
        directory: Path,
        chunk_size: int = 50_000,
        glob_pattern: str = "*.csv",
    ) -> Iterator[dict[str, object]]:
        """
        Yield raw row dicts from ALL matching files in a directory.

        This is the primary entry point for full-dataset ingestion.
        Files are processed in sorted order for reproducibility.

        Args:
            directory:    Path to directory containing dataset files.
            chunk_size:   Rows per chunk.
            glob_pattern: File glob pattern within the directory.

        Yields:
            Raw row dicts (same as parse_file).
        """
        ...

    def validate_file(self, filepath: Path) -> None:
        """
        Validate that a file exists and has a supported extension.

        Raises:
            FileNotFoundError: If file does not exist.
            ValueError:        If extension is not supported.
        """
        if not filepath.exists():
            raise FileNotFoundError(f"Dataset file not found: {filepath}")
        if not filepath.is_file():
            raise ValueError(f"Path is not a file: {filepath}")
        if filepath.suffix.lower() not in self.supported_extensions:
            raise ValueError(
                f"Unsupported file extension {filepath.suffix!r} for "
                f"{self.dataset_name}. Expected: {self.supported_extensions}"
            )

    def validate_directory(self, directory: Path, glob_pattern: str = "*.csv") -> list[Path]:
        """
        Validate directory and return sorted list of matching files.

        Raises:
            FileNotFoundError: If directory does not exist.
            ValueError:        If no matching files found.
        """
        if not directory.exists():
            raise FileNotFoundError(f"Dataset directory not found: {directory}")
        if not directory.is_dir():
            raise ValueError(f"Path is not a directory: {directory}")

        files = sorted(directory.glob(glob_pattern))
        if not files:
            raise ValueError(
                f"No files matching {glob_pattern!r} found in {directory}"
            )

        log = logger.bind(dataset=self.dataset_name, directory=str(directory))
        log.info("dataset_files_found", count=len(files), files=[f.name for f in files])
        return files

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(dataset={self.dataset_name!r})"
