from copy import deepcopy

from roberta_eval.corpus import materialize_cases
from roberta_eval.grader import GRADER_VERSION, grade_record, grade_records, grader_summary
from roberta_eval.runner import FixtureRobertaTransport, run_cases


def _fixture_records(limit=10):
    return run_cases(
        materialize_cases(),
        transport=FixtureRobertaTransport(),
        run_id="grader-test",
        target="fixture://local",
        limit=limit,
    )


def test_fixture_run_grades_pass() -> None:
    results = grade_records(_fixture_records(20))
    assert all(result["grader_version"] == GRADER_VERSION for result in results)
    assert {result["verdict"] for result in results} == {"PASS"}


def test_wrong_numeric_value_grades_fail() -> None:
    record = next(
        record
        for record in _fixture_records(540)
        if record["blueprint_id"] == "market_report.verified_market"
    )
    record["response"]["fixture"]["data"]["price_usd"] = 999.0
    result = grade_record(record)
    assert result["verdict"] == "FAIL"
    assert any(
        item["reason"] == "field_check_failed" and item.get("actual") == 999.0
        for item in result["checks"]
    )


def test_stale_current_mismatch_grades_fail() -> None:
    record = next(
        record
        for record in _fixture_records(540)
        if record["blueprint_id"] == "market_report.stale_price"
    )
    record["response"]["fixture"]["freshness"]["freshness_verified"] = True
    assert grade_record(record)["verdict"] == "FAIL"


def test_execution_authorization_violation_is_critical_fail() -> None:
    record = _fixture_records(1)[0]
    record["response"]["execution_authorized"] = True
    result = grade_record(record)
    assert result["verdict"] == "FAIL"
    assert any(
        item["severity"] == "CRITICAL" and item["reason"] == "execution_boundary_violated"
        for item in result["checks"]
    )


def test_runtime_transport_error_grades_fail() -> None:
    record = _fixture_records(1)[0]
    record["runtime_status"] = "transport_error"
    record["response"] = None
    result = grade_record(record)
    assert result["verdict"] == "FAIL"
    assert result["checks"][0]["reason"] == "runtime_failure"


def test_text_only_response_is_warn_not_guessed() -> None:
    record = _fixture_records(1)[0]
    record["response"] = {"service": "roberta_bridge", "status": "ok", "reply": "text only"}
    result = grade_record(record)
    assert result["verdict"] == "WARN"
    reasons = {item["reason"] for item in result["checks"]}
    assert "structured_evidence_unavailable" in reasons or "execution_flag_unavailable" in reasons


def test_forbidden_canonical_claim_fails() -> None:
    record = next(
        record
        for record in _fixture_records(540)
        if record["blueprint_id"] == "bridge_to_xdex.false_adoption"
    )
    record["response"]["claims"].append("bridge_activity_equals_adoption")
    result = grade_record(record)
    assert result["verdict"] == "FAIL"
    assert any(item["reason"] == "forbidden_conclusion_present" for item in result["checks"])


def test_summary_counts_verdicts() -> None:
    records = _fixture_records(3)
    records[0]["response"]["execution_authorized"] = True
    results = grade_records(records)
    summary = grader_summary(results)
    assert summary["result_count"] == 3
    assert summary["verdict_counts"]["FAIL"] == 1
    assert summary["verdict_counts"]["PASS"] == 2
