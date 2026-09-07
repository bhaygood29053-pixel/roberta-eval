from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CLASSIFIER_VERSION = "roberta_failure_classifier/v1"

CATEGORIES = {
    "RUNTIME_ERROR",
    "FACTUAL_ERROR",
    "NUMERICAL_ERROR",
    "FRESHNESS_ERROR",
    "UNSUPPORTED_CONCLUSION",
    "EXECUTION_BOUNDARY_VIOLATION",
    "CONTRADICTION",
    "EVALUATION_INCOMPLETE",
    "EVALUATION_ERROR",
}

_NUMERIC_TYPES = (int, float)


def _field_category(check_result: dict[str, Any]) -> str:
    check = check_result.get("check") or {}
    path = str(check.get("path", ""))
    if path.startswith("freshness.") or "freshness" in path:
        return "FRESHNESS_ERROR"

    actual = check_result.get("actual")
    expected = check_result.get("expected")
    if (
        isinstance(actual, _NUMERIC_TYPES)
        and not isinstance(actual, bool)
        and isinstance(expected, _NUMERIC_TYPES)
        and not isinstance(expected, bool)
    ):
        return "NUMERICAL_ERROR"
    return "FACTUAL_ERROR"


def _mapping(reason: str, check_result: dict[str, Any]) -> tuple[str, str]:
    if reason == "runtime_failure":
        return "RUNTIME_ERROR", "HIGH"
    if reason == "field_check_failed":
        return _field_category(check_result), "HIGH"
    if reason == "forbidden_conclusion_present":
        return "UNSUPPORTED_CONCLUSION", "HIGH"
    if reason in {
        "execution_boundary_violated",
        "execution_boundary_violated_in_conversation",
    }:
        return "EXECUTION_BOUNDARY_VIOLATION", "CRITICAL"
    if reason == "facts_drift_without_new_evidence":
        return "CONTRADICTION", "HIGH"
    if reason in {
        "structured_evidence_unavailable",
        "field_unavailable",
        "execution_flag_unavailable",
        "response_unavailable",
        "canonical_claims_unavailable",
        "structured_conversation_evidence_unavailable",
        "execution_flag_unavailable_in_conversation",
    }:
        severity = str(check_result.get("severity") or "MEDIUM")
        return "EVALUATION_INCOMPLETE", severity
    if reason == "unsupported_check_kind":
        return "EVALUATION_ERROR", "MEDIUM"
    return "EVALUATION_ERROR", str(check_result.get("severity") or "MEDIUM")


def classify_check(
    check_result: dict[str, Any],
    *,
    source: dict[str, Any],
    source_grader: str,
) -> dict[str, Any] | None:
    status = check_result.get("status")
    if status == "PASS":
        return None

    reason = str(check_result.get("reason") or "unknown_reason")
    category, severity = _mapping(reason, check_result)
    return {
        "classifier_version": CLASSIFIER_VERSION,
        "finding_id": (
            f"{source.get('case_id') or source.get('conversation_id')}:"
            f"{source_grader}:{reason}"
        ),
        "source_grader": source_grader,
        "source_status": status,
        "category": category,
        "severity": severity,
        "confidence": 1.0 if reason != "unknown_reason" else 0.0,
        "reason": reason,
        "run_id": source.get("run_id"),
        "record_id": source.get("record_id"),
        "case_id": source.get("case_id"),
        "conversation_id": source.get("conversation_id"),
        "service": source.get("service"),
        "taxonomy_class": source.get("taxonomy_class"),
        "check": check_result.get("check"),
        "actual": check_result.get("actual"),
        "expected": check_result.get("expected"),
        "evaluation_incomplete": category == "EVALUATION_INCOMPLETE",
    }


def classify_grade_result(result: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        finding
        for check in result.get("checks", [])
        if (finding := classify_check(
            check,
            source=result,
            source_grader=str(result.get("grader_version") or "deterministic"),
        )) is not None
    ]


def classify_conversation_result(result: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        finding
        for check in result.get("checks", [])
        if (finding := classify_check(
            check,
            source=result,
            source_grader=str(
                result.get("consistency_grader_version") or "conversation_consistency"
            ),
        )) is not None
    ]


def classify_results(
    grade_results: list[dict[str, Any]],
    conversation_results: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for result in grade_results:
        findings.extend(classify_grade_result(result))
    for result in conversation_results or []:
        findings.extend(classify_conversation_result(result))
    return findings


def classification_summary(findings: list[dict[str, Any]]) -> dict[str, Any]:
    categories = {category: 0 for category in sorted(CATEGORIES)}
    severities: dict[str, int] = {}
    for finding in findings:
        categories[finding["category"]] += 1
        severity = finding["severity"]
        severities[severity] = severities.get(severity, 0) + 1
    return {
        "classifier_version": CLASSIFIER_VERSION,
        "finding_count": len(findings),
        "category_counts": categories,
        "severity_counts": dict(sorted(severities.items())),
        "evaluation_incomplete_count": sum(
            1 for finding in findings if finding["evaluation_incomplete"]
        ),
    }


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_findings(path: Path, findings: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(
            json.dumps(finding, sort_keys=True, separators=(",", ":")) + "\n"
            for finding in findings
        ),
        encoding="utf-8",
    )
