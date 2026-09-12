from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .grader import load_run_jsonl
from .human_language import grade_human_language_records, human_language_summary

HUMAN_TREND_VERSION = "roberta_human_language_trend/v1"


def _rate(count: int, total: int) -> float:
    return round(count / total, 6) if total else 0.0


def _delta_pp(previous: float, current: float) -> float:
    return round((current - previous) * 100.0, 2)


def _direction(delta_pp: float, *, lower_is_better: bool = True) -> str:
    if abs(delta_pp) < 0.005:
        return "STABLE"
    improved = delta_pp < 0 if lower_is_better else delta_pp > 0
    return "IMPROVED" if improved else "REGRESSED"


def _verdict_metrics(bucket: dict[str, Any]) -> dict[str, Any]:
    passed = int(bucket.get("PASS", 0))
    defects = int(bucket.get("LANGUAGE_DEFECT", 0))
    total = passed + defects
    return {
        "result_count": total,
        "pass_count": passed,
        "defect_count": defects,
        "pass_rate": _rate(passed, total),
        "defect_rate": _rate(defects, total),
    }


def build_human_trend_snapshot(
    records: list[dict[str, Any]],
    *,
    snapshot_id: str,
    source: str,
) -> dict[str, Any]:
    results = grade_human_language_records(records)
    summary = human_language_summary(results)
    total = int(summary["result_count"])
    verdicts = summary["verdict_counts"]

    by_service = {
        service: _verdict_metrics(bucket)
        for service, bucket in summary.get("by_service", {}).items()
    }
    by_depth = {
        depth: _verdict_metrics(bucket)
        for depth, bucket in summary.get("by_response_depth", {}).items()
    }
    failure_codes = {
        code: {
            "count": int(count),
            "rate": _rate(int(count), total),
        }
        for code, count in summary.get("failure_code_counts", {}).items()
    }

    snapshot = {
        "human_trend_version": HUMAN_TREND_VERSION,
        "snapshot_id": snapshot_id,
        "source": source,
        "result_count": total,
        "pass_count": int(verdicts.get("PASS", 0)),
        "defect_count": int(verdicts.get("LANGUAGE_DEFECT", 0)),
        "pass_rate": _rate(int(verdicts.get("PASS", 0)), total),
        "defect_rate": _rate(int(verdicts.get("LANGUAGE_DEFECT", 0)), total),
        "by_service": dict(sorted(by_service.items())),
        "by_response_depth": dict(sorted(by_depth.items())),
        "failure_codes": dict(sorted(failure_codes.items())),
        "source_file_count": int(summary.get("source_file_count", 0)),
        "unique_response_count": int(summary.get("unique_response_count", 0)),
        "duplicate_response_record_count": int(
            summary.get("duplicate_response_record_count", 0)
        ),
        "deterministic": True,
        "advisory_only": True,
        "factual_authority": False,
        "ai_judge_used": False,
        "judge_model_calls": 0,
        "external_calls": 0,
        "zero_judge_tokens": True,
        "execution_authorized": False,
    }
    validate_human_trend_snapshot(snapshot)
    return snapshot


def validate_human_trend_snapshot(snapshot: dict[str, Any]) -> None:
    if snapshot.get("human_trend_version") != HUMAN_TREND_VERSION:
        raise ValueError("unsupported Human trend snapshot version")
    if not snapshot.get("snapshot_id"):
        raise ValueError("Human trend snapshot_id is required")
    total = snapshot.get("result_count")
    if not isinstance(total, int) or total < 0:
        raise ValueError("Human trend result_count must be a non-negative integer")
    for key in ("pass_rate", "defect_rate"):
        value = snapshot.get(key)
        if not isinstance(value, (int, float)) or value < 0 or value > 1:
            raise ValueError(f"{key}: invalid normalized rate")
    if total and round(float(snapshot["pass_rate"]) + float(snapshot["defect_rate"]), 5) != 1.0:
        raise ValueError("Human pass/defect rates must sum to 1")
    if snapshot.get("ai_judge_used") is not False:
        raise ValueError("Human trend engine must not use an AI judge")
    if snapshot.get("judge_model_calls") != 0 or snapshot.get("external_calls") != 0:
        raise ValueError("Human trend engine must remain zero-call")


def _compare_group(
    previous: dict[str, Any],
    current: dict[str, Any],
) -> dict[str, Any]:
    previous_rate = float(previous.get("defect_rate", 0.0))
    current_rate = float(current.get("defect_rate", 0.0))
    delta = _delta_pp(previous_rate, current_rate)
    return {
        "previous_result_count": int(previous.get("result_count", 0)),
        "current_result_count": int(current.get("result_count", 0)),
        "previous_defect_count": int(previous.get("defect_count", 0)),
        "current_defect_count": int(current.get("defect_count", 0)),
        "previous_defect_rate": previous_rate,
        "current_defect_rate": current_rate,
        "defect_rate_delta_pp": delta,
        "direction": _direction(delta, lower_is_better=True),
    }


def _group_trends(
    previous_groups: dict[str, dict[str, Any]],
    current_groups: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for name in sorted(set(previous_groups) | set(current_groups)):
        previous = previous_groups.get(name)
        current = current_groups.get(name)
        if previous is None:
            metrics = dict(current or {})
            output[name] = {
                "coverage": "NEW_CURRENT_COVERAGE",
                "previous_result_count": 0,
                "current_result_count": int(metrics.get("result_count", 0)),
                "previous_defect_rate": None,
                "current_defect_rate": float(metrics.get("defect_rate", 0.0)),
                "defect_rate_delta_pp": None,
                "direction": "NOT_COMPARABLE",
            }
        elif current is None:
            output[name] = {
                "coverage": "MISSING_CURRENT_COVERAGE",
                "previous_result_count": int(previous.get("result_count", 0)),
                "current_result_count": 0,
                "previous_defect_rate": float(previous.get("defect_rate", 0.0)),
                "current_defect_rate": None,
                "defect_rate_delta_pp": None,
                "direction": "NOT_COMPARABLE",
            }
        else:
            output[name] = {"coverage": "COMPARABLE", **_compare_group(previous, current)}
    return output


def _failure_code_trends(
    previous: dict[str, dict[str, Any]],
    current: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for code in sorted(set(previous) | set(current)):
        before = previous.get(code, {"count": 0, "rate": 0.0})
        after = current.get(code, {"count": 0, "rate": 0.0})
        previous_count = int(before.get("count", 0))
        current_count = int(after.get("count", 0))
        previous_rate = float(before.get("rate", 0.0))
        current_rate = float(after.get("rate", 0.0))
        delta = _delta_pp(previous_rate, current_rate)
        if previous_count and current_count:
            recurrence = "RECURRENT"
        elif current_count:
            recurrence = "NEW"
        else:
            recurrence = "RESOLVED"
        output[code] = {
            "previous_count": previous_count,
            "current_count": current_count,
            "previous_rate": previous_rate,
            "current_rate": current_rate,
            "rate_delta_pp": delta,
            "direction": _direction(delta, lower_is_better=True),
            "recurrence": recurrence,
        }
    return output


def compare_human_trend_snapshots(
    previous: dict[str, Any],
    current: dict[str, Any],
) -> dict[str, Any]:
    validate_human_trend_snapshot(previous)
    validate_human_trend_snapshot(current)

    defect_delta = _delta_pp(float(previous["defect_rate"]), float(current["defect_rate"]))
    pass_delta = _delta_pp(float(previous["pass_rate"]), float(current["pass_rate"]))
    service_trends = _group_trends(previous["by_service"], current["by_service"])
    depth_trends = _group_trends(previous["by_response_depth"], current["by_response_depth"])
    failure_trends = _failure_code_trends(previous["failure_codes"], current["failure_codes"])

    worst_current_services = sorted(
        (
            {
                "service": service,
                **metrics,
            }
            for service, metrics in current["by_service"].items()
            if int(metrics.get("result_count", 0)) > 0
        ),
        key=lambda item: (
            -float(item.get("defect_rate", 0.0)),
            -int(item.get("defect_count", 0)),
            str(item.get("service", "")),
        ),
    )

    recurring_defects = sorted(
        (
            {"code": code, **metrics}
            for code, metrics in failure_trends.items()
            if metrics["recurrence"] == "RECURRENT"
        ),
        key=lambda item: (
            -float(item["current_rate"]),
            -int(item["current_count"]),
            str(item["code"]),
        ),
    )

    improved_services = [
        service
        for service, metrics in service_trends.items()
        if metrics["direction"] == "IMPROVED"
    ]
    regressed_services = [
        service
        for service, metrics in service_trends.items()
        if metrics["direction"] == "REGRESSED"
    ]

    return {
        "human_trend_comparison_version": "roberta_human_language_trend_comparison/v1",
        "previous_snapshot_id": previous["snapshot_id"],
        "current_snapshot_id": current["snapshot_id"],
        "overall": {
            "previous_result_count": previous["result_count"],
            "current_result_count": current["result_count"],
            "previous_defect_rate": previous["defect_rate"],
            "current_defect_rate": current["defect_rate"],
            "defect_rate_delta_pp": defect_delta,
            "defect_direction": _direction(defect_delta, lower_is_better=True),
            "previous_pass_rate": previous["pass_rate"],
            "current_pass_rate": current["pass_rate"],
            "pass_rate_delta_pp": pass_delta,
            "pass_direction": _direction(pass_delta, lower_is_better=False),
        },
        "service_trends": service_trends,
        "response_depth_trends": depth_trends,
        "failure_code_trends": failure_trends,
        "worst_current_services": worst_current_services,
        "recurring_current_defects": recurring_defects,
        "improved_services": improved_services,
        "regressed_services": regressed_services,
        "deterministic": True,
        "advisory_only": True,
        "factual_authority": False,
        "ai_judge_used": False,
        "judge_model_calls": 0,
        "external_calls": 0,
        "zero_judge_tokens": True,
        "execution_authorized": False,
    }


def build_human_trend_report(
    previous_path: Path,
    current_path: Path,
    *,
    previous_id: str = "previous",
    current_id: str = "current",
) -> dict[str, Any]:
    previous_records = load_run_jsonl(previous_path)
    current_records = load_run_jsonl(current_path)
    previous = build_human_trend_snapshot(
        previous_records,
        snapshot_id=previous_id,
        source=str(previous_path),
    )
    current = build_human_trend_snapshot(
        current_records,
        snapshot_id=current_id,
        source=str(current_path),
    )
    return {
        "human_trend_report_version": "roberta_human_language_trend_report/v1",
        "previous": previous,
        "current": current,
        "comparison": compare_human_trend_snapshots(previous, current),
    }


def render_human_trend_markdown(report: dict[str, Any]) -> str:
    comparison = report["comparison"]
    overall = comparison["overall"]
    previous_pct = float(overall["previous_defect_rate"]) * 100.0
    current_pct = float(overall["current_defect_rate"]) * 100.0
    delta = float(overall["defect_rate_delta_pp"])

    lines = [
        "# Human ROBERTA v2 defect trend",
        "",
        f"Overall: **{overall['defect_direction']}** — language defects {previous_pct:.2f}% → {current_pct:.2f}% ({delta:+.2f} percentage points).",
        "",
        f"Previous records: {overall['previous_result_count']}  ",
        f"Current records: {overall['current_result_count']}  ",
        "Judge model calls: **0**  ",
        "External calls: **0**",
        "",
        "## Worst current services",
        "",
        "| Service | Defect rate | Defects | Records |",
        "| --- | ---: | ---: | ---: |",
    ]
    for item in comparison["worst_current_services"]:
        lines.append(
            f"| {item['service']} | {float(item['defect_rate']) * 100.0:.2f}% | {item['defect_count']} | {item['result_count']} |"
        )
    if not comparison["worst_current_services"]:
        lines.append("| — | 0.00% | 0 | 0 |")

    lines.extend(["", "## Recurring defects", "", "| Defect | Previous | Current | Delta |", "| --- | ---: | ---: | ---: |"])
    for item in comparison["recurring_current_defects"]:
        lines.append(
            f"| `{item['code']}` | {float(item['previous_rate']) * 100.0:.2f}% | {float(item['current_rate']) * 100.0:.2f}% | {float(item['rate_delta_pp']):+.2f} pp |"
        )
    if not comparison["recurring_current_defects"]:
        lines.append("| — | 0.00% | 0.00% | +0.00 pp |")

    lines.extend(["", "## Service movement", ""])
    lines.append(
        "Improved: " + (", ".join(comparison["improved_services"]) or "none")
    )
    lines.append(
        "Regressed: " + (", ".join(comparison["regressed_services"]) or "none")
    )
    lines.extend(
        [
            "",
            "This report is deterministic and advisory-only. It does not rewrite ROBERTA responses, change factual evidence, promote defects automatically, or authorize execution.",
            "",
        ]
    )
    return "\n".join(lines)


def write_human_trend_json(path: Path, report: dict[str, Any]) -> None:
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_human_trend_markdown(path: Path, report: dict[str, Any]) -> None:
    path.write_text(render_human_trend_markdown(report), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(prog="roberta-human-trends")
    parser.add_argument("--previous", required=True, help="previous saved run JSONL file or directory")
    parser.add_argument("--current", required=True, help="current saved run JSONL file or directory")
    parser.add_argument("--previous-id", default="previous")
    parser.add_argument("--current-id", default="current")
    parser.add_argument("--json", dest="json_output", default=None)
    parser.add_argument("--markdown", dest="markdown_output", default=None)
    args = parser.parse_args()

    report = build_human_trend_report(
        Path(args.previous),
        Path(args.current),
        previous_id=args.previous_id,
        current_id=args.current_id,
    )
    if args.json_output:
        write_human_trend_json(Path(args.json_output), report)
    if args.markdown_output:
        write_human_trend_markdown(Path(args.markdown_output), report)
    print(json.dumps(report["comparison"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
