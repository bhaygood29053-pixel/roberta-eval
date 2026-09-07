import json

from roberta_eval.scale import (
    generate_scale_cases,
    load_scale_surfaces,
    run_scale_qualification,
    scale_summary,
    select_scale_cases,
    validate_scale_surfaces,
)


def test_scale_surface_matrix_is_500_forms() -> None:
    surfaces = load_scale_surfaces()
    validate_scale_surfaces(surfaces)
    assert len(surfaces["prefixes"]) * len(surfaces["suffixes"]) * len(surfaces["closers"]) == 500


def test_scale_suite_generates_27000_unique_cases() -> None:
    cases = generate_scale_cases()
    summary = scale_summary(cases)
    assert summary["case_count"] == 27000
    assert summary["blueprint_count"] == 54
    assert summary["surface_count"] == 500
    assert summary["service_count"] == 18
    assert len({case["case_id"] for case in cases}) == 27000


def test_10k_and_25k_selections_cover_all_services() -> None:
    cases = generate_scale_cases()
    for limit in (10000, 25000):
        selected = select_scale_cases(cases, limit=limit)
        assert len(selected) == limit
        assert len({case["service"] for case in selected}) == 18


def test_variants_preserve_fixture_objective_and_checks_for_sample_blueprint() -> None:
    variants = [
        case for case in generate_scale_cases()
        if case["blueprint_id"] == "market_report.verified_market"
    ]
    assert len(variants) == 500
    assert len({case["objective_signature"] for case in variants}) == 1
    assert len({json.dumps(case["fixture"], sort_keys=True) for case in variants}) == 1
    assert len({json.dumps(case["checks"], sort_keys=True) for case in variants}) == 1


def test_scale_qualification_smoke_passes_and_is_non_live() -> None:
    report = run_scale_qualification(limit=1000)
    assert report["accepted"] is True
    assert report["grading"]["verdict_counts"] == {"PASS": 1000, "WARN": 0, "FAIL": 0}
    assert report["live_roberta_qualified"] is False
    assert "not a live ROBERTA quality claim" in report["boundary"]
