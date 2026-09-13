from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .human_checkpoint_history import (
    human_checkpoint_history_summary,
    latest_human_checkpoint_report,
    load_human_checkpoint_history,
)

DASHBOARD_VERSION = "roberta_evaluation_dashboard/v1"


def _human_priority(human_trend_report: dict[str, Any] | None) -> dict[str, Any] | None:
    if not human_trend_report:
        return None
    comparison = human_trend_report.get("comparison")
    if not isinstance(comparison, dict):
        return None

    selected: dict[str, Any] | None = None
    recurring = comparison.get("recurring_current_defects")
    if isinstance(recurring, list) and recurring:
        first = recurring[0]
        if isinstance(first, dict):
            selected = {
                "failure_code": first.get("code"),
                "recurrence": "RECURRENT",
                "current_rate": first.get("current_rate"),
                "current_count": first.get("current_count"),
            }

    if selected is None:
        failure_trends = comparison.get("failure_code_trends")
        if isinstance(failure_trends, dict):
            new_defects = [
                {"code": code, **metrics}
                for code, metrics in failure_trends.items()
                if isinstance(metrics, dict)
                and metrics.get("recurrence") == "NEW"
                and int(metrics.get("current_count", 0)) > 0
            ]
            new_defects.sort(
                key=lambda item: (
                    -float(item.get("current_rate", 0.0)),
                    -int(item.get("current_count", 0)),
                    str(item.get("code", "")),
                )
            )
            if new_defects:
                first = new_defects[0]
                selected = {
                    "failure_code": first.get("code"),
                    "recurrence": "NEW",
                    "current_rate": first.get("current_rate"),
                    "current_count": first.get("current_count"),
                }

    if selected is None:
        return None

    worst_services = comparison.get("worst_current_services")
    service = None
    if isinstance(worst_services, list):
        for item in worst_services:
            if isinstance(item, dict) and int(item.get("defect_count", 0)) > 0:
                service = item.get("service")
                break
    selected["service"] = service
    return selected


def _history_fields(history: dict[str, Any] | None) -> dict[str, Any]:
    history = history or {}
    return {
        "accepted_checkpoint_count": int(history.get("checkpoint_count", 0)),
        "latest_checkpoint_id": history.get("latest_checkpoint_id"),
        "previous_checkpoint_id": history.get("previous_checkpoint_id"),
        "checkpoint_comparison_available": bool(history.get("comparison_available", False)),
    }


def _human_section(
    human_trend_report: dict[str, Any] | None,
    human_checkpoint_history: dict[str, Any] | None = None,
) -> dict[str, Any]:
    history_fields = _history_fields(human_checkpoint_history)
    if not human_trend_report:
        return {
            "available": False,
            "source_mode": None,
            **history_fields,
            "advisory_only": True,
            "factual_authority": False,
            "ai_judge_used": False,
            "judge_model_calls": 0,
            "external_calls": 0,
            "zero_judge_tokens": True,
            "execution_authorized": False,
        }

    current = human_trend_report["current"]
    comparison = human_trend_report["comparison"]
    overall = comparison["overall"]
    worst_services = comparison.get("worst_current_services", [])
    recurring = comparison.get("recurring_current_defects", [])
    return {
        "available": True,
        "source_mode": human_trend_report.get("source_mode", "explicit_replay_pair"),
        **history_fields,
        "comparison_checkpoint_ids": {
            "previous": comparison.get("previous_snapshot_id"),
            "current": comparison.get("current_snapshot_id"),
        },
        "current": {
            "result_count": current["result_count"],
            "pass_count": current["pass_count"],
            "defect_count": current["defect_count"],
            "pass_rate": current["pass_rate"],
            "defect_rate": current["defect_rate"],
        },
        "movement": {
            "direction": overall["defect_direction"],
            "defect_rate_delta_pp": overall["defect_rate_delta_pp"],
            "previous_defect_rate": overall["previous_defect_rate"],
            "current_defect_rate": overall["current_defect_rate"],
        },
        "worst_current_services": worst_services[:5],
        "recurring_current_defects": recurring[:5],
        "improved_services": list(comparison.get("improved_services", [])),
        "regressed_services": list(comparison.get("regressed_services", [])),
        "next_priority": _human_priority(human_trend_report),
        "advisory_only": True,
        "factual_authority": False,
        "ai_judge_used": False,
        "judge_model_calls": 0,
        "external_calls": 0,
        "zero_judge_tokens": True,
        "execution_authorized": False,
    }


def build_dashboard(
    *,
    qualification: dict[str, Any],
    quality: dict[str, Any] | None = None,
    clusters: dict[str, Any] | None = None,
    regression_memory: dict[str, Any] | None = None,
    trend_history: dict[str, Any] | None = None,
    trend_comparison: dict[str, Any] | None = None,
    human_trend_report: dict[str, Any] | None = None,
    human_checkpoint_history: dict[str, Any] | None = None,
    human_remediation_lifecycle: dict[str, Any] | None = None,
    human_remediation_action_queue: dict[str, Any] | None = None,
    human_remediation_reopen_adjudication: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if human_checkpoint_history is None:
        accepted_history = load_human_checkpoint_history()
        human_checkpoint_history = human_checkpoint_history_summary(accepted_history)
        if human_trend_report is None:
            human_trend_report = latest_human_checkpoint_report(accepted_history)
        if quality is None and accepted_history["checkpoints"]:
            quality = accepted_history["checkpoints"][-1]["quality"]

    if human_remediation_lifecycle is None:
        from .human_remediation_lifecycle import lifecycle_summary, load_lifecycle

        human_remediation_lifecycle = lifecycle_summary(load_lifecycle())

    if human_remediation_action_queue is None:
        from .human_remediation_actions import load_approval_registry
        from .human_remediation_closure import load_closure_ledger
        from .human_remediation_lifecycle import load_lifecycle
        from .human_remediation_promotion import load_promotion_ledger
        from .human_remediation_terminal import build_terminal_action_queue

        human_remediation_action_queue = build_terminal_action_queue(
            load_lifecycle(),
            load_human_checkpoint_history(),
            load_approval_registry(),
            load_promotion_ledger(),
            load_closure_ledger(),
        )

    if human_remediation_reopen_adjudication is None:
        from .human_remediation_reopen import (
            load_reopen_adjudication_ledger,
            reopen_adjudication_summary,
        )

        human_remediation_reopen_adjudication = reopen_adjudication_summary(
            load_reopen_adjudication_ledger()
        )

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
        "human_v2": _human_section(human_trend_report, human_checkpoint_history),
        "human_remediation_lifecycle": human_remediation_lifecycle,
        "human_remediation_actions": human_remediation_action_queue,
        "human_remediation_reopen_adjudication": human_remediation_reopen_adjudication,
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


def _pct(value: Any) -> str:
    return f"{float(value) * 100.0:.2f}%"


def render_markdown(view: dict[str, Any]) -> str:
    q = view["qualification"]
    d = view["deterministic"]
    a = view["advisory"]
    human = view.get("human_v2", {"available": False})
    lifecycle = view.get("human_remediation_lifecycle", {"record_count": 0})
    actions = view.get("human_remediation_actions", {"record_count": 0, "items": []})
    reopen = view.get(
        "human_remediation_reopen_adjudication",
        {
            "adjudication_count": 0,
            "pending_adjudication_count": 0,
            "administrative_count": 0,
            "confirmed_regression_count": 0,
            "new_cycle_eligible_count": 0,
            "pending": [],
            "adjudications": [],
        },
    )
    defects = view["defects"]
    regressions = view["regressions"]
    trends = view["trends"]
    lines = [
        "# ROBERTA Evaluation Laboratory Dashboard",
        "",
        f"**Dashboard:** {view['dashboard_version']}",
        f"**Qualification scope:** {q['scope']}",
        f"**Accepted:** {'YES' if q['accepted'] else 'NO'}",
        f"Live ROBERTA qualified: {str(q['live_roberta_qualified']).lower()}",
        "",
        "## Deterministic quality",
        "",
        f"- Cases: {d['case_count']}",
        f"- PASS: {d['pass']}",
        f"- WARN: {d['warn']}",
        f"- FAIL: {d['fail']}",
        f"- Services covered: {d['service_count']}",
        f"- Blueprints covered: {d['blueprint_count']}",
        "",
        "## Advisory human quality",
        "",
        f"- Authority: {a['label']}",
        f"- Factual authority: {str(a['factual_authority']).lower()}",
        f"- Average score: {a['average_human_quality'] if a['average_human_quality'] is not None else 'not available'}",
    ]

    if human.get("available"):
        current = human["current"]
        movement = human["movement"]
        ids = human.get("comparison_checkpoint_ids", {})
        lines.extend(
            [
                "",
                "## Human ROBERTA v2 language intelligence",
                "",
                f"- Source: {human.get('source_mode')}",
                f"- Comparison: {ids.get('previous')} → {ids.get('current')}",
                f"- Accepted checkpoints stored: {human.get('accepted_checkpoint_count', 0)}",
                f"- Current records: {current['result_count']}",
                f"- Human PASS rate: {_pct(current['pass_rate'])}",
                f"- Language defect rate: {_pct(current['defect_rate'])}",
                f"- Direction: {movement['direction']}",
                f"- Defect-rate movement: {float(movement['defect_rate_delta_pp']):+.2f} percentage points",
                f"- Judge model calls: {human['judge_model_calls']}",
                f"- External calls: {human['external_calls']}",
                f"- Zero judge tokens: {str(human['zero_judge_tokens']).lower()}",
                "",
                "### Worst current Human-facing services",
                "",
            ]
        )
        worst = human["worst_current_services"]
        if worst:
            for item in worst:
                lines.append(
                    f"- {item['service']}: {_pct(item['defect_rate'])} defects ({item['defect_count']}/{item['result_count']})"
                )
        else:
            lines.append("- none")

        lines.extend(["", "### Recurring Human-language defects", ""])
        recurring = human["recurring_current_defects"]
        if recurring:
            for item in recurring:
                lines.append(
                    f"- `{item['code']}`: {_pct(item['current_rate'])} current rate ({item['current_count']} occurrences)"
                )
        else:
            lines.append("- none")

        lines.extend(["", "### Service movement", ""])
        lines.append("- Improved: " + (", ".join(human["improved_services"]) or "none"))
        lines.append("- Regressed: " + (", ".join(human["regressed_services"]) or "none"))

        priority = human.get("next_priority")
        lines.extend(["", "### Next Human defect to fix", ""])
        if priority:
            service_text = f" in {priority['service']}" if priority.get("service") else ""
            lines.append(
                f"- `{priority['failure_code']}` ({priority['recurrence']}){service_text}: {_pct(priority['current_rate'])} current rate, {priority['current_count']} occurrences."
            )
        else:
            lines.append("- none — no current Human v2 language defect is present in the current accepted/replay corpus.")
    elif int(human.get("accepted_checkpoint_count", 0)) > 0:
        lines.extend(
            [
                "",
                "## Human ROBERTA v2 checkpoint history",
                "",
                f"- Accepted checkpoints stored: {human['accepted_checkpoint_count']}",
                f"- Latest checkpoint: {human.get('latest_checkpoint_id') or 'none'}",
                "- Trend comparison: not enough accepted checkpoints yet; two are required.",
                "- Judge model calls: 0",
                "- External calls: 0",
                "- Zero judge tokens: true",
            ]
        )

    if int(lifecycle.get("record_count", 0)) > 0:
        counts = lifecycle.get("status_counts", {})
        lines.extend(
            [
                "",
                "## Human remediation lifecycle",
                "",
                f"- Tracked remediations: {lifecycle['record_count']}",
                f"- Active: {lifecycle['active_count']}",
                f"- Replay verified: {lifecycle['verified_count']}",
                f"- Improved: {lifecycle['improved_count']}",
                f"- Resolved: {lifecycle['resolved_count']}",
                "- Current stage counts: " + ", ".join(
                    f"{stage}={count}" for stage, count in counts.items() if count
                ),
                "",
                "### Active Human remediations",
                "",
            ]
        )
        active = lifecycle.get("active", [])
        if active:
            for item in active:
                service = f" / {item['service']}" if item.get("service") else ""
                issue = f" / issue #{item['issue_number']}" if item.get("issue_number") else ""
                lines.append(
                    f"- `{item['failure_code']}`{service}: **{item['status']}**{issue}"
                )
        else:
            lines.append("- none")
        lines.extend(
            [
                "",
                "A GitHub issue or merged fix is not treated as resolved. Resolution requires a later accepted Human checkpoint with zero occurrences of the targeted defect.",
            ]
        )

    if int(actions.get("record_count", 0)) > 0:
        lines.extend(
            [
                "",
                "## Human remediation action queue",
                "",
                f"- Tracked remediations: {actions['record_count']}",
                f"- Active remediations: {actions['active_count']}",
                f"- Terminal CLOSED: {actions.get('terminal_closed_count', 0)}",
                f"- Reopened inconsistencies: {actions.get('reopened_inconsistency_count', 0)}",
                f"- Closure-ready issues: {actions['closure_ready_count']}",
                "- Action counts: " + (", ".join(
                    f"{name}={count}"
                    for name, count in actions.get("action_counts", {}).items()
                    if count
                ) or "none"),
                "",
                "### Exact next actions",
                "",
            ]
        )
        active_items = actions.get("items", [])[:10]
        if active_items:
            for item in active_items:
                service = f" / {item['service']}" if item.get("service") else ""
                issue = f" / issue #{item['issue_number']}" if item.get("issue_number") else ""
                ready = " / closure-ready" if item.get("closure_ready") else ""
                lines.append(
                    f"- `{item['failure_code']}`{service}: **{item['next_action_label']}** "
                    f"({item['effective_stage']}){issue}{ready}"
                )
        else:
            lines.append("- none")

        terminal = actions.get("terminal", [])[:10]
        if terminal:
            lines.extend(["", "### Terminal CLOSED remediations", ""])
            for item in terminal:
                service = f" / {item['service']}" if item.get("service") else ""
                consistency = item.get("consistency", "NOT_CHECKED")
                lines.append(
                    f"- `{item['failure_code']}`{service}: **CLOSED** / issue #{item['issue_number']} / {consistency} / resolved checkpoint `{item['resolved_checkpoint_id']}`"
                )

        inconsistencies = actions.get("inconsistencies", [])[:10]
        if inconsistencies:
            lines.extend(["", "### Terminal reconciliation inconsistencies", ""])
            for item in inconsistencies:
                lines.append(
                    f"- issue #{item['issue_number']}: **REOPENED_INCONSISTENCY** — prior CLOSED/RESOLVED evidence is preserved and has not been rewritten."
                )

        lines.extend(
            [
                "",
                "The closure gate is fail-closed: only lifecycle status RESOLVED with a promoted issue identity is closure-ready. IMPROVED, REPLAY_VERIFIED, and FIX_MERGED are never sufficient for closure.",
                "Terminal CLOSED remediations are removed from the active action queue. Reconciliation is read-only: a later reopened GitHub issue is reported as an inconsistency and does not erase the accepted resolution or closure evidence.",
            ]
        )

    if int(reopen.get("adjudication_count", 0)) > 0 or int(reopen.get("pending_adjudication_count", 0)) > 0:
        lines.extend(
            [
                "",
                "## Human remediation reopen adjudication",
                "",
                f"- Pending owner adjudication: {reopen.get('pending_adjudication_count', 0)}",
                f"- Administrative / non-quality: {reopen.get('administrative_count', 0)}",
                f"- Confirmed Human-quality regressions: {reopen.get('confirmed_regression_count', 0)}",
                f"- New-cycle eligible: {reopen.get('new_cycle_eligible_count', 0)}",
            ]
        )
        pending = reopen.get("pending", [])[:10]
        if pending:
            lines.extend(["", "### Pending reopen decisions", ""])
            for item in pending:
                service = f" / {item['service']}" if item.get("service") else ""
                lines.append(
                    f"- `{item['failure_code']}`{service}: issue #{item['issue_number']} requires explicit owner classification."
                )
        rows = reopen.get("adjudications", [])[:10]
        if rows:
            lines.extend(["", "### Reopen decisions", ""])
            for item in rows:
                checkpoint = ""
                if item.get("fresh_regression_evidence"):
                    checkpoint = f" / fresh checkpoint `{item['fresh_regression_evidence']['checkpoint_id']}`"
                cycle = " / new-cycle eligible" if item.get("new_cycle_eligible") else " / terminal CLOSED preserved"
                lines.append(
                    f"- `{item['failure_code']}`: **{item['classification']}** / issue #{item['issue_number']}{checkpoint}{cycle}"
                )
        lines.extend(
            [
                "",
                "A GitHub reopen is not proof of a Human-quality regression. Genuine regression classification requires a newer explicitly accepted checkpoint that shows the same targeted defect has returned; administrative reopens preserve the prior terminal CLOSED evidence and cannot start a new remediation cycle.",
            ]
        )

    lines.extend(
        [
            "",
            "## Defect intelligence",
            "",
            f"- Failure clusters: {defects['cluster_count']}",
            f"- Actionable product clusters: {defects['actionable_product_cluster_count']}",
            f"- Active permanent regressions: {regressions['active_count']}",
            "",
            "## Trend intelligence",
            "",
            f"- Stored snapshots: {trends['snapshot_count']}",
            f"- Current deterministic direction: {trends['current_direction'] or 'not enough history'}",
            "",
            "## Qualification boundary",
            "",
            str(q["boundary"]),
            "",
            "The dashboard is presentation-only. It does not create evidence, override deterministic grading, convert fixture-pipeline results into live ROBERTA proof, promote Human defects automatically, mark a merged fix resolved without replay proof, close or reopen remediation issues automatically, adjudicate a reopened issue automatically, create a new remediation cycle automatically, rewrite terminal closure evidence, or authorize execution.",
            "",
        ]
    )
    return "\n".join(lines)


def write_dashboard_json(path: Path, view: dict[str, Any]) -> None:
    path.write_text(json.dumps(view, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_dashboard_markdown(path: Path, view: dict[str, Any]) -> None:
    path.write_text(render_markdown(view), encoding="utf-8")