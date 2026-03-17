"""
UNSW-NB15 Dataset Parser.

Dataset: UNSW Network-Based Intrusion Detection 2015
URL:     https://research.unsw.edu.au/projects/unsw-nb15-dataset
Size:    ~2GB (4 CSV files: UNSW-NB15_1.csv to UNSW-NB15_4.csv)
Labels:  Normal + 9 attack categories

Attack categories:
  Fuzzers, Analysis, Backdoors, DoS, Exploits, Generic,
  Reconnaissance, Shellcode, Worms

CSV columns use lowercase short names (e.g. srcip, dsport, proto).
There are 49 features per flow.
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
# Canonical 49-column header for UNSW-NB15 raw files (no header row)
# Derived from NUSW-NB15_features.csv — same order as columns in the CSVs.
# ---------------------------------------------------------------------------
_UNSW_HEADERS: list[str] = [
    "srcip", "sport", "dstip", "dsport", "proto", "state", "dur",
    "sbytes", "dbytes", "sttl", "dttl", "sloss", "dloss", "service",
    "Sload", "Dload", "Spkts", "Dpkts", "swin", "dwin", "stcpb",
    "dtcpb", "smeansz", "dmeansz", "trans_depth", "res_bdy_len",
    "Sjit", "Djit", "Stime", "Ltime", "Sintpkt", "Dintpkt",
    "tcprtt", "synack", "ackdat", "is_sm_ips_ports", "ct_state_ttl",
    "ct_flw_http_mthd", "is_ftp_login", "ct_ftp_cmd", "ct_srv_src",
    "ct_srv_dst", "ct_dst_ltm", "ct_src_ltm", "ct_src_dport_ltm",
    "ct_dst_sport_ltm", "ct_dst_src_ltm", "attack_cat", "Label",
]

# ---------------------------------------------------------------------------
# Column mapping: UNSW-NB15 column name -> internal field name
# ---------------------------------------------------------------------------
_UNSW_COLUMN_MAP: dict[str, str] = {
    "srcip":    "src_ip",
    "sport":    "src_port",
    "dstip":    "dst_ip",
    "dsport":   "dst_port",
    "proto":    "protocol",
    "dur":      "duration_s",       # seconds (convert to ms)
    "sbytes":   "bytes_sent",
    "dbytes":   "bytes_received",
    "spkts":    "packets_sent",
    "dpkts":    "packets_received",
    "rate":     "flow_bytes_per_second",
    "smean":    "fwd_packet_length_mean",
    "dmean":    "bwd_packet_length_mean",
    "sinpkt":   "flow_iat_mean",    # src inter-packet arrival time
    "ct_srv_src": "ct_srv_src",     # extra UNSW feature
    "label":    "label_int",        # 0=normal, 1=attack
    "attack_cat": "attack_cat",
    "Stime":    "stime",            # start time (Unix epoch)
    "Ltime":    "ltime",            # last time (Unix epoch)
}

# ---------------------------------------------------------------------------
# Protocol name normalization
# ---------------------------------------------------------------------------
_PROTO_MAP: dict[str, str] = {
    "tcp":   "TCP",
    "udp":   "UDP",
    "icmp":  "ICMP",
    "icmp6": "ICMP",
    "arp":   "OTHER",
    "ospf":  "OTHER",
    "igmp":  "OTHER",
    "rtp":   "OTHER",
    "unas":  "OTHER",
    "sctp":  "OTHER",
}

# ---------------------------------------------------------------------------
# Attack category -> AttackLabel
# ---------------------------------------------------------------------------
_ATTACK_CAT_MAP: dict[str, AttackLabel] = {
    "":               AttackLabel.BENIGN,
    "normal":         AttackLabel.BENIGN,
    "fuzzers":        AttackLabel.FUZZERS,
    "analysis":       AttackLabel.ANALYSIS,
    "backdoors":      AttackLabel.BACKDOORS,
    "backdoor":       AttackLabel.BACKDOORS,
    "dos":            AttackLabel.DOS,
    "exploits":       AttackLabel.EXPLOITS,
    "generic":        AttackLabel.GENERIC,
    "reconnaissance": AttackLabel.RECONNAISSANCE,
    "shellcode":      AttackLabel.SHELLCODE,
    "worms":          AttackLabel.WORMS,
}


def _normalize_proto(raw: Any) -> str:
    """Normalize UNSW protocol string to standard name."""
    s = str(raw or "").strip().lower()
    return _PROTO_MAP.get(s, "OTHER")


def _normalize_attack_cat(cat: Any, label_int: Any) -> tuple[AttackLabel, bool]:
    """
    Derive AttackLabel and is_attack flag from UNSW attack_cat and label columns.

    UNSW uses label=0 for normal, label=1 for attack.
    attack_cat gives the specific category.
    """
    label_val = _safe_int(label_int, 0)
    is_attack = bool(label_val == 1)

    raw_cat = str(cat or "").strip().lower()
    attack_label = _ATTACK_CAT_MAP.get(raw_cat, AttackLabel.UNKNOWN if is_attack else AttackLabel.BENIGN)

    # If label=1 but cat is empty/unknown, set generic EXPLOITS
    if is_attack and attack_label == AttackLabel.BENIGN:
        attack_label = AttackLabel.UNKNOWN

    return attack_label, is_attack


def _parse_timestamp(stime: Any) -> datetime:
    """Parse UNSW Stime (Unix epoch float) to UTC datetime.

    Returns Unix epoch (1970-01-01T00:00:00Z) as a sentinel value when the
    timestamp is missing or invalid, so these records are identifiable and
    sort to the beginning of any time-ordered window.
    """
    try:
        ts = float(stime)
        if ts > 0:
            return datetime.fromtimestamp(ts, tz=timezone.utc)
    except (ValueError, TypeError, OSError):
        pass
    logger.debug("unsw_invalid_timestamp", raw_value=repr(stime))
    return datetime.fromtimestamp(0.0, tz=timezone.utc)


class UNSWParser(BaseParser):
    """
    Parser for UNSW-NB15 dataset CSV files.

    UNSW-NB15 has 4 CSV files (~500MB each) and a features CSV.
    Uses Polars lazy scan for memory-efficient chunk processing.
    Full dataset: ~2GB, ~2.5M rows across 4 files.
    """

    dataset_name = "UNSW-NB15"
    supported_extensions = (".csv",)

    def parse_file(
        self,
        filepath: Path,
        chunk_size: int = 50_000,
    ) -> Iterator[dict[str, Any]]:
        """
        Yield normalized row dicts from a single UNSW-NB15 CSV file.

        UNSW files may or may not have a header row.
        Files UNSW-NB15_1.csv through UNSW-NB15_4.csv have headers.
        """
        self.validate_file(filepath)
        log = logger.bind(parser="unsw", file=filepath.name)
        log.info("parsing_file_start", path=str(filepath))

        rows_yielded = 0
        rows_skipped = 0

        try:
            # Detect whether the file has a header row by peeking at the
            # first line.  Raw UNSW-NB15_1..4.csv files ship WITHOUT headers;
            # the training/testing sets DO have headers.
            has_hdr = _file_has_header(filepath)

            scan_kwargs: dict[str, Any] = {
                "ignore_errors": True,
                "truncate_ragged_lines": True,
                "encoding": "utf8-lossy",
                "infer_schema_length": 10_000,
                "null_values": ["", "N/A", "NA", "null", "NULL", "-"],
            }
            if has_hdr:
                lazy = pl.scan_csv(filepath, has_header=True, **scan_kwargs)
            else:
                # No header — assign canonical column names explicitly.
                lazy = pl.scan_csv(
                    filepath,
                    has_header=False,
                    new_columns=_UNSW_HEADERS,
                    **scan_kwargs,
                )

            # Normalize column names to lowercase stripped
            schema_names = lazy.collect_schema().names()
            lazy = lazy.rename({col: col.strip().lower() for col in schema_names})

            # Re-fetch normalized column names
            available = lazy.collect_schema().names()
            needed = [c for c in _UNSW_COLUMN_MAP if c in available]

            if not needed:
                raise ValueError(
                    f"No recognized UNSW-NB15 columns found in {filepath.name}. "
                    f"Expected columns like: {list(_UNSW_COLUMN_MAP.keys())[:5]}"
                )

            lazy = lazy.select(needed)

            offset = 0
            while True:
                chunk_df = lazy.slice(offset, chunk_size).collect()
                if chunk_df.is_empty():
                    break

                for row in chunk_df.iter_rows(named=True):
                    parsed = self._parse_row(row)
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
        glob_pattern: str = "UNSW-NB15_*.csv",
    ) -> Iterator[dict[str, Any]]:
        """
        Yield row dicts from all UNSW-NB15_1.csv through UNSW-NB15_4.csv.
        Skips the features CSV (UNSW_NB15_LIST_EVENTS.csv) automatically.
        """
        files = self.validate_directory(directory, glob_pattern)
        log = logger.bind(parser="unsw", directory=str(directory))

        total_yielded = 0
        for i, filepath in enumerate(files, 1):
            # Skip the events/features metadata file
            if "list_events" in filepath.name.lower() or "features" in filepath.name.lower():
                log.info("skipping_metadata_file", file=filepath.name)
                continue

            log.info("processing_file", current=i, total=len(files), file=filepath.name)
            for row in self.parse_file(filepath, chunk_size=chunk_size):
                total_yielded += 1
                yield row

        log.info("directory_parse_complete", total_rows=total_yielded)

    def _parse_row(self, row: dict[str, Any]) -> dict[str, Any] | None:
        """Convert a raw UNSW row to normalized intermediate dict."""
        src_ip = str(row.get("srcip", "") or "").strip()
        dst_ip = str(row.get("dstip", "") or "").strip()

        # Skip rows with missing or clearly invalid IPs
        if not src_ip or not dst_ip or src_ip in ("nan", "0.0.0.0") or dst_ip in ("nan", "0.0.0.0"):
            return None

        if not _is_valid_ip(src_ip) or not _is_valid_ip(dst_ip):
            return None

        # Duration: UNSW stores in seconds
        duration_s = _safe_float(row.get("dur"), 0.0)
        duration_ms = duration_s * 1000.0

        # Attack label
        attack_label, is_attack = _normalize_attack_cat(
            row.get("attack_cat"), row.get("label")
        )

        # Timestamp
        timestamp = _parse_timestamp(row.get("stime") or row.get("Stime"))

        return {
            "src_ip":   src_ip,
            "src_port": _safe_int(row.get("sport"), None),
            "dst_ip":   dst_ip,
            "dst_port": _safe_int(row.get("dsport"), None),
            "protocol": _normalize_proto(row.get("proto")),
            "duration_ms":               duration_ms,
            "bytes_sent":                _safe_int(row.get("sbytes"), 0),
            "bytes_received":            _safe_int(row.get("dbytes"), 0),
            "packets_sent":              _safe_int(row.get("spkts"), 0),
            "packets_received":          _safe_int(row.get("dpkts"), 0),
            "flow_bytes_per_second":     _safe_float(row.get("rate"), 0.0),
            "flow_packets_per_second":   0.0,   # not in UNSW schema
            "fwd_packet_length_mean":    _safe_float(row.get("smean"), 0.0),
            "bwd_packet_length_mean":    _safe_float(row.get("dmean"), 0.0),
            "flow_iat_mean":             _safe_float(row.get("sinpkt"), 0.0),
            "active_mean":               0.0,   # not in UNSW schema
            "idle_mean":                 0.0,   # not in UNSW schema
            "original_label": str(row.get("attack_cat", "Normal") or "Normal").strip(),
            "attack_label":   attack_label,
            "is_attack":      is_attack,
            "timestamp":      timestamp,
            "dataset_source": "UNSW-NB15",
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _file_has_header(filepath: Path) -> bool:
    """Return True if the first line of filepath looks like a UNSW header row."""
    try:
        with filepath.open("r", encoding="utf-8-sig", errors="replace") as f:
            first = f.readline().lower()
        return "srcip" in first or "sport" in first or "dstip" in first
    except OSError:
        return True   # safe default: assume header present


def _is_valid_ip(ip: str) -> bool:
    """Return True if ip is a valid IPv4 address."""
    import ipaddress
    try:
        ipaddress.IPv4Address(ip)
        return True
    except ValueError:
        return False


def _safe_float(val: Any, default: float) -> float:
    import math
    if val is None:
        return default
    try:
        f = float(val)
        return default if (math.isnan(f) or math.isinf(f)) else f
    except (ValueError, TypeError):
        return default


def _safe_int(val: Any, default: int | None) -> int | None:
    import math
    if val is None:
        return default
    try:
        f = float(val)
        return default if (math.isnan(f) or math.isinf(f)) else int(f)
    except (ValueError, TypeError):
        return default
