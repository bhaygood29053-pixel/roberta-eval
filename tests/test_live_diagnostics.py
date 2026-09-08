from __future__ import annotations

import json

import pytest

from roberta_eval.live import LIVE_GRADE_VERSION
from roberta_eval.live_diagnostics import (
    DIAGNOSTICS_VERSION,
    diagnose_live_grades,
    render_diagnostics_markdown,
)


def grade(
    record_id: str,
    service: str,
    verdict: str,
    reason: str,
) -> dict:
    value = {
        "live_grader_version": LIVE_GRADE_VERSION,
        "run_id": "live-smoke",
        "record_id": record_id,
        "case_id": f"case::{record_id}",
        "service": service,
        "verdict": verdict,
        "reason": reason,
        "live_roberta_qualified": False,
    }
    if verdict == "FAIL":
        value["severity"] = "HIGH"
    return value


def test_diagnostics_groups_live_failures_and_evidence_gaps_separately():
    results = [
        grade("1", "asset_lookup", "FAIL", "runtime_failure"),
        grade("2", "market_report", "EVIDENCE_REQUIRED", "canonical_claims_empty"),
        grade("3", "risk_check", "EVIDENCE_REQUIRED", "claim_integrity_unavailable"),
        grade("4", "pre_trade_check", "FAIL", "execution_boundary_violated"),
        grade("5", "asset_lookup", "PASS", "live_evidence_contract_satisfied"),
    ]

    report = diagnose_live_grades(results)

    assert report["diagnostics_version"] == DIAGNOSTICS_VERSION
    assert report["verdict_counts"] == {
        "PASS": 1,
        "EVIDENCE_REQUIRED": 2,
        "FAIL": 2,
    }
    assert report["qualification_blocking"] is True
    assert report["actual_live_failures_present"] is True
    assert report["evidence_gaps_present"] is True

    groups = {item["reason"]: item for item in report["remediation_groups"]}
    assert groups["runtime_failure"]["priority"] == "P0"
    assert groups["runtime_failure"]["owner_repository"] == (
        "bhaygood29053-pixel/roberta-langgraph"
    )
    assert groups["canonical_claims_empty"]["diagnostic_class"] == (
        "canonical_claim_coverage_gap"
    )
    assert groups["canonical_claims_empty"]["product_defect_candidate"] is False
    assert groups["claim_integrity_unavailable"]["owner_repository"] == (
        "bhaygood29053-pixel/roberta-core"
    )
    assert groups["execution_boundary_violated"]["priority"] == "P0"
    assert groups["execution_boundary_violated"]["product_defect_candidate"] is True


def test_service_summary_preserves_gradeability_boundary():
    results = [
        grade("1", "asset_lookup", "PASS", "live_evidence_contract_satisfied"),
        grade("2", "asset_lookup", "PASS", "live_evidence_contract_satisfied"),
        grade("3", "market_report", "EVIDENCE_REQUIRED", "evidence_freshness_unavailable"),
    ]

    report = diagnose_live_grades(results)
    services = {item["service"]: item for item in report["service_summaries"]}

    assert services["asset_lookup"]["fully_gradeable"] is True
    assert services["asset_lookup"]["all_pass"] is True
    assert services["market_report"]["fully_gradeable"] is False
    assert services["market_report"]["all_pass"] is False


def test_runtime_failure_is_prioritized_before_noncritical_evidence_gap():
    results = [
        grade("1", "market_report", "EVIDENCE_REQUIRED", "evidence_provenance_unavailable"),
        grade("2", "asset_lookup", "FAIL", "runtime_failure"),
    ]

    report = diagnose_live_grades(results)

    assert report["recommended_next_group"]["reason"] == "runtime_failure"
    assert report["recommended_next_group"]["priority"] == "P0"


def test_unknown_reason_stays_with_laboratory_until_explicitly_mapped():
    results = [
        grade("1", "asset_lookup", "EVIDENCE_REQUIRED", "new_future_reason"),
    ]

    report = diagnose_live_grades(results)
    group = report["remediation_groups"][0]

    assert group["diagnostic_class"] == "unclassified_live_grade_reason"
    assert group["owner_repository"] == "bhaygood29053-pixel/roberta-eval"
    assert group["product_defect_candidate"] is False


def test_diagnostics_reject_non_live_grades():
    with pytest.raises(ValueError, match="LAB #21"):
        diagnose_live_grades(
            [
                {
                    "live_grader_version": "wrong/v1",
                    "record_id": "1",
                    "verdict": "FAIL",
                }
            ]
        )


def test_diagnostics_reject_duplicate_record_identity():
    value = grade("same", "asset_lookup", "FAIL", "runtime_failure")
    with pytest.raises(ValueError, match="duplicate"):
        diagnose_live_grades([value, dict(value)])


def test_markdown_states_evidence_required_is_not_factual_failure():
    report = diagnose_live_grades(
        [grade("1", "market_report", "EVIDENCE_REQUIRED", "canonical_claims_empty")]
    )

    markdown = render_diagnostics_markdown(report)

    assert "EVIDENCE_REQUIRED is not a ROBERTA factual failure" in markdown
    assert "canonical_claims_empty" in markdown
    assert "bhaygood29053-pixel/roberta-langgraph" in markdown


def test_report_is_json_serializable_and_deterministic():
    results = [
        grade("2", "market_report", "EVIDENCE_REQUIRED", "canonical_claims_empty"),
        grade("1", "asset_lookup", "FAIL", "runtime_failure"),
    ]

    first = diagnose_live_grades(results)
    second = diagnose_live_grades(list(reversed(results)))

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_missing_current_x1_evidence_is_owned_by_protected_orchestration() -> None:
    report = diagnose_live_grades(
        [
            grade(
                "1",
                "tokenomics",
                "EVIDENCE_REQUIRED",
                "current_x1_evidence_unavailable",
            ),
            grade(
                "2",
                "risk_check",
                "EVIDENCE_REQUIRED",
                "current_x1_evidence_unavailable",
            ),
        ]
    )

    group = report["recommended_next_group"]
    assert group["reason"] == "current_x1_evidence_unavailable"
    assert group["diagnostic_class"] == "current_x1_evidence_delegation_gap"
    assert group["owner_repository"] == "bhaygood29053-pixel/roberta-core"
    assert group["component"] == "roberta_oracle_evidence_delegation"
    assert group["product_defect_candidate"] is True
    assert report["product_defect_candidate_count"] == 2
    assert report["actual_live_failures_present"] is False
    assert report["evidence_gaps_present"] is True
