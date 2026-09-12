import pytest

from roberta_eval.cli import dashboard_suite
from roberta_eval.dashboard import build_dashboard, render_markdown
from roberta_eval.human_trends import (
    build_human_trend_snapshot,
    compare_human_trend_snapshots,
)
from roberta_eval.stress import run_stress_qualification


def _record(record_id: str, service: str, reply: str) -> dict:
    return {
        "record_version": "roberta_eval_run_record/v1",
        "record_id": record_id,
        "case_id": record_id,
        "service": service,
        "runtime_status": "ok",
        "response": {"reply": reply, "response_depth": "normal"},
    }


def _human_report() -> dict:
    previous_records = [
        _record("p1", "pre_trade", "CMIS deterministic risk result says wait."),
        _record("p2", "wallet_relationship", "I would wait until I can verify the relationship."),
        _record("p3", "pre_trade", "Risk: UNKNOWN\nI would wait."),
        _record("p4", "bridge", "I can verify the asset path, but I would still watch the liquidity."),
    ]
    current_records = [
        _record("c1", "pre_trade", "CMIS deterministic risk result says wait."),
        _record("c2", "pre_trade", "I would wait until I can verify slippage and price impact."),
        _record("c3", "wallet_relationship", "I can confirm the observed transfer, but not common ownership."),
        _record("c4", "bridge", "I can verify the asset path, but I would still watch the liquidity."),
        _record("c5", "pre_trade", "I would wait until I can verify route quality."),
        _record("c6", "pre_trade", "I would wait until I can verify the likely fill."),
    ]
    previous = build_human_trend_snapshot(previous_records, snapshot_id="before", source="before")
    current = build_human_trend_snapshot(current_records, snapshot_id="after", source="after")
    return {
        "human_trend_report_version": "roberta_human_language_trend_report/v1",
        "previous": previous,
        "current": current,
        "comparison": compare_human_trend_snapshots(previous, current),
    }


def test_fixture_dashboard_preserves_non_live_boundary() -> None:
    view = build_dashboard(qualification=run_stress_qualification(limit=100))
    assert view["qualification"]["live_roberta_qualified"] is False
    assert view["presentation_only"] is True
    assert view["human_v2"]["available"] is False
    markdown = render_markdown(view)
    assert "Live ROBERTA qualified: false" in markdown
    assert "fixture-pipeline results into live ROBERTA proof" in markdown


def test_advisory_quality_is_separate_and_non_authoritative() -> None:
    view = build_dashboard(
        qualification=run_stress_qualification(limit=100),
        quality={"average_overall_score": 88.5},
    )
    assert view["advisory"]["average_human_quality"] == 88.5
    assert view["advisory"]["factual_authority"] is False
    assert view["advisory"]["label"] == "advisory_only"


def test_dashboard_reflects_source_counts_without_reinterpreting() -> None:
    report = run_stress_qualification(limit=100)
    view = build_dashboard(
        qualification=report,
        clusters={"cluster_count": 7, "actionable_product_cluster_count": 3},
        regression_memory={"active_regression_count": 2},
        trend_history={"snapshot_count": 4},
        trend_comparison={"overall_deterministic_direction": "IMPROVED"},
    )
    assert view["deterministic"]["pass"] == report["grading"]["verdict_counts"]["PASS"]
    assert view["defects"]["cluster_count"] == 7
    assert view["regressions"]["active_count"] == 2
    assert view["trends"]["current_direction"] == "IMPROVED"


def test_human_trend_panel_surfaces_current_state_and_priority() -> None:
    view = build_dashboard(
        qualification=run_stress_qualification(limit=100),
        human_trend_report=_human_report(),
    )
    human = view["human_v2"]
    assert human["available"] is True
    assert human["current"]["result_count"] == 6
    assert human["movement"]["direction"] == "IMPROVED"
    assert human["worst_current_services"][0]["service"] == "pre_trade"
    assert human["next_priority"]["failure_code"] == "technical_language_leak"
    assert human["next_priority"]["recurrence"] == "RECURRENT"
    assert human["next_priority"]["service"] == "pre_trade"
    assert human["judge_model_calls"] == 0
    assert human["external_calls"] == 0
    assert human["zero_judge_tokens"] is True

    markdown = render_markdown(view)
    assert "## Human ROBERTA v2 language intelligence" in markdown
    assert "### Worst current Human-facing services" in markdown
    assert "### Recurring Human-language defects" in markdown
    assert "### Next Human defect to fix" in markdown
    assert "`technical_language_leak`" in markdown


def test_human_priority_is_none_when_current_corpus_has_no_defects() -> None:
    previous = build_human_trend_snapshot(
        [_record("p1", "pre_trade", "CMIS deterministic risk result says wait.")],
        snapshot_id="before",
        source="before",
    )
    current = build_human_trend_snapshot(
        [_record("c1", "pre_trade", "I would wait until I can verify the likely fill.")],
        snapshot_id="after",
        source="after",
    )
    report = {
        "human_trend_report_version": "roberta_human_language_trend_report/v1",
        "previous": previous,
        "current": current,
        "comparison": compare_human_trend_snapshots(previous, current),
    }
    view = build_dashboard(
        qualification=run_stress_qualification(limit=50),
        human_trend_report=report,
    )
    assert view["human_v2"]["next_priority"] is None


def test_dashboard_requires_paired_human_replay_inputs() -> None:
    with pytest.raises(ValueError, match="must be supplied together"):
        dashboard_suite(None, None, human_previous="/tmp/before", human_current=None)


def test_markdown_contains_required_sections() -> None:
    markdown = render_markdown(build_dashboard(qualification=run_stress_qualification(limit=50)))
    for heading in (
        "## Deterministic quality",
        "## Advisory human quality",
        "## Defect intelligence",
        "## Trend intelligence",
        "## Qualification boundary",
    ):
        assert heading in markdown
