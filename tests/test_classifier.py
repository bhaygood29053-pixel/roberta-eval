from copy import deepcopy

from roberta_eval.classifier import (
    classify_conversation_result,
    classify_grade_result,
    classification_summary,
)
from roberta_eval.corpus import materialize_cases
from roberta_eval.grader import grade_record
from roberta_eval.runner import FixtureRobertaTransport, run_cases


def _record(blueprint_id: str):
    record = next(
        item
        for item in run_cases(
            materialize_cases(),
            transport=FixtureRobertaTransport(),
            run_id="classify-test",
            target="fixture://local",
        )
        if item["blueprint_id"] == blueprint_id
    )
    return record


def test_execution_violation_is_critical() -> None:
    record = _record("pre_trade_check.execution")
    record["response"]["execution_authorized"] = True
    findings = classify_grade_result(grade_record(record))
    assert any(
        item["category"] == "EXECUTION_BOUNDARY_VIOLATION"
        and item["severity"] == "CRITICAL"
        for item in findings
    )


def test_numeric_field_failure_is_numeric_error() -> None:
    record = _record("market_report.verified_market")
    record["response"]["fixture"]["data"]["price_usd"] = 99.0
    findings = classify_grade_result(grade_record(record))
    assert any(item["category"] == "NUMERICAL_ERROR" for item in findings)


def test_freshness_failure_is_freshness_error() -> None:
    record = _record("market_report.stale_price")
    record["response"]["fixture"]["freshness"]["freshness_verified"] = True
    findings = classify_grade_result(grade_record(record))
    assert any(item["category"] == "FRESHNESS_ERROR" for item in findings)


def test_text_only_warning_is_evaluation_incomplete_not_product_defect() -> None:
    record = _record("market_report.verified_market")
    record["response"] = {"status": "ok", "reply": "text only"}
    findings = classify_grade_result(grade_record(record))
    assert findings
    assert all(
        item["category"] in {"EVALUATION_INCOMPLETE", "EVALUATION_ERROR"}
        for item in findings
    )
    assert any(item["evaluation_incomplete"] for item in findings)


def test_conversation_fact_drift_is_contradiction() -> None:
    result = {
        "consistency_grader_version": "roberta_conversation_consistency/v1",
        "conversation_id": "conv::x",
        "run_id": "run",
        "service": "market_report",
        "objective_signature": "market_report:x",
        "turn_count": 3,
        "verdict": "FAIL",
        "checks": [
            {
                "status": "FAIL",
                "severity": "HIGH",
                "reason": "facts_drift_without_new_evidence",
            }
        ],
    }
    findings = classify_conversation_result(result)
    assert findings[0]["category"] == "CONTRADICTION"
    assert findings[0]["confidence"] == 1.0


def test_summary_counts_categories_and_incomplete() -> None:
    record = _record("market_report.verified_market")
    record["response"] = {"status": "ok", "reply": "text only"}
    findings = classify_grade_result(grade_record(record))
    summary = classification_summary(findings)
    assert summary["finding_count"] == len(findings)
    assert summary["evaluation_incomplete_count"] > 0
