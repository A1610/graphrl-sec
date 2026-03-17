"""
Unit tests for src/ingestion/parsers/unsw.py
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.ingestion.parsers.unsw import UNSWParser, _normalize_attack_cat, _normalize_proto
from src.ingestion.schemas import AttackLabel

FIXTURE_CSV = Path("tests/fixtures/sample_unsw.csv")


class TestUNSWParser:
    @pytest.fixture()
    def parser(self) -> UNSWParser:
        return UNSWParser()

    def test_parse_file_yields_rows(self, parser: UNSWParser) -> None:
        rows = list(parser.parse_file(FIXTURE_CSV))
        # Rows with 0.0.0.0 and 999.999.999.999 should be skipped
        assert len(rows) >= 8

    def test_parse_file_skips_zero_src_ip(self, parser: UNSWParser) -> None:
        rows = list(parser.parse_file(FIXTURE_CSV))
        for row in rows:
            assert row["src_ip"] != "0.0.0.0"

    def test_parse_file_skips_invalid_dst_ip(self, parser: UNSWParser) -> None:
        rows = list(parser.parse_file(FIXTURE_CSV))
        for row in rows:
            assert row["dst_ip"] != "999.999.999.999"

    def test_parse_file_required_fields_present(self, parser: UNSWParser) -> None:
        rows = list(parser.parse_file(FIXTURE_CSV))
        required = {"src_ip", "dst_ip", "protocol", "attack_label", "is_attack", "timestamp", "dataset_source"}
        for row in rows:
            assert required.issubset(row.keys())

    def test_parse_file_dataset_source_set(self, parser: UNSWParser) -> None:
        rows = list(parser.parse_file(FIXTURE_CSV))
        for row in rows:
            assert row["dataset_source"] == "UNSW-NB15"

    def test_parse_file_duration_converted_to_ms(self, parser: UNSWParser) -> None:
        rows = list(parser.parse_file(FIXTURE_CSV))
        # First row has dur=0.001121s => 1.121ms
        row = rows[0]
        assert abs(row["duration_ms"] - 1.121) < 0.01

    def test_parse_file_attack_labels_correct(self, parser: UNSWParser) -> None:
        rows = list(parser.parse_file(FIXTURE_CSV))
        labels = {r["attack_label"] for r in rows}
        assert AttackLabel.BENIGN in labels
        assert AttackLabel.EXPLOITS in labels

    def test_parse_file_is_attack_flag_consistent(self, parser: UNSWParser) -> None:
        rows = list(parser.parse_file(FIXTURE_CSV))
        for row in rows:
            if row["attack_label"] == AttackLabel.BENIGN:
                assert row["is_attack"] is False
            else:
                assert row["is_attack"] is True

    def test_parse_file_protocol_normalized(self, parser: UNSWParser) -> None:
        rows = list(parser.parse_file(FIXTURE_CSV))
        valid_protos = {"TCP", "UDP", "ICMP", "OTHER"}
        for row in rows:
            assert row["protocol"] in valid_protos

    def test_parse_file_timestamp_is_utc_datetime(self, parser: UNSWParser) -> None:
        from datetime import timezone
        rows = list(parser.parse_file(FIXTURE_CSV))
        for row in rows:
            ts = row["timestamp"]
            assert ts.tzinfo is not None
            assert ts.tzinfo == timezone.utc

    def test_file_not_found_raises(self, parser: UNSWParser) -> None:
        with pytest.raises(FileNotFoundError):
            list(parser.parse_file(Path("no_such_file.csv")))

    def test_chunk_size_does_not_affect_output(self, parser: UNSWParser) -> None:
        rows_small = list(parser.parse_file(FIXTURE_CSV, chunk_size=3))
        rows_large = list(parser.parse_file(FIXTURE_CSV, chunk_size=1000))
        assert len(rows_small) == len(rows_large)


# ---------------------------------------------------------------------------
# Protocol normalization
# ---------------------------------------------------------------------------


class TestProtoNormalization:
    def test_tcp(self) -> None:
        assert _normalize_proto("tcp") == "TCP"

    def test_udp(self) -> None:
        assert _normalize_proto("udp") == "UDP"

    def test_icmp(self) -> None:
        assert _normalize_proto("icmp") == "ICMP"

    def test_icmp6(self) -> None:
        assert _normalize_proto("icmp6") == "ICMP"

    def test_unknown_returns_other(self) -> None:
        assert _normalize_proto("ospf") == "OTHER"

    def test_empty_returns_other(self) -> None:
        assert _normalize_proto("") == "OTHER"

    def test_none_returns_other(self) -> None:
        assert _normalize_proto(None) == "OTHER"


# ---------------------------------------------------------------------------
# Attack category normalization
# ---------------------------------------------------------------------------


class TestAttackCatNormalization:
    def test_normal_label_0(self) -> None:
        label, is_attack = _normalize_attack_cat("Normal", 0)
        assert label == AttackLabel.BENIGN
        assert is_attack is False

    def test_exploits_label_1(self) -> None:
        label, is_attack = _normalize_attack_cat("Exploits", 1)
        assert label == AttackLabel.EXPLOITS
        assert is_attack is True

    def test_empty_cat_label_0_is_benign(self) -> None:
        label, is_attack = _normalize_attack_cat("", 0)
        assert label == AttackLabel.BENIGN
        assert is_attack is False

    def test_empty_cat_label_1_is_unknown(self) -> None:
        label, is_attack = _normalize_attack_cat("", 1)
        assert label == AttackLabel.UNKNOWN
        assert is_attack is True

    def test_backdoor_variant(self) -> None:
        label, _ = _normalize_attack_cat("Backdoor", 1)
        assert label == AttackLabel.BACKDOORS

    def test_case_insensitive(self) -> None:
        label, _ = _normalize_attack_cat("FUZZERS", 1)
        assert label == AttackLabel.FUZZERS

    def test_worms(self) -> None:
        label, _ = _normalize_attack_cat("Worms", 1)
        assert label == AttackLabel.WORMS

    def test_shellcode(self) -> None:
        label, _ = _normalize_attack_cat("Shellcode", 1)
        assert label == AttackLabel.SHELLCODE
