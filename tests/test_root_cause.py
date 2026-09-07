import pytest

from roberta_eval.root_cause import localize_finding, localization_summary


def _finding(category="FACTUAL_ERROR", reason="field_check_failed"):
    return {
        "finding_id": "c1:grader:reason",
        "category": category,
        "severity": "HIGH",
        "service": "market_report",
        "reason": reason,
    }


@pytest.mark.parametrize(
    ("snapshot", "expected"),
    [
        ({"provider": "incorrect"}, "provider"),
        ({"provider": "correct", "cmis": "incorrect"}, "cmis"),
        (
            {"provider": "correct", "cmis": "correct", "x1_scout": "incorrect"},
            "x1_scout",
        ),
        (
            {
                "provider": "correct",
                "cmis": "correct",
                "x1_scout": "correct",
                "roberta": "incorrect",
            },
            "roberta",
        ),
    ],
)
def test_layer_snapshot_localizes_first_observed_incorrect_layer(snapshot, expected):
    result = localize_finding(_finding(), snapshot)
    assert result["likely_layer"] == expected
    assert result["confidence"] == 1.0


def test_missing_snapshot_is_unknown_not_guess() -> None:
    result = localize_finding(_finding())
    assert result["likely_layer"] == "unknown"
    assert result["confidence"] == 0.0


def test_inconclusive_snapshot_is_unknown() -> None:
    result = localize_finding(
        _finding(),
        {"provider": "correct", "cmis": "unknown", "x1_scout": "incorrect"},
    )
    assert result["likely_layer"] == "unknown"


def test_evaluation_incomplete_belongs_to_laboratory_not_roberta() -> None:
    result = localize_finding(
        _finding("EVALUATION_INCOMPLETE", "structured_evidence_unavailable")
    )
    assert result["likely_layer"] == "laboratory"
    assert result["confidence"] == 1.0


def test_runtime_error_localizes_transport_conservatively() -> None:
    result = localize_finding(_finding("RUNTIME_ERROR", "runtime_failure"))
    assert result["likely_layer"] == "runtime_transport"


def test_execution_violation_can_localize_to_roberta_response_boundary() -> None:
    result = localize_finding(
        _finding("EXECUTION_BOUNDARY_VIOLATION", "execution_boundary_violated")
    )
    assert result["likely_layer"] == "roberta"
    assert result["confidence"] >= 0.9


def test_invalid_snapshot_state_is_rejected() -> None:
    with pytest.raises(ValueError, match="invalid layer snapshot state"):
        localize_finding(_finding(), {"provider": "probably"})


def test_summary_counts_unknowns() -> None:
    results = [
        localize_finding(_finding()),
        localize_finding(_finding("RUNTIME_ERROR", "runtime_failure")),
    ]
    summary = localization_summary(results)
    assert summary["result_count"] == 2
    assert summary["unknown_count"] == 1
