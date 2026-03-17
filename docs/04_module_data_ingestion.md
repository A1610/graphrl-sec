# 04 — Module: Data Ingestion Pipeline

## Phase 1, Module 1.1

---

## 1. What We Are Building

A data ingestion pipeline that reads raw network traffic datasets (CICIDS2017, UNSW-NB15), normalizes them into a unified event schema, and publishes them to Kafka topics. For local development, we also support batch ingestion from CSV files (simulating real-time streaming).

**In Simple Terms:** This module takes messy, different-format network log files and converts them into a clean, uniform JSON format that the rest of the system can consume.

---

## 2. Why We Are Building It

The entire GraphRL-Sec system depends on clean, normalized data. Different datasets have different column names, formats, and feature sets. Without a normalization layer:
- The graph constructor would need to handle every format separately
- Adding new data sources would require changes everywhere
- Testing would be inconsistent

This module is the **single source of truth** for data entering the system.

---

## 3. How It Works

```
CSV/PCAP Files ──▶ [DatasetParser] ──▶ [EventNormalizer] ──▶ [KafkaProducer]
                                                                    │
                                                               Kafka Topic:
                                                            "normalized-events"
```

### Internal Logic

1. **DatasetParser**: Each dataset (CICIDS, UNSW-NB15, LANL) has its own parser class that reads raw files and extracts relevant fields.

2. **EventNormalizer**: Maps dataset-specific fields to the Unified Event Schema (defined in 02_system_architecture.md). Handles:
   - Timestamp normalization (all to ISO 8601 UTC)
   - IP address validation
   - Protocol standardization
   - Feature scaling/encoding

3. **KafkaProducer**: Publishes normalized events to Kafka topics. Supports:
   - Batch mode (for historical data)
   - Streaming mode (for real-time simulation)
   - Rate limiting (configurable events/second)

---

## 4. Implementation Plan

### Task 4.1: Create Unified Event Schema (Pydantic Model)

```python
# src/ingestion/schemas.py
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum
from typing import Optional
import uuid

class EventType(str, Enum):
    NETWORK_FLOW = "network_flow"
    AUTH = "auth"
    DNS = "dns"
    PROCESS = "process"
    FILE = "file"

class SourceInfo(BaseModel):
    ip: str
    port: Optional[int] = None
    hostname: Optional[str] = None
    user: Optional[str] = None

class DestinationInfo(BaseModel):
    ip: str
    port: Optional[int] = None
    hostname: Optional[str] = None
    service: Optional[str] = None

class NetworkInfo(BaseModel):
    protocol: str = "TCP"
    bytes_sent: int = 0
    bytes_received: int = 0
    duration_ms: float = 0.0
    packets_sent: int = 0
    packets_received: int = 0

class EventMetadata(BaseModel):
    dataset_source: str
    original_label: str = "BENIGN"
    collector: str = "batch"

class UnifiedEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime
    event_type: EventType
    source: SourceInfo
    destination: DestinationInfo
    network: NetworkInfo
    metadata: EventMetadata
```

### Task 4.2: CICIDS2017 Parser

```python
# src/ingestion/parsers/cicids.py
```
- Read CICIDS CSV files (they have spaces in column names!)
- Map columns: `Source IP` → `source.ip`, `Destination Port` → `destination.port`, etc.
- Handle label mapping: `BENIGN`, `DDoS`, `PortScan`, `Bot`, etc.
- Handle NaN and Infinity values (common in CICIDS)

### Task 4.3: UNSW-NB15 Parser

```python
# src/ingestion/parsers/unsw.py
```
- Read UNSW CSV files
- Map columns: `srcip` → `source.ip`, `dsport` → `destination.port`, etc.
- Handle attack categories: Normal, Fuzzers, Analysis, Backdoors, DoS, Exploits, Generic, Reconnaissance, Shellcode, Worms

### Task 4.4: Kafka Producer Wrapper

```python
# src/ingestion/producer.py
```
- Async Kafka producer using `confluent-kafka`
- Configurable batch size and flush interval
- JSON serialization of UnifiedEvent
- Error handling and retry logic

### Task 4.5: Ingestion CLI Tool

```python
# src/ingestion/cli.py
```
- `python -m src.ingestion.cli ingest --dataset cicids --path data/raw/cicids/ --rate 1000`
- `python -m src.ingestion.cli ingest --dataset unsw --path data/raw/unsw/ --rate 500`

### Task 4.6: Batch Mode (No Kafka)

For early development (before Kafka is needed), support direct in-memory ingestion:
```python
# src/ingestion/batch.py
```
- Reads CSV → Normalizes → Returns list of UnifiedEvent
- Used by graph constructor directly (no Kafka dependency)

---

## 5. Folder Structure

```
src/ingestion/
├── __init__.py
├── schemas.py              # UnifiedEvent Pydantic models
├── normalizer.py           # EventNormalizer base class
├── producer.py             # Kafka producer wrapper
├── batch.py                # Batch ingestion (no Kafka)
├── cli.py                  # CLI tool
├── parsers/
│   ├── __init__.py
│   ├── base.py             # Abstract base parser
│   ├── cicids.py           # CICIDS2017 parser
│   ├── unsw.py             # UNSW-NB15 parser
│   └── lanl.py             # LANL dataset parser (Phase 3)
└── config.py               # Ingestion configuration
```

---

## 6. Dependencies Required

```
pandas>=2.0
polars>=0.20          # Fast CSV reading
pydantic>=2.5
confluent-kafka>=2.3
click>=8.1
tqdm>=4.66
```

---

## 7. Data Flow

```
Raw CSV File
    │
    ▼
[Parser.parse(filepath)] ── yields rows as dicts
    │
    ▼
[Normalizer.normalize(row)] ── returns UnifiedEvent
    │
    ├──▶ [Batch Mode] ── returns List[UnifiedEvent]
    │
    └──▶ [Kafka Mode] ── publishes to "normalized-events" topic
```

---

## 8. Expected Output

### Successful ingestion:
```
$ python -m src.ingestion.cli ingest --dataset cicids --path data/raw/cicids/Friday-WorkingHours-Afternoon-DDos.pcap_ISCX.csv --rate 1000

[INFO] Loading CICIDS2017 dataset from data/raw/cicids/...
[INFO] Parsed 225,745 rows
[INFO] Normalized 225,740 events (5 skipped: invalid IP)
[INFO] Publishing to Kafka topic: normalized-events
[INFO] ████████████████████████████████████ 100% | 225,740 events | 1,000/s
[INFO] Ingestion complete. Total: 225,740 events in 225.7s
```

### Sample normalized event:
```json
{
    "event_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "timestamp": "2017-07-07T15:30:00.000Z",
    "event_type": "network_flow",
    "source": {
        "ip": "192.168.10.50",
        "port": 54321,
        "hostname": null,
        "user": null
    },
    "destination": {
        "ip": "205.174.165.73",
        "port": 80,
        "hostname": null,
        "service": "http"
    },
    "network": {
        "protocol": "TCP",
        "bytes_sent": 0,
        "bytes_received": 0,
        "duration_ms": 0.0,
        "packets_sent": 1,
        "packets_received": 0
    },
    "metadata": {
        "dataset_source": "CICIDS2017",
        "original_label": "DDoS",
        "collector": "batch"
    }
}
```

---

## 9. Edge Cases

| Edge Case | Handling |
|---|---|
| NaN/Infinity in CICIDS numeric fields | Replace with 0, log warning |
| Invalid IP addresses | Skip row, log error |
| Missing timestamps | Use file-level timestamp or skip |
| Duplicate events | Deduplicate by (src_ip, dst_ip, timestamp, port) hash |
| Empty CSV files | Log warning, return empty list |
| Encoding issues | Force UTF-8, replace errors |
| Extremely large files (>10GB) | Use chunked reading (polars lazy frames) |

---

## 10. Testing Strategy

### Unit Tests
```
tests/unit/test_ingestion/
├── test_schemas.py          # Validate UnifiedEvent schema
├── test_cicids_parser.py    # CICIDS parsing with sample data
├── test_unsw_parser.py      # UNSW parsing with sample data
├── test_normalizer.py       # Edge cases in normalization
└── test_batch.py            # Batch ingestion pipeline
```

### Test with sample fixture:
```python
# tests/fixtures/sample_cicids.csv (10 rows)
# tests/fixtures/sample_unsw.csv (10 rows)
```

### Key test cases:
1. Schema validation: valid events pass, invalid events fail with clear error
2. Parser: correct column mapping for each dataset
3. Normalizer: timestamp conversion, IP validation, protocol mapping
4. Batch mode: end-to-end CSV → List[UnifiedEvent]
5. Edge cases: NaN handling, empty files, malformed rows

```python
# Example test
def test_cicids_parser_handles_nan():
    parser = CICIDSParser()
    row = {"Flow Duration": float('inf'), "Source IP": "192.168.1.1", ...}
    event = parser.parse_row(row)
    assert event.network.duration_ms == 0.0  # NaN replaced
```

---

## 11. Datasets Download Instructions

### UNSW-NB15 (Start with this — smallest)
```bash
mkdir -p data/raw/unsw
# Download from: https://research.unsw.edu.au/projects/unsw-nb15-dataset
# Files: UNSW-NB15_1.csv through UNSW-NB15_4.csv
# Place in data/raw/unsw/
```

### CICIDS2017
```bash
mkdir -p data/raw/cicids
# Download from: https://www.unb.ca/cic/datasets/ids-2017.html
# Files: Multiple CSV files (one per day)
# Place in data/raw/cicids/
```

---

## 12. Definition of Done

- [ ] UnifiedEvent schema validates correctly with all fields
- [ ] CICIDS parser reads real CICIDS CSV files and produces UnifiedEvents
- [ ] UNSW parser reads real UNSW CSV files and produces UnifiedEvents
- [ ] Batch mode works end-to-end: CSV → List[UnifiedEvent]
- [ ] Kafka mode publishes events to Redpanda topic
- [ ] All unit tests pass
- [ ] No type errors (mypy clean)
- [ ] No lint errors (ruff clean)
