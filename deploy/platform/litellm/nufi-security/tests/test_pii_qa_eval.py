"""CMP-350 — PII QA 평가셋 로딩 + 스키마 검증 테스트."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DATASET_PATH = ROOT / "data" / "pii_qa_eval.jsonl"

REQUIRED_FIELDS = {"id", "question", "expected_answer", "pii_entities", "category"}
REQUIRED_ENTITY_FIELDS = {"type", "value", "start", "end"}
VALID_PII_TYPES = {"KR_PERSON", "KR_PHONE", "EMAIL", "KR_LOCATION", "KR_BRN"}
VALID_CATEGORIES = {"customer_service", "document_summary", "payment", "hr", "medical", "legal"}

MIN_SAMPLES = 100
MAX_SAMPLES = 300
MIN_PII_TYPES = 5
CONTROL_MIN_RATIO = 0.10
CONTROL_MAX_RATIO = 0.20


@pytest.fixture(scope="module")
def dataset():
    assert DATASET_PATH.exists(), f"Dataset not found: {DATASET_PATH}"
    rows = []
    with open(DATASET_PATH, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            row["_lineno"] = lineno
            rows.append(row)
    return rows


def test_dataset_exists():
    assert DATASET_PATH.exists()


def test_sample_count(dataset):
    assert MIN_SAMPLES <= len(dataset) <= MAX_SAMPLES, (
        f"Expected {MIN_SAMPLES}~{MAX_SAMPLES} samples, got {len(dataset)}"
    )


def test_schema_fields(dataset):
    for row in dataset:
        missing = REQUIRED_FIELDS - set(row.keys())
        assert not missing, f"Row {row.get('id', '?')}: missing fields {missing}"


def test_id_uniqueness(dataset):
    ids = [row["id"] for row in dataset]
    assert len(ids) == len(set(ids)), "Duplicate IDs found"


def test_entity_schema(dataset):
    for row in dataset:
        for ent in row["pii_entities"]:
            missing = REQUIRED_ENTITY_FIELDS - set(ent.keys())
            assert not missing, f"Row {row['id']}: entity missing fields {missing}"
            assert isinstance(ent["start"], int)
            assert isinstance(ent["end"], int)
            assert ent["start"] >= 0
            assert ent["end"] > ent["start"]
            assert ent["type"] in VALID_PII_TYPES, (
                f"Row {row['id']}: unknown PII type {ent['type']}"
            )


def test_entity_offsets(dataset):
    """Verify that start/end offsets correctly point to the value in the question."""
    for row in dataset:
        q = row["question"]
        for ent in row["pii_entities"]:
            extracted = q[ent["start"]:ent["end"]]
            assert extracted == ent["value"], (
                f"Row {row['id']}: offset mismatch for {ent['type']}: "
                f"expected {ent['value']!r}, got {extracted!r}"
            )


def test_categories(dataset):
    cats = {row["category"] for row in dataset}
    assert cats == VALID_CATEGORIES, f"Category mismatch: {cats}"


def test_pii_type_coverage(dataset):
    types_seen = set()
    for row in dataset:
        for ent in row["pii_entities"]:
            types_seen.add(ent["type"])
    assert len(types_seen) >= MIN_PII_TYPES, (
        f"Expected >= {MIN_PII_TYPES} PII types, got {len(types_seen)}: {types_seen}"
    )


def test_control_group_ratio(dataset):
    ctrl = [r for r in dataset if not r["pii_entities"]]
    ratio = len(ctrl) / len(dataset)
    assert CONTROL_MIN_RATIO <= ratio <= CONTROL_MAX_RATIO, (
        f"Control group ratio {ratio:.2%} not in [{CONTROL_MIN_RATIO:.0%}, {CONTROL_MAX_RATIO:.0%}]"
    )


def test_pii_samples_have_entities(dataset):
    """Non-control samples must have at least 1 PII entity."""
    pii_rows = [r for r in dataset if r["pii_entities"]]
    for row in pii_rows:
        assert len(row["pii_entities"]) >= 1


def test_pii_in_expected_answer(dataset):
    """Most PII samples should have PII values in expected_answer (for roundtrip testing)."""
    pii_rows = [r for r in dataset if r["pii_entities"]]
    pii_in_answer = sum(
        1 for r in pii_rows
        if any(e["value"] in r["expected_answer"] for e in r["pii_entities"])
    )
    ratio = pii_in_answer / len(pii_rows)
    assert ratio >= 0.8, (
        f"Only {ratio:.0%} of PII samples have PII in expected_answer (need >= 80%)"
    )
