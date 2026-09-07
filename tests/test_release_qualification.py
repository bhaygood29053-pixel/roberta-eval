from copy import deepcopy

from roberta_eval.release_qualification import load_policy, qualify_release, validate_policy
from roberta_eval.stress import run_stress_qualification


def test_policy_keeps_advisory_non_blocking() -> None:
    policy = load_policy()
    validate_policy(policy)
    assert policy["advisory"]["blocking"] is False


def test_green_fixture_baseline_qualifies() -> None:
    result = qualify_release(
        requested_scope="fixture_pipeline",
        qualification_report=run_stress_qualification(limit=100),
    )
    assert result["status"] == "QUALIFIED"
    assert result["release_qualified"] is True


def test_live_scope_requires_live_evidence() -> None:
    result = qualify_release(
        requested_scope="live_roberta",
        qualification_report=run_stress_qualification(limit=100),
    )
    assert result["status"] == "EVIDENCE_REQUIRED"
    assert result["release_qualified"] is False


def test_deterministic_failure_blocks_despite_high_advisory_score() -> None:
    report = run_stress_qualification(limit=100)
    report = deepcopy(report)
    report["grading"]["verdict_counts"]["PASS"] = 99
    report["grading"]["verdict_counts"]["FAIL"] = 1
    result = qualify_release(
        requested_scope="fixture_pipeline",
        qualification_report=report,
        quality_summary={"average_overall_score": 100},
    )
    assert result["status"] == "BLOCKED"
    assert result["advisory"]["human_quality_average"] == 100


def test_low_human_quality_warns_but_does_not_block() -> None:
    result = qualify_release(
        requested_scope="fixture_pipeline",
        qualification_report=run_stress_qualification(limit=100),
        quality_summary={"average_overall_score": 50},
    )
    assert result["status"] == "QUALIFIED_WITH_ADVISORY_WARNINGS"
    assert result["release_qualified"] is True
    assert result["advisory_warnings"][0]["authority"] == "advisory_only"


def test_regression_replay_failure_blocks() -> None:
    result = qualify_release(
        requested_scope="fixture_pipeline",
        qualification_report=run_stress_qualification(limit=100),
        regression_replay_summary={"fail_count": 1},
    )
    assert result["status"] == "BLOCKED"


def test_deterministic_regression_blocks() -> None:
    result = qualify_release(
        requested_scope="fixture_pipeline",
        qualification_report=run_stress_qualification(limit=100),
        trend_comparison={"overall_deterministic_direction": "REGRESSED"},
    )
    assert result["status"] == "BLOCKED"
