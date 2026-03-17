"""
CICIDS2017 Dataset Parser.

Dataset: Canadian Institute for Cybersecurity Intrusion Detection System 2017
URL:     https://www.unb.ca/cic/datasets/ids-2017.html
Size:    ~7GB (multiple CSV files, one per day)
Labels:  BENIGN, DDoS, PortScan, Bot, Infiltration, BruteForce, etc.

Known quirks handled here:
  - Column names have leading/trailing spaces: " Source IP" -> "Source IP"
  - Numeric fields contain Inf and NaN values
  - Label column is " Label" (with leading space)
  - Some rows have wrong number of columns (skipped)
  - Timestamps are not in the CSV — derived from filename
  - Duplicate flows are common
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import polars as pl
import structlog

from src.ingestion.parsers.base import BaseParser
from src.ingestion.schemas import AttackLabel

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Column mapping: CICIDS2017 column name -> internal field name
# ---------------------------------------------------------------------------
_CICIDS_COLUMN_MAP: dict[str, str] = {
    "Source IP":                    "src_ip",
    "Source Port":                  "src_port",
    "Destination IP":               "dst_ip",
    "Destination Port":             "dst_port",
    "Protocol":                     "protocol_num",
    "Flow Duration":                "duration_us",       # microseconds
    "Total Fwd Packets":            "packets_sent",
    "Total Backward Packets":       "packets_received",
    "Total Length of Fwd Packets":  "bytes_sent",
    "Total Length of Bwd Packets":  "bytes_received",
    "Flow Bytes/s":                 "flow_bytes_per_second",
    "Flow Packets/s":               "flow_packets_per_second",
    "Fwd Packet Length Mean":       "fwd_packet_length_mean",
    "Bwd Packet Length Mean":       "bwd_packet_length_mean",
    "Flow IAT Mean":                "flow_iat_mean",
    "Active Mean":                  "active_mean",
    "Idle Mean":                    "idle_mean",
    "Timestamp":                    "timestamp_str",  # GeneratedLabelledFlows only
    "Label":                        "label",
}

# ---------------------------------------------------------------------------
# Protocol number -> name mapping (IANA)
# ---------------------------------------------------------------------------
_PROTOCOL_MAP: dict[int, str] = {
    6:   "TCP",
    17:  "UDP",
    1:   "ICMP",
    0:   "OTHER",
}

# ---------------------------------------------------------------------------
# Label normalization: raw CICIDS label -> AttackLabel enum value
# ---------------------------------------------------------------------------
_LABEL_MAP: dict[str, AttackLabel] = {
    "BENIGN":               AttackLabel.BENIGN,
    "DDoS":                 AttackLabel.DDOS,
    "DoS Hulk":             AttackLabel.DOS_HULK,
    "DoS GoldenEye":        AttackLabel.DOS_GOLDENEYE,
    "DoS slowloris":        AttackLabel.DOS_SLOWLORIS,
    "DoS Slowhttptest":     AttackLabel.DOS_SLOWHTTPTEST,
    "PortScan":             AttackLabel.PORT_SCAN,
    "FTP-Patator":          AttackLabel.FTP_PATATOR,
    "SSH-Patator":          AttackLabel.SSH_PATATOR,
    "Bot":                  AttackLabel.BOT,
    "Web Attack \x96 Brute Force":   AttackLabel.BRUTE_FORCE,
    "Web Attack \x96 XSS":           AttackLabel.XSS,
    "Web Attack \x96 Sql Injection":  AttackLabel.SQL_INJECTION,
    "Web Attack \ufffd Brute Force":  AttackLabel.BRUTE_FORCE,   # utf8-lossy replacement
    "Web Attack \ufffd XSS":          AttackLabel.XSS,
    "Web Attack \ufffd Sql Injection": AttackLabel.SQL_INJECTION,
    "Web Attack ? Brute Force":      AttackLabel.BRUTE_FORCE,   # ? replacement
    "Web Attack ? XSS":              AttackLabel.XSS,
    "Web Attack ? Sql Injection":    AttackLabel.SQL_INJECTION,
    "Web Attack Brute Force":        AttackLabel.BRUTE_FORCE,
    "Web Attack XSS":                AttackLabel.XSS,
    "Web Attack Sql Injection":      AttackLabel.SQL_INJECTION,
    "Infiltration":         AttackLabel.INFILTRATION,
    "Heartbleed":           AttackLabel.HEARTBLEED,
}

# Regex to extract date from CICIDS filename
# e.g. "Friday-WorkingHours-Afternoon-DDos.pcap_ISCX.csv"
_FILENAME_DATE_PATTERNS: dict[str, str] = {
    "Monday":    "2017-07-03",
    "Tuesday":   "2017-07-04",
    "Wednesday": "2017-07-05",
    "Thursday":  "2017-07-06",
    "Friday":    "2017-07-07",
}


def _parse_cicids_timestamp(raw: Any, fallback: datetime) -> datetime:
    """
    Parse a CICIDS GeneratedLabelledFlows timestamp string.

    Format: "03/07/2017 08:55:58"  (DD/MM/YYYY HH:MM:SS, UTC)
    Falls back to the file-derived date when the value is missing or invalid.
    """
    if not raw:
        return fallback
    s = str(raw).strip()
    if not s or s.lower() in ("nan", "none", "null"):
        return fallback
    for fmt in ("%d/%m/%Y %H:%M:%S", "%m/%d/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return fallback


def _extract_file_date(filepath: Path) -> datetime:
    """Extract the recording date from the CICIDS filename."""
    name = filepath.stem  # e.g. "Friday-WorkingHours-Afternoon-DDos.pcap_ISCX"
    for day_name, date_str in _FILENAME_DATE_PATTERNS.items():
        if day_name.lower() in name.lower():
            return datetime.fromisoformat(f"{date_str}T00:00:00+00:00")
    # Fallback: use file modification time
    mtime = filepath.stat().st_mtime
    return datetime.fromtimestamp(mtime, tz=timezone.utc)


def _normalize_columns(df: pl.DataFrame) -> pl.DataFrame:
    """Strip leading/trailing whitespace from all column names."""
    return df.rename({col: col.strip() for col in df.columns})


def _protocol_num_to_str(num: Any) -> str:
    """Convert IANA protocol number to name string."""
    try:
        return _PROTOCOL_MAP.get(int(float(str(num))), "OTHER")
    except (ValueError, TypeError):
        return "OTHER"


def _normalize_label(raw_label: str) -> AttackLabel:
    """Map raw CICIDS label string to AttackLabel enum."""
    cleaned = str(raw_label).strip()
    if cleaned in _LABEL_MAP:
        return _LABEL_MAP[cleaned]
    # Case-insensitive fallback
    upper = cleaned.upper()
    for key, val in _LABEL_MAP.items():
        if key.upper() == upper:
            return val
    logger.warning("unknown_cicids_label", raw_label=cleaned)
    return AttackLabel.UNKNOWN


class CICIDSParser(BaseParser):
    """
    Parser for CICIDS2017 dataset CSV files.

    Uses Polars lazy evaluation for memory-efficient processing of large files.
    A single CICIDS file can be 200-500MB; the full dataset is ~7GB.
    Chunked reading ensures we never load more than `chunk_size` rows at once.
    """

    dataset_name = "CICIDS2017"
    supported_extensions = (".csv",)

    def parse_file(
        self,
        filepath: Path,
        chunk_size: int = 50_000,
    ) -> Iterator[dict[str, Any]]:
        """
        Yield normalized row dicts from a single CICIDS2017 CSV file.

        Args:
            filepath:   Path to a CICIDS CSV file.
            chunk_size: Rows per batch (controls peak memory usage).

        Yields:
            Dict with standardized field names ready for EventNormalizer.
        """
        self.validate_file(filepath)
        file_date = _extract_file_date(filepath)
        log = logger.bind(
            parser="cicids",
            file=filepath.name,
            file_date=file_date.date().isoformat(),
        )
        log.info("parsing_file_start", path=str(filepath))

        rows_yielded = 0
        rows_skipped = 0

        try:
            # Use Polars lazy scan — reads metadata only, not full file
            lazy = pl.scan_csv(
                filepath,
                has_header=True,
                ignore_errors=True,          # skip malformed rows
                truncate_ragged_lines=True,  # handle rows with wrong col count
                encoding="utf8-lossy",       # handle encoding issues
                infer_schema_length=10_000,  # infer types from first 10k rows
                null_values=["", "N/A", "NA", "null", "NULL", "Infinity", "-Infinity"],
            )

            # Strip column name whitespace
            lazy = lazy.rename({col: col.strip() for col in lazy.collect_schema().names()})

            # Collect only the columns we need (pushdown projection).
            # _CICIDS_COLUMN_MAP already includes "Label" — select all mapped
            # columns that exist in the file schema.
            schema_names = set(lazy.collect_schema().names())
            needed_cols = [c for c in _CICIDS_COLUMN_MAP if c in schema_names]
            missing = set(_CICIDS_COLUMN_MAP.keys()) - set(needed_cols)
            if "Label" in missing:
                log.warning("label_column_missing_attack_classification_disabled")
            if missing - {"Label"}:
                log.warning("missing_columns", missing=list(missing - {"Label"}))

            lazy = lazy.select(needed_cols)

            # Process in chunks using slice
            offset = 0
            while True:
                chunk_df = lazy.slice(offset, chunk_size).collect()
                if chunk_df.is_empty():
                    break

                for row in chunk_df.iter_rows(named=True):
                    parsed = self._parse_row(row, file_date)
                    if parsed is None:
                        rows_skipped += 1
                        continue
                    rows_yielded += 1
                    yield parsed

                if len(chunk_df) < chunk_size:
                    break
                offset += chunk_size

        except Exception as exc:
            log.error("parsing_file_error", error=str(exc), exc_info=True)
            raise

        log.info(
            "parsing_file_complete",
            rows_yielded=rows_yielded,
            rows_skipped=rows_skipped,
        )

    def parse_directory(
        self,
        directory: Path,
        chunk_size: int = 50_000,
        glob_pattern: str = "*.csv",
    ) -> Iterator[dict[str, Any]]:
        """
        Yield row dicts from ALL CICIDS CSV files in a directory.

        Files are processed in sorted order (Monday → Friday).
        """
        files = self.validate_directory(directory, glob_pattern)
        log = logger.bind(parser="cicids", directory=str(directory))

        total_yielded = 0
        for i, filepath in enumerate(files, 1):
            log.info("processing_file", current=i, total=len(files), file=filepath.name)
            for row in self.parse_file(filepath, chunk_size=chunk_size):
                total_yielded += 1
                yield row

        log.info("directory_parse_complete", total_rows=total_yielded)

    def _parse_row(
        self,
        row: dict[str, Any],
        file_date: datetime,
    ) -> dict[str, Any] | None:
        """
        Convert a raw CICIDS row dict to a normalized intermediate dict.

        Returns None if the row should be skipped (invalid IP, etc.).
        """
        # --- Source IP validation ---
        src_ip = str(row.get("Source IP", "") or "").strip()
        dst_ip = str(row.get("Destination IP", "") or "").strip()
        if not src_ip or not dst_ip or src_ip == "nan" or dst_ip == "nan":
            return None

        # Validate IP addresses (catches 999.x.x.x etc.)
        if not _is_valid_ip(src_ip) or not _is_valid_ip(dst_ip):
            return None

        # --- Protocol ---
        protocol = _protocol_num_to_str(row.get("Protocol"))

        # --- Duration: CICIDS stores in microseconds ---
        duration_us = _safe_float(row.get("Flow Duration"), 0.0)
        duration_ms = duration_us / 1000.0

        # --- Label ---
        raw_label = str(row.get("Label", "BENIGN") or "BENIGN").strip()
        attack_label = _normalize_label(raw_label)
        is_attack = attack_label != AttackLabel.BENIGN

        return {
            # Endpoint info
            "src_ip":   src_ip,
            "src_port": _safe_int(row.get("Source Port"), None),
            "dst_ip":   dst_ip,
            "dst_port": _safe_int(row.get("Destination Port"), None),
            # Network stats
            "protocol":                  protocol,
            "duration_ms":               duration_ms,
            "bytes_sent":                _safe_int(row.get("Total Length of Fwd Packets"), 0),
            "bytes_received":            _safe_int(row.get("Total Length of Bwd Packets"), 0),
            "packets_sent":              _safe_int(row.get("Total Fwd Packets"), 0),
            "packets_received":          _safe_int(row.get("Total Backward Packets"), 0),
            "flow_bytes_per_second":     _safe_float(row.get("Flow Bytes/s"), 0.0),
            "flow_packets_per_second":   _safe_float(row.get("Flow Packets/s"), 0.0),
            "fwd_packet_length_mean":    _safe_float(row.get("Fwd Packet Length Mean"), 0.0),
            "bwd_packet_length_mean":    _safe_float(row.get("Bwd Packet Length Mean"), 0.0),
            "flow_iat_mean":             _safe_float(row.get("Flow IAT Mean"), 0.0),
            "active_mean":               _safe_float(row.get("Active Mean"), 0.0),
            "idle_mean":                 _safe_float(row.get("Idle Mean"), 0.0),
            # Labels
            "original_label": raw_label,
            "attack_label":   attack_label,
            "is_attack":      is_attack,
            # Provenance — use real timestamp when available, else file date
            "timestamp":      _parse_cicids_timestamp(row.get("Timestamp"), file_date),
            "dataset_source": "CICIDS2017",
        }


# ---------------------------------------------------------------------------
# Safe type coercion helpers
# ---------------------------------------------------------------------------


def _is_valid_ip(ip: str) -> bool:
    """Return True if ip is a valid IPv4 address."""
    import ipaddress
    try:
        ipaddress.IPv4Address(ip)
        return True
    except ValueError:
        return False


def _safe_float(val: Any, default: float) -> float:
    """Convert to float, replacing NaN/Inf/None with default."""
    import math
    if val is None:
        return default
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (ValueError, TypeError):
        return default


def _safe_int(val: Any, default: int | None) -> int | None:
    """Convert to int, returning default on failure."""
    import math
    if val is None:
        return default
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return default
        return int(f)
    except (ValueError, TypeError):
        return default
