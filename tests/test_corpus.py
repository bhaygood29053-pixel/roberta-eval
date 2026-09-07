import copy

import pytest

from roberta_eval.corpus import (
    corpus_digest,
    corpus_summary,
    load_blueprints,
    materialize_cases,
    serialize_jsonl,
    validate_blueprints,
)


def test_blueprints_cover_all_registered_services() -> None:
    document = load_blueprints()
    validate_blueprints(document)
    assert len({item["service"] for item in document["blueprints"]}) == 18


def test_materialized_corpus_reaches_500_case_target() -> None:
    cases = materialize_cases()
    assert len(cases) == 540
    assert len({case["case_id"] for case in cases}) == 540


def test_first_100_is_stable_subset_of_same_corpus() -> None:
    cases = materialize_cases()
    first_100 = cases[:100]
    assert len(first_100) == 100
    assert all(case["corpus_version"] == "roberta_deterministic_corpus/v1" for case in first_100)


def test_variations_preserve_objective_and_checks() -> None:
    cases = materialize_cases()
    grouped = {}
    for case in cases:
        grouped.setdefault(case["blueprint_id"], []).append(case)

    for variants in grouped.values():
        assert len({item["objective_signature"] for item in variants}) == 1
        assert len({serialize_jsonl([{"checks": item["checks"]}]) for item in variants}) == 1


def test_every_case_keeps_execution_unauthorized() -> None:
    for case in materialize_cases():
        assert any(
            check["kind"] == "execution_authorized" and check["value"] is False
            for check in case["checks"]
        )


def test_generation_is_byte_for_byte_reproducible() -> None:
    first = serialize_jsonl(materialize_cases())
    second = serialize_jsonl(materialize_cases())
    assert first == second
    assert corpus_digest(materialize_cases()) == corpus_digest(materialize_cases())


def test_rejects_blueprint_with_unknown_service() -> None:
    document = load_blueprints()
    document["blueprints"][0]["service"] = "not_a_service"
    with pytest.raises(ValueError, match="unknown service"):
        validate_blueprints(document)


def test_rejects_objective_without_execution_boundary_check() -> None:
    document = load_blueprints()
    document["blueprints"][0]["checks"] = [
        check
        for check in document["blueprints"][0]["checks"]
        if check["kind"] != "execution_authorized"
    ]
    with pytest.raises(ValueError, match="execution boundary"):
        validate_blueprints(document)


def test_summary_reports_expected_scale() -> None:
    summary = corpus_summary()
    assert summary["case_count"] == 540
    assert summary["service_count"] == 18
    assert len(summary["sha256"]) == 64
