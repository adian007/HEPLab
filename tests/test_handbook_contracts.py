"""Adversarial boundary cases for the proposed target interchange contracts."""

import importlib.util
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts"
spec = importlib.util.spec_from_file_location("check_handbook", ROOT / "tools/check_handbook.py")
assert spec is not None and spec.loader is not None
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


def example(name):
    return json.loads((CONTRACTS / "examples" / f"{name}.json").read_text(encoding="utf-8"))


def validate(name, value):
    schema = json.loads((CONTRACTS / f"{name}.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(value)
    checker.semantic_example_checks(name, value)


def test_foreign_units_are_rejected_before_physics():
    value = example("event-chunk")
    value["units"]["length"] = "cm"
    with pytest.raises(ValidationError):
        validate("event-chunk", value)


def test_null_isolation_cannot_claim_valid_measurement():
    value = example("event-chunk")
    value["events"][0]["Muon"][0]["isolation"]["value"] = None
    with pytest.raises(ValidationError):
        validate("event-chunk", value)


def test_duplicate_source_ranges_cannot_double_count_a_plan():
    value = example("run-plan")
    value["source_ranges"].append(value["source_ranges"][0].copy())
    with pytest.raises(ValueError, match="overlapping"):
        validate("run-plan", value)


def test_source_mismatch_cannot_reassign_an_event_to_another_file():
    value = example("event-chunk")
    value["events"][0]["EventInfo"]["source_id"] = "1" * 64
    with pytest.raises(ValueError, match="differs"):
        validate("event-chunk", value)


def test_duplicate_object_identity_is_rejected():
    value = example("event-chunk")
    value["events"][0]["Muon"][1]["object_id"] = 0
    with pytest.raises(ValueError, match="duplicate muon"):
        validate("event-chunk", value)


def test_calibrated_fidelity_requires_calibration_payload():
    value = example("detector")
    value["fidelity"] = "T1"
    with pytest.raises(ValidationError):
        validate("detector", value)


def test_response_domain_must_be_increasing():
    value = example("detector")
    value["response"]["valid_pt"] = [100, 1]
    with pytest.raises(ValueError, match="increasing"):
        validate("detector", value)


def test_nonfinite_python_number_rejected_even_if_schema_number_accepts_it():
    value = example("event-chunk")
    value["events"][0]["Muon"][0]["eta"] = float("nan")
    with pytest.raises(ValueError, match="nonfinite"):
        validate("event-chunk", value)


def test_checksum_value_must_match_declared_algorithm():
    value = example("run-plan")
    value["source_ranges"][0]["declared_checksum"]["algorithm"] = "adler32"
    with pytest.raises(ValueError, match="checksum length"):
        validate("run-plan", value)


def test_measurement_requires_validation_evidence():
    value = example("run-plan")
    value["validation"] = {"mode": "measurement", "required_evidence_ids": []}
    with pytest.raises(ValueError, match="no required validation"):
        validate("run-plan", value)
