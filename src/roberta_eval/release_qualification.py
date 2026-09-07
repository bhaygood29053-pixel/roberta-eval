from __future__ import annotations

import json
from pathlib import Path
from typing import Any

POLICY_VERSION = "roberta_release_policy/v1"
QUALIFICATION_VERSION = "roberta_release_qualification/v1"


def policy_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "release_policy.json"


def load_policy(path: Path | None = None) -> dict[str, Any]:
    source = path or policy_path()
    return json.loads(source.read_text(encoding="utf-8"))


def validate_policy(policy: dict[str, Any]) -> None:
    if policy.get("policy_version") != POLICY_VERSION:
        raise ValueError("unsupported release policy version")
    deterministic = policy.get("deterministic")
    advisory = policy.get("advisory")
    scope = policy.get("scope")
    if not isinstance(deterministic, dict) or not isinstance(advisory, dict) or not isinstance(scope, dict):
        raise ValueError("release policy sections are required")
    if advisory.get("blocking") is not False:
        raise ValueError("advisory quality must not become a blocking factual authority")
    for key in ("max_failures", "max_critical_findings", "max_regression_replay_failures"):
        value = deterministic.get(key)
        if not isinstance(value, int) or value < 0:
            raise ValueError(f"{key}: invalid threshold")


def qualify_release(
    *,
    requested_scope: str,
    qualification_report: dict[str, Any],
    critical_finding_count: int = 0,
    regression_replay_summary: dict[str, Any] | None = None,
    quality_summary: dict[str, Any] | None = None,
    trend_comparison: dict[str, Any] | None = None,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    policy = policy or load_policy()
    validate_policy(policy)
    if requested_scope not in {"fixture_pipeline", "live_roberta"}:
        raise ValueError("unsupported requested release scope")

    deterministic = policy["deterministic"]
    verdicts = qualification_report["grading"]["verdict_counts"]
    failures = int(verdicts["FAIL"])
    regression_failures = int((regression_replay_summary or {}).get("fail_count", 0))

    blocking: list[dict[str, Any]] = []
    advisory_warnings: list[dict[str, Any]] = []

    if requested_scope == "live_roberta" and not qualification_report.get("live_roberta_qualified", False):
        status = "EVIDENCE_REQUIRED"
        blocking.append(
            {
                "gate": "live_evidence",
                "reason": "requested live ROBERTA release scope lacks live-qualified evidence",
            }
        )
    else:
        status = "QUALIFIED"

    if failures > deterministic["max_failures"]:
        blocking.append({"gate": "deterministic_failures", "actual": failures})
    if critical_finding_count > deterministic["max_critical_findings"]:
        blocking.append({"gate": "critical_findings", "actual": critical_finding_count})
    if regression_failures > deterministic["max_regression_replay_failures"]:
        blocking.append({"gate": "regression_replay_failures", "actual": regression_failures})
    if (
        deterministic.get("block_on_regressed_trend")
        and trend_comparison is not None
        and trend_comparison.get("overall_deterministic_direction") == "REGRESSED"
    ):
        blocking.append({"gate": "deterministic_trend", "actual": "REGRESSED"})

    quality = (
        float(quality_summary["average_overall_score"])
        if quality_summary is not None
        and quality_summary.get("average_overall_score") is not None
        else None
    )
    threshold = float(policy["advisory"]["human_quality_warn_below"])
    if quality is not None and quality < threshold:
        advisory_warnings.append(
            {
                "gate": "human_quality",
                "actual": quality,
                "warn_below": threshold,
                "authority": "advisory_only",
            }
        )

    if any(item["gate"] != "live_evidence" for item in blocking):
        status = "BLOCKED"
    elif status != "EVIDENCE_REQUIRED" and advisory_warnings:
        status = "QUALIFIED_WITH_ADVISORY_WARNINGS"

    return {
        "qualification_version": QUALIFICATION_VERSION,
        "policy_version": POLICY_VERSION,
        "requested_scope": requested_scope,
        "status": status,
        "release_qualified": status in {"QUALIFIED", "QUALIFIED_WITH_ADVISORY_WARNINGS"},
        "live_roberta_qualified": bool(qualification_report.get("live_roberta_qualified", False)),
        "blocking_gates": blocking,
        "advisory_warnings": advisory_warnings,
        "deterministic": {
            "failures": failures,
            "critical_finding_count": critical_finding_count,
            "regression_replay_failures": regression_failures,
        },
        "advisory": {
            "human_quality_average": quality,
            "factual_authority": False,
        },
    }


def write_qualification(path: Path, report: dict[str, Any]) -> None:
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
