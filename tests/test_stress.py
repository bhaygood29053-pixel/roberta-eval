from roberta_eval.generator import generate_cases
from roberta_eval.stress import (
    DEFAULT_STRESS_LIMIT,
    render_stress_markdown,
    run_stress_qualification,
    select_stress_cases,
)


def test_stress_selection_is_2500_and_covers_all_services() -> None:
    selected = select_stress_cases(generate_cases(), limit=DEFAULT_STRESS_LIMIT)
    assert len(selected) == 2500
    assert len({case["case_id"] for case in selected}) == 2500
    assert len({case["service"] for case in selected}) == 18


def test_full_fixture_stress_qualification_passes() -> None:
    report = run_stress_qualification()
    assert report["selected_case_count"] == 2500
    assert report["coverage"]["service_count"] == 18
    assert report["runtime"]["record_count"] == 2500
    assert report["grading"]["result_count"] == 2500
    assert report["grading"]["verdict_counts"] == {
        "PASS": 2500,
        "WARN": 0,
        "FAIL": 0,
    }
    assert report["accepted"] is True
    assert report["live_roberta_qualified"] is False


def test_stress_report_states_fixture_boundary() -> None:
    report = run_stress_qualification(limit=100)
    markdown = render_stress_markdown(report)
    assert "does not prove" in report["boundary"]
    assert "Live ROBERTA qualified: false" in markdown
    assert "separate live-eligible suite" in markdown


def test_stress_selection_is_reproducible() -> None:
    first = select_stress_cases(generate_cases(), limit=2500)
    second = select_stress_cases(generate_cases(), limit=2500)
    assert [case["case_id"] for case in first] == [case["case_id"] for case in second]
