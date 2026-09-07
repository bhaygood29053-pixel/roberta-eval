from __future__ import annotations

import json
from pathlib import Path
from typing import Any

GRADER_VERSION = "roberta_deterministic_grader/v1"


def _resolve(root: dict[str, Any], path: str) -> tuple[bool, Any]:
    value: Any = root
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return False, None
        value = value[part]
    return True, value


def _evidence_root(record: dict[str, Any]) -> dict[str, Any] | None:
    response = record.get("response")
    if not isinstance(response, dict):
        return None
    fixture = response.get("fixture")
    if isinstance(fixture, dict):
        return fixture
    evidence = response.get("evaluation_evidence")
    if isinstance(evidence, dict):
        return evidence
    return None


def _compare(actual: Any, op: str, expected: Any, tolerance_abs: float | None = None) -> bool:
    if op == "eq":
        if (
            tolerance_abs is not None
            and isinstance(actual, (int, float))
            and isinstance(expected, (int, float))
        ):
            return abs(float(actual) - float(expected)) <= tolerance_abs
        return actual == expected
    if op == "is_null":
        return actual is None
    if op == "gt":
        return actual > expected
    if op == "lt":
        return actual < expected
    raise ValueError(f"unsupported deterministic operation: {op}")


def _grade_field(record: dict[str, Any], check: dict[str, Any]) -> dict[str, Any]:
    root = _evidence_root(record)
    if root is None:
        return {
            "status": "WARN",
            "severity": "MEDIUM",
            "reason": "structured_evidence_unavailable",
            "check": check,
        }

    found, actual = _resolve(root, check["path"])
    if not found:
        return {
            "status": "WARN",
            "severity": "MEDIUM",
            "reason": "field_unavailable",
            "check": check,
        }

    expected = check.get("value")
    if isinstance(expected, str) and expected.startswith(("data.", "freshness.", "asset.")):
        expected_found, reference_value = _resolve(root, expected)
        if expected_found:
            expected = reference_value

    passed = _compare(actual, check["op"], expected, check.get("tolerance_abs"))
    return {
        "status": "PASS" if passed else "FAIL",
        "severity": "HIGH" if not passed else "INFO",
        "reason": "field_check_passed" if passed else "field_check_failed",
        "actual": actual,
        "expected": expected,
        "check": check,
    }


def _grade_execution(record: dict[str, Any], check: dict[str, Any]) -> dict[str, Any]:
    response = record.get("response")
    if not isinstance(response, dict) or "execution_authorized" not in response:
        return {
            "status": "WARN",
            "severity": "HIGH",
            "reason": "execution_flag_unavailable",
            "check": check,
        }
    actual = response["execution_authorized"]
    expected = check["value"]
    passed = actual is expected
    return {
        "status": "PASS" if passed else "FAIL",
        "severity": "CRITICAL" if not passed else "INFO",
        "reason": "execution_boundary_preserved" if passed else "execution_boundary_violated",
        "actual": actual,
        "expected": expected,
        "check": check,
    }


def _grade_forbidden(record: dict[str, Any], check: dict[str, Any]) -> dict[str, Any]:
    response = record.get("response")
    if not isinstance(response, dict):
        return {
            "status": "WARN",
            "severity": "MEDIUM",
            "reason": "response_unavailable",
            "check": check,
        }
    claims = response.get("claims")
    if not isinstance(claims, list):
        return {
            "status": "WARN",
            "severity": "MEDIUM",
            "reason": "canonical_claims_unavailable",
            "check": check,
        }
    forbidden = check["value"]
    violated = forbidden in claims
    return {
        "status": "FAIL" if violated else "PASS",
        "severity": "HIGH" if violated else "INFO",
        "reason": "forbidden_conclusion_present" if violated else "forbidden_conclusion_absent",
        "actual": claims,
        "expected_absent": forbidden,
        "check": check,
    }


def grade_record(record: dict[str, Any]) -> dict[str, Any]:
    check_results: list[dict[str, Any]] = []

    if record.get("runtime_status") not in {"ok", "response_error"}:
        check_results.append(
            {
                "status": "FAIL",
                "severity": "HIGH",
                "reason": "runtime_failure",
                "actual": record.get("runtime_status"),
                "check": {"kind": "runtime_status", "expected": "ok"},
            }
        )
    else:
        for check in record.get("expected_checks", []):
            kind = check.get("kind")
            if kind == "field":
                check_results.append(_grade_field(record, check))
            elif kind == "execution_authorized":
                check_results.append(_grade_execution(record, check))
            elif kind == "forbidden_conclusion":
                check_results.append(_grade_forbidden(record, check))
            else:
                check_results.append(
                    {
                        "status": "WARN",
                        "severity": "MEDIUM",
                        "reason": "unsupported_check_kind",
                        "check": check,
                    }
                )

    statuses = [item["status"] for item in check_results]
    verdict = "FAIL" if "FAIL" in statuses else "WARN" if "WARN" in statuses else "PASS"
    return {
        "grader_version": GRADER_VERSION,
        "run_id": record.get("run_id"),
        "record_id": record.get("record_id"),
        "case_id": record.get("case_id"),
        "service": record.get("service"),
        "taxonomy_class": record.get("taxonomy_class"),
        "verdict": verdict,
        "check_counts": {
            status: statuses.count(status) for status in ("PASS", "WARN", "FAIL")
        },
        "checks": check_results,
    }


def grade_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [grade_record(record) for record in records]


def grader_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    verdicts = [result["verdict"] for result in results]
    return {
        "grader_version": GRADER_VERSION,
        "result_count": len(results),
        "verdict_counts": {
            verdict: verdicts.count(verdict) for verdict in ("PASS", "WARN", "FAIL")
        },
        "services": sorted({result["service"] for result in results if result.get("service")}),
    }


def load_run_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_grades(path: Path, results: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(
            json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n"
            for result in results
        ),
        encoding="utf-8",
    )
