from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from chatledger_core.domain.generator.ground_truth import GroundTruthMeta, Overlap, build_document
from generator_support import Rendered

SCHEMA = Path(__file__).resolve().parents[5] / "tests/fixtures/generator/ground-truth.schema.json"


@pytest.fixture(scope="module")
def validator() -> jsonschema.Draft202012Validator:
    schema = json.loads(SCHEMA.read_text())
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(schema)


def test_generated_ground_truth_validates(
    validator: jsonschema.Draft202012Validator, small_stress: Rendered
) -> None:
    meta = GroundTruthMeta("1.0.0", 42, "small", "stress", 10_000, 50, 10_000)
    document = json.loads(build_document(meta, small_stress.anomalies))
    validator.validate(document)
    assert document["totals"]["anomalies"] > 0


def test_overlap_and_clean_documents_validate(validator: jsonschema.Draft202012Validator) -> None:
    meta = GroundTruthMeta("1.0.0", 43, "small", "clean", 10_000, 50, 9_000, Overlap(42, 30))
    validator.validate(json.loads(build_document(meta, [])))


def test_missing_key_is_rejected(validator: jsonschema.Draft202012Validator) -> None:
    meta = GroundTruthMeta("1.0.0", 1, "small", "clean", 10_000, 50, 10_000)
    document = json.loads(build_document(meta, []))
    del document["totals"]
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(document)
