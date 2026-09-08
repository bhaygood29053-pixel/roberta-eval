from __future__ import annotations

import pytest

from roberta_eval.corpus import materialize_cases
from roberta_eval.live import (
    grade_live_record,
    live_case_summary,
    materialize_live_cases,
)
from roberta_eval.runner import select_cases


def _live_record(response: dict, *, service: str = "asset_lookup") -> dict:
    return {
        "record_version": "roberta_eval_run_record/v1",
        "run_id": "live-test",
        "record_id": f"live-test:{service}",
        "case_id": f"live.{service}.test::xnt",
        "service": service,
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
                    },
                    "claim_integrity": {
                        "contract_version": "roberta_claim_integrity/v1",
                        "status": "PASS",
                    },
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
    assert result["live_evidence_contract_qualified"] is True
    assert result["live_roberta_qualified"] is False
    assert result["provider_truth_certified"] is False
    assert result["all_natural_language_claims_certified"] is False


def test_live_grader_requires_claim_integrity_certificate() -> None:
    result = grade_live_record(
        _live_record(
            {
                "service": "roberta_bridge",
                "status": "ok",
                "reply": "Structured but not claim-integrity certified.",
                "evaluation_telemetry_version": "roberta_evaluation_telemetry/v1",
                "evaluation_evidence": {"asset": {"symbol": "XNT"}},
                "claims": [
                    {
                        "name": "asset_symbol",
                        "evidence_path": "asset.symbol",
                        "value": "XNT",
                    }
                ],
                "evidence_provenance": {"facts_authority": "chain_scout_cmis"},
                "evidence_freshness": {"state": "unknown"},
                "execution_authorized": False,
            }
        )
    )

    assert result["verdict"] == "EVIDENCE_REQUIRED"
    assert result["reason"] == "claim_integrity_unavailable"


def test_live_grader_fails_claim_evidence_mismatch() -> None:
    result = grade_live_record(
        _live_record(
            {
                "service": "roberta_bridge",
                "status": "ok",
                "reply": "Mismatch example.",
                "evaluation_telemetry_version": "roberta_evaluation_telemetry/v1",
                "evaluation_evidence": {
                    "asset": {"symbol": "XNT"},
                    "claim_integrity": {
                        "contract_version": "roberta_claim_integrity/v1",
                        "status": "PASS",
                    },
                },
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


def test_live_grader_passes_v2_factual_projection_integrity() -> None:
    result = grade_live_record(
        _live_record(
            {
                "service": "roberta_bridge",
                "status": "ok",
                "reply": "XNT market evidence is available.",
                "evaluation_telemetry_version": "roberta_evaluation_telemetry/v2",
                "evaluation_evidence": {
                    "factual_response": {
                        "contract_version": "roberta_evaluation_factual_evidence/v1",
                        "findings": {
                            "data": {
                                "price": 0.0123,
                                "liquidity": 5000.0,
                            }
                        },
                    },
                    "evaluation_projection_integrity": {
                        "contract_version": "roberta_evaluation_projection_integrity/v1",
                        "status": "PASS",
                        "claim_count": 2,
                        "provider_truth_certified": False,
                        "all_natural_language_claims_certified": False,
                        "execution_authorized": False,
                    },
                },
                "claims": [
                    {
                        "name": "factual_data_price",
                        "evidence_path": "factual_response.findings.data.price",
                        "value": 0.0123,
                    },
                    {
                        "name": "factual_data_liquidity",
                        "evidence_path": "factual_response.findings.data.liquidity",
                        "value": 5000.0,
                    },
                ],
                "evidence_provenance": {
                    "facts_authority": "chain_scout_cmis",
                    "factual_projection": {
                        "second_cmis_query_performed": False,
                        "prose_claim_inference_performed": False,
                    },
                },
                "evidence_freshness": {"state": "VERIFIED"},
                "execution_authorized": False,
            },
            service="market_report",
        )
    )

    assert result["verdict"] == "PASS"
    assert result["checked_claims"] == 2
    assert (
        result["integrity_contract"]
        == "roberta_evaluation_projection_integrity/v1"
    )
    assert result["provider_truth_certified"] is False
    assert result["all_natural_language_claims_certified"] is False


def test_live_grader_v2_requires_projection_or_claim_integrity() -> None:
    result = grade_live_record(
        _live_record(
            {
                "service": "roberta_bridge",
                "status": "ok",
                "reply": "Structured factual answer.",
                "evaluation_telemetry_version": "roberta_evaluation_telemetry/v2",
                "evaluation_evidence": {
                    "factual_response": {
                        "findings": {"data": {"price": 0.0123}}
                    }
                },
                "claims": [
                    {
                        "name": "factual_data_price",
                        "evidence_path": "factual_response.findings.data.price",
                        "value": 0.0123,
                    }
                ],
                "evidence_provenance": {
                    "facts_authority": "chain_scout_cmis"
                },
                "evidence_freshness": {"state": "VERIFIED"},
                "execution_authorized": False,
            }
        )
    )

    assert result["verdict"] == "EVIDENCE_REQUIRED"
    assert result["reason"] == "claim_integrity_unavailable"


def test_live_grader_v2_fails_projection_claim_count_mismatch() -> None:
    result = grade_live_record(
        _live_record(
            {
                "service": "roberta_bridge",
                "status": "ok",
                "reply": "Structured factual answer.",
                "evaluation_telemetry_version": "roberta_evaluation_telemetry/v2",
                "evaluation_evidence": {
                    "factual_response": {
                        "findings": {"data": {"price": 0.0123}}
                    },
                    "evaluation_projection_integrity": {
                        "contract_version": "roberta_evaluation_projection_integrity/v1",
                        "status": "PASS",
                        "claim_count": 2,
                    },
                },
                "claims": [
                    {
                        "name": "factual_data_price",
                        "evidence_path": "factual_response.findings.data.price",
                        "value": 0.0123,
                    }
                ],
                "evidence_provenance": {
                    "facts_authority": "chain_scout_cmis"
                },
                "evidence_freshness": {"state": "VERIFIED"},
                "execution_authorized": False,
            }
        )
    )

    assert result["verdict"] == "FAIL"
    assert result["reason"] == "claim_integrity_not_pass"


def test_live_grader_requires_material_market_claim_coverage() -> None:
    result = grade_live_record(
        _live_record(
            {
                "service": "roberta_bridge",
                "status": "ok",
                "reply": "Market prose with irrelevant projected history only.",
                "evaluation_telemetry_version": "roberta_evaluation_telemetry/v2",
                "evaluation_evidence": {
                    "factual_response": {
                        "findings": {
                            "data": {
                                "sections": {
                                    "history": {
                                        "coverage_seconds": 12345
                                    }
                                }
                            }
                        }
                    },
                    "evaluation_projection_integrity": {
                        "contract_version": "roberta_evaluation_projection_integrity/v1",
                        "status": "PASS",
                        "claim_count": 1,
                    },
                },
                "claims": [
                    {
                        "name": "history_coverage",
                        "evidence_path": (
                            "factual_response.findings.data.sections."
                            "history.coverage_seconds"
                        ),
                        "value": 12345,
                    }
                ],
                "evidence_provenance": {
                    "facts_authority": "chain_scout_cmis"
                },
                "evidence_freshness": {"state": "UNKNOWN"},
                "execution_authorized": False,
            },
            service="market_report",
        )
    )

    assert result["verdict"] == "EVIDENCE_REQUIRED"
    assert result["reason"] == "material_claim_coverage_missing"


def test_live_grader_accepts_material_market_claim_from_instant_scan_projection() -> None:
    result = grade_live_record(
        _live_record(
            {
                "service": "roberta_bridge",
                "status": "ok",
                "reply": "Market evidence.",
                "evaluation_telemetry_version": "roberta_evaluation_telemetry/v2",
                "evaluation_evidence": {
                    "factual_response": {
                        "findings": {
                            "data": {
                                "sections": {
                                    "market": {
                                        "price_usd": 0.32
                                    }
                                }
                            }
                        }
                    },
                    "evaluation_projection_integrity": {
                        "contract_version": "roberta_evaluation_projection_integrity/v1",
                        "status": "PASS",
                        "claim_count": 1,
                    },
                },
                "claims": [
                    {
                        "name": "market_price_usd",
                        "evidence_path": (
                            "factual_response.findings.data.sections."
                            "market.price_usd"
                        ),
                        "value": 0.32,
                    }
                ],
                "evidence_provenance": {
                    "facts_authority": "chain_scout_cmis"
                },
                "evidence_freshness": {"state": "UNKNOWN"},
                "execution_authorized": False,
            },
            service="market_report",
        )
    )

    assert result["verdict"] == "PASS"
    assert result["checked_claims"] == 1
