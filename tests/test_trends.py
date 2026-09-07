import pytest

from roberta_eval.trends import (
    append_snapshot,
    build_snapshot,
    compare_snapshots,
    history_summary,
    load_history,
    validate_history,
)


def _grade(pass_count, warn_count, fail_count):
    total = pass_count + warn_count + fail_count
    return {
        "result_count": total,
        "verdict_counts": {"PASS": pass_count, "WARN": warn_count, "FAIL": fail_count},
    }


def test_repository_history_is_valid() -> None:
    history = load_history()
    validate_history(history)
    assert history_summary(history)["snapshot_count"] == 0


def test_snapshot_uses_normalized_rates() -> None:
    a = build_snapshot(snapshot_id="a", scope="fixture_pipeline", grade_summary=_grade(90, 5, 5))
    b = build_snapshot(snapshot_id="b", scope="fixture_pipeline", grade_summary=_grade(900, 50, 50))
    assert a["deterministic"]["pass_rate"] == b["deterministic"]["pass_rate"] == 0.9


def test_compare_detects_deterministic_improvement() -> None:
    prev = build_snapshot(snapshot_id="a", scope="live_roberta", grade_summary=_grade(80, 10, 10))
    cur = build_snapshot(snapshot_id="b", scope="live_roberta", grade_summary=_grade(90, 5, 5))
    result = compare_snapshots(prev, cur)
    assert result["metrics"]["pass_rate"]["direction"] == "IMPROVED"
    assert result["metrics"]["fail_rate"]["direction"] == "IMPROVED"
    assert result["overall_deterministic_direction"] == "IMPROVED"


def test_compare_detects_regression_even_if_advisory_improves() -> None:
    prev = build_snapshot(
        snapshot_id="a",
        scope="live_roberta",
        grade_summary=_grade(95, 3, 2),
        quality_summary={"average_overall_score": 70},
    )
    cur = build_snapshot(
        snapshot_id="b",
        scope="live_roberta",
        grade_summary=_grade(90, 5, 5),
        quality_summary={"average_overall_score": 90},
    )
    result = compare_snapshots(prev, cur)
    assert result["overall_deterministic_direction"] == "REGRESSED"
    assert result["metrics"]["human_quality_average"]["direction"] == "IMPROVED"
    assert result["metrics"]["human_quality_average"]["authority"] == "advisory_only"


def test_incompatible_scopes_are_rejected() -> None:
    a = build_snapshot(snapshot_id="a", scope="fixture_pipeline", grade_summary=_grade(10, 0, 0))
    b = build_snapshot(snapshot_id="b", scope="live_roberta", grade_summary=_grade(10, 0, 0))
    with pytest.raises(ValueError, match="same scope"):
        compare_snapshots(a, b)


def test_history_append_is_idempotent() -> None:
    history = load_history()
    snap = build_snapshot(snapshot_id="a", scope="fixture_pipeline", grade_summary=_grade(10, 0, 0))
    history = append_snapshot(history, snap)
    history = append_snapshot(history, snap)
    assert len(history["snapshots"]) == 1
