from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DASHBOARD_VERSION = "roberta_evaluation_dashboard/v1"


def build_dashboard(
    *,
    qualification: dict[str, Any],
    quality: dict[str, Any] | None = None,
    clusters: dict[str, Any] | None = None,
    regression_memory: dict[str, Any] | None = None,
    trend_history: dict[str, Any] | None = None,
    trend_comparison: dict[str, Any] | None = None,
) -> dict[str, Any]:
    verdicts = qualification["grading"]["verdict_counts"]
    coverage = qualification["coverage"]
    return {
        "dashboard_version": DASHBOARD_VERSION,
        "presentation_only": True,
        "qualification": {
            "scope": qualification["qualification_scope"],
            "accepted": bool(qualification["accepted"]),
            "live_roberta_qualified": bool(qualification["live_roberta_qualified"]),
            "boundary": qualification["boundary"],
        },
        "deterministic": {
            "case_count": qualification["selected_case_count"],
            "pass": verdicts["PASS"],
            "warn": verdicts["WARN"],
            "fail": verdicts["FAIL"],
            "service_count": coverage["service_count"],
            "blueprint_count": coverage["blueprint_count"],
        },
        "advisory": {
            "label": "advisory_only",
            "factual_authority": False,
            "average_human_quality": (
                quality.get("average_overall_score") if quality else None
            ),
        },
        "defects": {
            "cluster_count": int((clusters or {}).get("cluster_count", 0)),
            "actionable_product_cluster_count": int(
                (clusters or {}).get("actionable_product_cluster_count", 0)
            ),
        },
        "regressions": {
            "active_count": int(
                (regression_memory or {}).get("active_regression_count", 0)
            ),
        },
        "trends": {
            "snapshot_count": int((trend_history or {}).get("snapshot_count", 0)),
            "current_direction": (
                trend_comparison.get("overall_deterministic_direction")
                if trend_comparison
                else None
            ),
        },
    }


def render_markdown(view: dict[str, Any]) -> str:
    q = view["qualification"]
    d = view["deterministic"]
    a = view["advisory"]
    defects = view["defects"]
    regressions = view["regressions"]
    trends = view["trends"]
    return f"""# ROBERTA Evaluation Laboratory Dashboard

**Dashboard:** {view['dashboard_version']}
**Qualification scope:** {q['scope']}
**Accepted:** {'YES' if q['accepted'] else 'NO'}
Live ROBERTA qualified: {str(q['live_roberta_qualified']).lower()}

## Deterministic quality

- Cases: {d['case_count']}
- PASS: {d['pass']}
- WARN: {d['warn']}
- FAIL: {d['fail']}
- Services covered: {d['service_count']}
- Blueprints covered: {d['blueprint_count']}

## Advisory human quality

- Authority: {a['label']}
- Factual authority: {str(a['factual_authority']).lower()}
- Average score: {a['average_human_quality'] if a['average_human_quality'] is not None else 'not available'}

## Defect intelligence

- Failure clusters: {defects['cluster_count']}
- Actionable product clusters: {defects['actionable_product_cluster_count']}
- Active permanent regressions: {regressions['active_count']}

## Trend intelligence

- Stored snapshots: {trends['snapshot_count']}
- Current deterministic direction: {trends['current_direction'] or 'not enough history'}

## Qualification boundary

{q['boundary']}

The dashboard is presentation-only. It does not create evidence, override
deterministic grading, or convert fixture-pipeline results into live ROBERTA proof.
"""


def write_dashboard_json(path: Path, view: dict[str, Any]) -> None:
    path.write_text(json.dumps(view, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_dashboard_markdown(path: Path, view: dict[str, Any]) -> None:
    path.write_text(render_markdown(view), encoding="utf-8")
