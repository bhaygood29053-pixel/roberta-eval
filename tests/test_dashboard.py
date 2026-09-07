from roberta_eval.dashboard import build_dashboard, render_markdown
from roberta_eval.stress import run_stress_qualification


def test_fixture_dashboard_preserves_non_live_boundary() -> None:
    view = build_dashboard(qualification=run_stress_qualification(limit=100))
    assert view["qualification"]["live_roberta_qualified"] is False
    assert view["presentation_only"] is True
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


def test_markdown_contains_required_sections() -> None:
    markdown = render_markdown(
        build_dashboard(qualification=run_stress_qualification(limit=50))
    )
    for heading in (
        "## Deterministic quality",
        "## Advisory human quality",
        "## Defect intelligence",
        "## Trend intelligence",
        "## Qualification boundary",
    ):
        assert heading in markdown
