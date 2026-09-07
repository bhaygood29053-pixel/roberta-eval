from __future__ import annotations

import pytest

from roberta_eval.corpus import materialize_cases
from roberta_eval.live import (
    grade_live_record,
    live_case_summary,
    materialize_live_cases,
)
from roberta_eval.runner import select_cases


def _live_record(response: dict) -> dict:
    return {
        "record_version": "roberta_eval_run_record/v1",
        "run_id": "live-test",
        "record_id": "live-test:case",
        "case_id": "live.asset_lookup.identity::xnt",
        "service": "asset_lookup",
        "case_data_mode": "live_evidence",
        "runtime_status": "ok",
        "response": response,
    }


def test_live_suite_uses_real_subjects_without_synthetic_answer_key() -> None:
    cases = materialize_live_cases()
    summary = live_case_summary(cases)

    assert len(cases) == 20
    assert summary["subjects"] == ["AGI", "XNT"]
    assert summary["synthetic_ground_truth_used"] is False
    assert all(case["case_data_mode"] == "live_evidence" for case in cases)
    assert all("fixture" not in case for case in cases)
    assert all("LABX" not in case["question"] for case in cases)


def test_balanced_selection_spans_services() -> None:
    cases = materialize_cases()
    selected = select_cases(cases, limit=20, strategy="balanced")

    assert len(selected) == 20
    assert len({case["service"] for case in selected}) == 18


def test_live_grader_requires_structured_telemetry() -> None:
    result = grade_live_record(
        _live_record(
            {
                "service": "roberta_bridge",
                "status": "ok",
                "reply": "Human-facing answer only.",
            }
        )
    )

    assert result["verdict"] == "EVIDENCE_REQUIRED"
    assert result["reason"] == "evaluation_telemetry_version_unavailable"
    assert result["live_roberta_qualified"] is False


def test_live_grader_requires_at_least_one_canonical_claim() -> None:
    result = grade_live_record(
        _live_record(
            {
                "service": "roberta_bridge",
                "status": "ok",
                "reply": "No structured claim.",
                "evaluation_telemetry_version": "roberta_evaluation_telemetry/v1",
                "evaluation_evidence": {"state": {"status": "unknown"}},
                "claims": [],
                "evidence_provenance": {"facts_authority": "chain_scout_cmis"},
                "evidence_freshness": {"state": "unknown"},
                "execution_authorized": False,
            }
        )
    )

    assert result["verdict"] == "EVIDENCE_REQUIRED"
    assert result["reason"] == "canonical_claims_empty"
    assert result["live_roberta_qualified"] is False


def test_live_grader_passes_claims_that_match_evidence() -> None:
    result = grade_live_record(
        _live_record(
            {
                "service": "roberta_bridge",
                "status": "ok",
                "reply": "XNT resolved from verified evidence.",
                "evaluation_telemetry_version": "roberta_evaluation_telemetry/v1",
                "evaluation_evidence": {
                    "asset": {
                        "symbol": "XNT",
                        "mint": "verified-mint",
                    }
                },
                "claims": [
                    {
                        "name": "asset_symbol",
                        "evidence_path": "asset.symbol",
                        "value": "XNT",
                    }
                ],
                "evidence_provenance": [{"authority": "cmis"}],
                "evidence_freshness": {"state": "current"},
                "execution_authorized": False,
            }
        )
    )

    assert result["verdict"] == "PASS"
    assert result["checked_claims"] == 1
    assert result["live_roberta_qualified"] is True


def test_live_grader_fails_claim_evidence_mismatch() -> None:
    result = grade_live_record(
        _live_record(
            {
                "service": "roberta_bridge",
                "status": "ok",
                "reply": "Mismatch example.",
                "evaluation_telemetry_version": "roberta_evaluation_telemetry/v1",
                "evaluation_evidence": {"asset": {"symbol": "XNT"}},
                "claims": [
                    {
                        "name": "asset_symbol",
                        "evidence_path": "asset.symbol",
                        "value": "AGI",
                    }
                ],
                "evidence_provenance": [{"authority": "cmis"}],
                "evidence_freshness": {"state": "current"},
                "execution_authorized": False,
            }
        )
    )

    assert result["verdict"] == "FAIL"
    assert result["reason"] == "canonical_claim_disagrees_with_evidence"


def test_live_grader_refuses_synthetic_record() -> None:
    record = _live_record({})
    record["case_data_mode"] = "synthetic_fixture"

    with pytest.raises(ValueError, match="refuses non-live"):
        grade_live_record(record)
