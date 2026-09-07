from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

TREND_VERSION = "roberta_trend_snapshot/v1"
HISTORY_VERSION = "roberta_trend_history/v1"


def history_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "trend_history.json"


def load_history(path: Path | None = None) -> dict[str, Any]:
    source = path or history_path()
    return json.loads(source.read_text(encoding="utf-8"))


def _rate(count: int, total: int) -> float:
    return round(count / total, 6) if total else 0.0


def build_snapshot(
    *,
    snapshot_id: str,
    scope: str,
    grade_summary: dict[str, Any],
    quality_summary: dict[str, Any] | None = None,
    cluster_summary: dict[str, Any] | None = None,
    critical_finding_count: int = 0,
    subject_version: str | None = None,
) -> dict[str, Any]:
    verdicts = grade_summary["verdict_counts"]
    total = int(grade_summary["result_count"])
    snapshot = {
        "trend_version": TREND_VERSION,
        "snapshot_id": snapshot_id,
        "scope": scope,
        "subject_version": subject_version,
        "deterministic": {
            "result_count": total,
            "pass_rate": _rate(int(verdicts["PASS"]), total),
            "warn_rate": _rate(int(verdicts["WARN"]), total),
            "fail_rate": _rate(int(verdicts["FAIL"]), total),
            "critical_finding_count": int(critical_finding_count),
        },
        "advisory": {
            "human_quality_average": (
                float(quality_summary["average_overall_score"])
                if quality_summary is not None
                else None
            ),
            "factual_authority": False,
        },
        "defects": {
            "cluster_count": int((cluster_summary or {}).get("cluster_count", 0)),
            "actionable_product_cluster_count": int(
                (cluster_summary or {}).get("actionable_product_cluster_count", 0)
            ),
        },
        "live_roberta_quality_claim": scope == "live_roberta",
    }
    validate_snapshot(snapshot)
    return snapshot


def validate_snapshot(snapshot: dict[str, Any]) -> None:
    if snapshot.get("trend_version") != TREND_VERSION:
        raise ValueError("unsupported trend snapshot version")
    if not snapshot.get("snapshot_id") or not snapshot.get("scope"):
        raise ValueError("trend snapshot identity is incomplete")
    deterministic = snapshot.get("deterministic")
    if not isinstance(deterministic, dict):
        raise ValueError("deterministic trend metrics are required")
    for key in ("pass_rate", "warn_rate", "fail_rate"):
        value = deterministic.get(key)
        if not isinstance(value, (int, float)) or value < 0 or value > 1:
            raise ValueError(f"{key}: invalid normalized rate")
    if round(
        float(deterministic["pass_rate"])
        + float(deterministic["warn_rate"])
        + float(deterministic["fail_rate"]),
        5,
    ) not in {0.0, 1.0}:
        raise ValueError("deterministic verdict rates must sum to 1 for non-empty runs")
    advisory = snapshot.get("advisory")
    if not isinstance(advisory, dict) or advisory.get("factual_authority") is not False:
        raise ValueError("advisory trend metrics must remain non-authoritative")


def _direction(delta: float, *, higher_is_better: bool, epsilon: float = 1e-6) -> str:
    if abs(delta) <= epsilon:
        return "STABLE"
    improved = delta > 0 if higher_is_better else delta < 0
    return "IMPROVED" if improved else "REGRESSED"


def compare_snapshots(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    validate_snapshot(previous)
    validate_snapshot(current)
    if previous["scope"] != current["scope"]:
        raise ValueError("trend snapshots must use the same scope")

    metrics = {}
    definitions = [
        ("pass_rate", previous["deterministic"]["pass_rate"], current["deterministic"]["pass_rate"], True),
        ("warn_rate", previous["deterministic"]["warn_rate"], current["deterministic"]["warn_rate"], False),
        ("fail_rate", previous["deterministic"]["fail_rate"], current["deterministic"]["fail_rate"], False),
        (
            "critical_finding_count",
            previous["deterministic"]["critical_finding_count"],
            current["deterministic"]["critical_finding_count"],
            False,
        ),
        (
            "actionable_product_cluster_count",
            previous["defects"]["actionable_product_cluster_count"],
            current["defects"]["actionable_product_cluster_count"],
            False,
        ),
    ]
    for name, before, after, higher in definitions:
        delta = round(float(after) - float(before), 6)
        metrics[name] = {
            "previous": before,
            "current": after,
            "delta": delta,
            "direction": _direction(delta, higher_is_better=higher),
            "authority": "deterministic",
        }

    q_prev = previous["advisory"]["human_quality_average"]
    q_cur = current["advisory"]["human_quality_average"]
    if q_prev is not None and q_cur is not None:
        delta = round(float(q_cur) - float(q_prev), 6)
        metrics["human_quality_average"] = {
            "previous": q_prev,
            "current": q_cur,
            "delta": delta,
            "direction": _direction(delta, higher_is_better=True),
            "authority": "advisory_only",
        }

    deterministic_directions = {
        item["direction"]
        for item in metrics.values()
        if item["authority"] == "deterministic"
    }
    overall = (
        "REGRESSED"
        if "REGRESSED" in deterministic_directions
        else "IMPROVED"
        if "IMPROVED" in deterministic_directions
        else "STABLE"
    )
    return {
        "trend_comparison_version": "roberta_trend_comparison/v1",
        "scope": current["scope"],
        "previous_snapshot_id": previous["snapshot_id"],
        "current_snapshot_id": current["snapshot_id"],
        "overall_deterministic_direction": overall,
        "metrics": metrics,
    }


def validate_history(history: dict[str, Any]) -> None:
    if history.get("history_version") != HISTORY_VERSION:
        raise ValueError("unsupported trend history version")
    if not history.get("policy"):
        raise ValueError("trend history policy is required")
    snapshots = history.get("snapshots")
    if not isinstance(snapshots, list):
        raise ValueError("trend history snapshots must be a list")
    ids = [item.get("snapshot_id") for item in snapshots]
    if len(ids) != len(set(ids)):
        raise ValueError("trend snapshot IDs must be unique")
    for snapshot in snapshots:
        validate_snapshot(snapshot)


def append_snapshot(history: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    validate_history(history)
    validate_snapshot(snapshot)
    if any(item["snapshot_id"] == snapshot["snapshot_id"] for item in history["snapshots"]):
        return history
    updated = deepcopy(history)
    updated["snapshots"].append(deepcopy(snapshot))
    validate_history(updated)
    return updated


def history_summary(history: dict[str, Any] | None = None) -> dict[str, Any]:
    history = history or load_history()
    validate_history(history)
    return {
        "history_version": HISTORY_VERSION,
        "snapshot_count": len(history["snapshots"]),
        "scopes": sorted({item["scope"] for item in history["snapshots"]}),
    }
