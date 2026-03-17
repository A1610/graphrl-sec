"""
Unit tests for src/ingestion/parsers/cicids.py
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.ingestion.parsers.cicids import CICIDSParser, _normalize_label, _safe_float, _safe_int
from src.ingestion.schemas import AttackLabel

FIXTURE_CSV = Path("tests/fixtures/sample_cicids.csv")


class TestCICIDSParser:
    @pytest.fixture()
    def parser(self) -> CICIDSParser:
        return CICIDSParser()

    # ------------------------------------------------------------------
    # File parsing
    # ------------------------------------------------------------------

    def test_parse_file_yields_rows(self, parser: CICIDSParser) -> None:
        rows = list(parser.parse_file(FIXTURE_CSV, chunk_size=100))
        # Rows 11 (invalid IP), 12 (missing dst IP) should be skipped
        assert len(rows) > 5

    def test_parse_file_skips_invalid_src_ip(self, parser: CICIDSParser) -> None:
        rows = list(parser.parse_file(FIXTURE_CSV))
        src_ips = [r["src_ip"] for r in rows]
        assert "999.999.999.999" not in src_ips

    def test_parse_file_skips_missing_dst_ip(self, parser: CICIDSParser) -> None:
        rows = list(parser.parse_file(FIXTURE_CSV))
        for row in rows:
            assert row["dst_ip"] != ""
            assert row["dst_ip"] is not None

    def test_parse_file_inf_sanitized(self, parser: CICIDSParser) -> None:
        rows = list(parser.parse_file(FIXTURE_CSV))
        for row in rows:
            import math
            for key in ("flow_bytes_per_second", "fwd_packet_length_mean", "bwd_packet_length_mean"):
                val = row.get(key, 0.0)
                assert not math.isnan(float(val)), f"{key} is NaN"
                assert not math.isinf(float(val)), f"{key} is Inf"

    def test_parse_file_required_fields_present(self, parser: CICIDSParser) -> None:
        rows = list(parser.parse_file(FIXTURE_CSV))
        required = {"src_ip", "dst_ip", "protocol", "attack_label", "dataset_source", "timestamp"}
        for row in rows:
            assert required.issubset(row.keys()), f"Missing fields: {required - row.keys()}"

    def test_parse_file_label_mapping(self, parser: CICIDSParser) -> None:
        rows = list(parser.parse_file(FIXTURE_CSV))
        # Row with port 54322 is DDoS
        assert any(r["attack_label"] == AttackLabel.DDOS for r in rows)
        # Row with port 54321 is BENIGN
        assert any(r["attack_label"] == AttackLabel.BENIGN for r in rows)

    def test_parse_file_dataset_source_set(self, parser: CICIDSParser) -> None:
        rows = list(parser.parse_file(FIXTURE_CSV))
        for row in rows:
            assert row["dataset_source"] == "CICIDS2017"

    def test_parse_file_duration_converted_from_microseconds(self, parser: CICIDSParser) -> None:
        rows = list(parser.parse_file(FIXTURE_CSV))
        # Flow Duration in CSV is 150000 µs = 150ms
        row = next(r for r in rows if r["src_port"] == 54321)
        assert abs(row["duration_ms"] - 150.0) < 0.01

    def test_file_not_found_raises(self, parser: CICIDSParser) -> None:
        with pytest.raises(FileNotFoundError):
            list(parser.parse_file(Path("nonexistent.csv")))

    def test_wrong_extension_raises(self, parser: CICIDSParser, tmp_path: Path) -> None:
        bad_file = tmp_path / "data.txt"
        bad_file.write_text("dummy")
        with pytest.raises(ValueError, match="Unsupported file extension"):
            list(parser.parse_file(bad_file))

    def test_directory_not_found_raises(self, parser: CICIDSParser) -> None:
        with pytest.raises(FileNotFoundError):
            list(parser.parse_directory(Path("nonexistent_dir/")))

    def test_chunk_size_does_not_affect_output(self, parser: CICIDSParser) -> None:
        rows_small = list(parser.parse_file(FIXTURE_CSV, chunk_size=3))
        rows_large = list(parser.parse_file(FIXTURE_CSV, chunk_size=1000))
        assert len(rows_small) == len(rows_large)

    def test_is_attack_flag_set_correctly(self, parser: CICIDSParser) -> None:
        rows = list(parser.parse_file(FIXTURE_CSV))
        for row in rows:
            if row["attack_label"] == AttackLabel.BENIGN:
                assert row["is_attack"] is False
            else:
                assert row["is_attack"] is True


# ---------------------------------------------------------------------------
# Label normalization
# ---------------------------------------------------------------------------


class TestLabelNormalization:
    def test_benign_label(self) -> None:
        assert _normalize_label("BENIGN") == AttackLabel.BENIGN

    def test_ddos_label(self) -> None:
        assert _normalize_label("DDoS") == AttackLabel.DDOS

    def test_portscan_label(self) -> None:
        assert _normalize_label("PortScan") == AttackLabel.PORT_SCAN

    def test_unknown_label_returns_unknown(self) -> None:
        assert _normalize_label("SomeMadeUpAttack") == AttackLabel.UNKNOWN

    def test_case_insensitive_fallback(self) -> None:
        assert _normalize_label("DDOS") == AttackLabel.DDOS

    def test_dos_hulk_label(self) -> None:
        assert _normalize_label("DoS Hulk") == AttackLabel.DOS_HULK


# ---------------------------------------------------------------------------
# Safe type coercion helpers
# ---------------------------------------------------------------------------


class TestSafeFloat:
    def test_valid_float(self) -> None:
        assert _safe_float(3.14, 0.0) == 3.14

    def test_inf_returns_default(self) -> None:
        assert _safe_float(float("inf"), 0.0) == 0.0

    def test_nan_returns_default(self) -> None:
        assert _safe_float(float("nan"), 0.0) == 0.0

    def test_none_returns_default(self) -> None:
        assert _safe_float(None, -1.0) == -1.0

    def test_string_float(self) -> None:
        assert _safe_float("2.5", 0.0) == 2.5

    def test_invalid_string_returns_default(self) -> None:
        assert _safe_float("abc", 99.0) == 99.0


class TestSafeInt:
    def test_valid_int(self) -> None:
        assert _safe_int(42, 0) == 42

    def test_float_string_converted(self) -> None:
        assert _safe_int("3.7", 0) == 3

    def test_inf_returns_default(self) -> None:
        assert _safe_int(float("inf"), 0) == 0

    def test_none_returns_default(self) -> None:
        assert _safe_int(None, None) is None

    def test_invalid_string_returns_default(self) -> None:
        assert _safe_int("xyz", 5) == 5
