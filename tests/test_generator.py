import json

from roberta_eval.corpus import serialize_jsonl
from roberta_eval.generator import (
    generate_cases,
    generated_digest,
    generated_summary,
    load_surfaces,
    validate_surfaces,
)


def test_surface_matrix_is_valid() -> None:
    surfaces = load_surfaces()
    validate_surfaces(surfaces)
    assert len(surfaces["prefixes"]) == 10
    assert len(surfaces["suffixes"]) == 6


def test_generation_exceeds_2500_target() -> None:
    cases = generate_cases()
    assert len(cases) == 3240
    assert len({case["case_id"] for case in cases}) == 3240
    assert len({case["service"] for case in cases}) == 18


def test_every_blueprint_gets_60_unique_surface_forms() -> None:
    grouped = {}
    for case in generate_cases():
        grouped.setdefault(case["blueprint_id"], []).append(case)
    assert len(grouped) == 54
    for variants in grouped.values():
        assert len(variants) == 60
        assert len({item["question"] for item in variants}) == 60


def test_generation_preserves_objective_fixture_and_checks() -> None:
    grouped = {}
    for case in generate_cases():
        grouped.setdefault(case["blueprint_id"], []).append(case)

    for variants in grouped.values():
        assert len({item["objective_signature"] for item in variants}) == 1
        fixture_serializations = {
            json.dumps(item["fixture"], sort_keys=True) for item in variants
        }
        check_serializations = {
            json.dumps(item["checks"], sort_keys=True) for item in variants
        }
        assert len(fixture_serializations) == 1
        assert len(check_serializations) == 1


def test_generation_is_reproducible() -> None:
    first = generate_cases()
    second = generate_cases()
    assert serialize_jsonl(first) == serialize_jsonl(second)
    assert generated_digest(first) == generated_digest(second)


def test_generated_summary_is_stable_shape() -> None:
    summary = generated_summary()
    assert summary["case_count"] == 3240
    assert summary["blueprint_count"] == 54
    assert summary["service_count"] == 18
    assert summary["surface_count"] == 60
    assert len(summary["sha256"]) == 64
