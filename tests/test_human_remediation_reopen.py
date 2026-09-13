import hashlib

import pytest

from roberta_eval.github_promotion import HUMAN_REMEDIATION_REPOSITORY
from roberta_eval.human_checkpoint_history import (
    append_human_checkpoint,
    empty_human_checkpoint_history,
)
from roberta_eval.human_remediation_closure import empty_closure_ledger
from roberta_eval.human_remediation_lifecycle import empty_lifecycle
from roberta_eval.human_remediation_reopen import (
    ADMINISTRATIVE_NON_QUALITY,
    GENUINE_HUMAN_QUALITY_REGRESSION,
    build_new_cycle_seed,
    build_reopen_adjudication,
    empty_reopen_adjudication_ledger,
    register_reopen_adjudication,
    reopen_adjudication_summary,
)
from roberta_eval.human_remediation_terminal import build_terminal_reconciliation

FINGERPRINT = "a" * 64
PROPOSAL_SHA = "b" * 64
CLOSURE_KEY = "c" * 64
VERIFICATION_SHA = "d" * 64
ISSUE_URL = "https://github.com/bhaygood29053-pixel/roberta-langgraph/issues/900"
FAILURE_CODE = "technical_language_leak"


def _snapshot(checkpoint_id: str, *, count: int = 0, total: int = 2) -> dict:
    rate = round(count / total, 6) if total else 0.0
    failures = {FAILURE_CODE: {"count": count, "rate": rate}} if count else {}
    defect_count = count
    pass_count = max(total - defect_count, 0)
    return {
        "human_trend_version": "roberta_human_language_trend/v1",
        "snapshot_id": checkpoint_id,
        "source": f"accepted_checkpoint:{checkpoint_id}",
        "result_count": total,
        "pass_count": pass_count,
        "defect_count": defect_count,
        "pass_rate": round(pass_count / total, 6) if total else 0.0,
        "defect_rate": rate,
        "by_service": {},
        "by_response_depth": {},
        "failure_codes": failures,
        "source_file_count": 1,
        "unique_response_count": total,
        "duplicate_response_record_count": 0,
        "deterministic": True,
        "advisory_only": True,
        "factual_authority": False,
        "ai_judge_used": False,
        "judge_model_calls": 0,
        "external_calls": 0,
        "zero_judge_tokens": True,
        "execution_authorized": False,
    }


def _checkpoint(checkpoint_id: str, *, count: int = 0) -> dict:
    return {
        "checkpoint_id": checkpoint_id,
        "corpus_sha256": hashlib.sha256(checkpoint_id.encode()).hexdigest(),
        "snapshot": _snapshot(checkpoint_id, count=count),
        "quality": {
            "result_count": 2,
            "average_overall_score": 100.0,
            "internal_leakage_count": count,
            "advisory_only": True,
            "factual_authority": False,
            "ai_judge_used": False,
            "judge_model_calls": 0,
            "zero_judge_tokens": True,
        },
    }


def _history(*, fresh_count: int | None = None) -> dict:
    history = empty_human_checkpoint_history()
    for checkpoint_id, count in (("cp-before", 1), ("cp-base", 1), ("cp-clean", 0)):
        history, _ = append_human_checkpoint(history, _checkpoint(checkpoint_id, count=count))
    if fresh_count is not None:
        history, _ = append_human_checkpoint(history, _checkpoint("cp-fresh", count=fresh_count))
    return history


def _lifecycle() -> dict:
    lifecycle = empty_lifecycle()
    lifecycle["records"] = [
        {
            "sequence": 1,
            "lifecycle_id": f"human-remediation::{FINGERPRINT}",
            "proposal_fingerprint": FINGERPRINT,
            "proposal_sha256": PROPOSAL_SHA,
            "target_repository": HUMAN_REMEDIATION_REPOSITORY,
            "previous_snapshot_id": "cp-before",
            "current_snapshot_id": "cp-base",
            "failure_code": FAILURE_CODE,
            "recurrence": "RECURRENT",
            "service": "pre_trade",
            "baseline_count": 2,
            "baseline_rate": 1.0,
            "status": "RESOLVED",
            "issue_number": 900,
            "issue_url": ISSUE_URL,
            "fix": {
                "repository": HUMAN_REMEDIATION_REPOSITORY,
                "pr_number": 901,
                "merge_sha": "1" * 40,
                "verified_by": "Bryant",
                "verification_checkpoint_sequence_floor": 2,
                "latest_checkpoint_at_fix": "cp-base",
            },
            "verifications": [
                {
                    "checkpoint_id": "cp-clean",
                    "checkpoint_sequence": 3,
                    "targeted_failure_count": 0,
                    "targeted_failure_rate": 0.0,
                    "baseline_failure_count": 2,
                    "baseline_failure_rate": 1.0,
                    "outcome": "RESOLVED",
                    "zero_judge_tokens": True,
                }
            ],
            "events": [
                {"sequence": 1, "stage": "DETECTED", "evidence": {}},
                {"sequence": 2, "stage": "PROPOSED", "evidence": {}},
                {"sequence": 3, "stage": "RESOLVED", "evidence": {}},
            ],
            "production_code_mutation": False,
            "execution_authorized": False,
        }
    ]
    return lifecycle


def _closure_ledger() -> dict:
    ledger = empty_closure_ledger()
    approval = {
        "approval_version": "roberta_human_remediation_closure_approval/v1",
        "approved": True,
        "approved_by": "Bryant",
        "proposal_fingerprint": FINGERPRINT,
        "proposal_sha256": PROPOSAL_SHA,
        "closure_evidence_key": CLOSURE_KEY,
        "target_repository": HUMAN_REMEDIATION_REPOSITORY,
        "issue_number": 900,
        "issue_url": ISSUE_URL,
        "failure_code": FAILURE_CODE,
        "resolved_checkpoint_id": "cp-clean",
        "resolved_checkpoint_sequence": 3,
        "targeted_failure_count": 0,
        "targeted_failure_rate": 0.0,
        "resolved_verification_sha256": VERIFICATION_SHA,
        "closure_gate_status": "READY_TO_CLOSE",
        "production_code_mutation": False,
        "execution_authorized": False,
    }
    ledger["closures"] = [
        {
            "sequence": 1,
            "proposal_fingerprint": FINGERPRINT,
            "closure_evidence_key": CLOSURE_KEY,
            "target_repository": HUMAN_REMEDIATION_REPOSITORY,
            "issue_number": 900,
            "issue_url": ISSUE_URL,
            "issue_closed": True,
            "issue_state": "closed",
            "approval": approval,
            "production_code_mutation": False,
            "execution_authorized": False,
        }
    ]
    return ledger


def _reopened_report() -> dict:
    return build_terminal_reconciliation(
        _lifecycle(),
        _closure_ledger(),
        observed_issue_states={900: "open"},
    )


def test_reopened_inconsistency_requires_explicit_adjudication_and_admin_preserves_closed() -> None:
    report = _reopened_report()
    ledger = empty_reopen_adjudication_ledger()
    summary = reopen_adjudication_summary(ledger, report)
    assert summary["pending_adjudication_count"] == 1

    with pytest.raises(ValueError, match="explicit owner approval"):
        build_reopen_adjudication(
            report,
            _history(),
            fingerprint=FINGERPRINT,
            owner="Bryant",
            classification=ADMINISTRATIVE_NON_QUALITY,
            approved=False,
        )

    admin = build_reopen_adjudication(
        report,
        _history(),
        fingerprint=FINGERPRINT,
        owner="Bryant",
        classification=ADMINISTRATIVE_NON_QUALITY,
        approved=True,
    )
    assert admin["prior_terminal_state"] == "CLOSED"
    assert admin["terminal_evidence_preserved"] is True
    assert admin["new_cycle_eligible"] is False
    assert admin["new_cycle_id"] is None

    ledger, status = register_reopen_adjudication(ledger, admin)
    assert status == "APPENDED"
    same, status = register_reopen_adjudication(ledger, admin)
    assert status == "UNCHANGED"
    assert same == ledger

    summary = reopen_adjudication_summary(ledger, report)
    assert summary["pending_adjudication_count"] == 0
    assert summary["administrative_count"] == 1
    assert summary["new_cycle_eligible_count"] == 0


def test_genuine_regression_requires_fresh_accepted_checkpoint_with_same_defect() -> None:
    report = _reopened_report()

    with pytest.raises(ValueError, match="fresh accepted checkpoint"):
        build_reopen_adjudication(
            report,
            _history(),
            fingerprint=FINGERPRINT,
            owner="Bryant",
            classification=GENUINE_HUMAN_QUALITY_REGRESSION,
            approved=True,
        )

    with pytest.raises(ValueError, match="newer than the prior resolved checkpoint"):
        build_reopen_adjudication(
            report,
            _history(),
            fingerprint=FINGERPRINT,
            owner="Bryant",
            classification=GENUINE_HUMAN_QUALITY_REGRESSION,
            approved=True,
            checkpoint_id="cp-clean",
        )

    with pytest.raises(ValueError, match="does not prove recurrence"):
        build_reopen_adjudication(
            report,
            _history(fresh_count=0),
            fingerprint=FINGERPRINT,
            owner="Bryant",
            classification=GENUINE_HUMAN_QUALITY_REGRESSION,
            approved=True,
            checkpoint_id="cp-fresh",
        )

    regression = build_reopen_adjudication(
        report,
        _history(fresh_count=1),
        fingerprint=FINGERPRINT,
        owner="Bryant",
        classification=GENUINE_HUMAN_QUALITY_REGRESSION,
        approved=True,
        checkpoint_id="cp-fresh",
    )
    assert regression["new_cycle_eligible"] is True
    assert regression["fresh_regression_evidence"]["checkpoint_sequence"] == 4
    assert regression["fresh_regression_evidence"]["targeted_failure_count"] == 1
    assert regression["new_cycle_id"].startswith("human-remediation-reopen::")
    assert regression == build_reopen_adjudication(
        report,
        _history(fresh_count=1),
        fingerprint=FINGERPRINT,
        owner="Bryant",
        classification=GENUINE_HUMAN_QUALITY_REGRESSION,
        approved=True,
        checkpoint_id="cp-fresh",
    )

    ledger, status = register_reopen_adjudication(empty_reopen_adjudication_ledger(), regression)
    assert status == "APPENDED"
    seed = build_new_cycle_seed(ledger, fingerprint=FINGERPRINT)
    assert seed["new_cycle_id"] == regression["new_cycle_id"]
    assert seed["fresh_checkpoint_id"] == "cp-fresh"
    assert seed["new_cycle_eligible"] is True
    assert seed["automatic_new_cycle_creation"] is False


def test_conflicting_reopen_classification_fails_closed() -> None:
    report = _reopened_report()
    admin = build_reopen_adjudication(
        report,
        _history(),
        fingerprint=FINGERPRINT,
        owner="Bryant",
        classification=ADMINISTRATIVE_NON_QUALITY,
        approved=True,
    )
    ledger, _ = register_reopen_adjudication(empty_reopen_adjudication_ledger(), admin)
    regression = build_reopen_adjudication(
        report,
        _history(fresh_count=1),
        fingerprint=FINGERPRINT,
        owner="Bryant",
        classification=GENUINE_HUMAN_QUALITY_REGRESSION,
        approved=True,
        checkpoint_id="cp-fresh",
    )
    with pytest.raises(ValueError, match="conflicting adjudication"):
        register_reopen_adjudication(ledger, regression)


def test_non_reopened_terminal_report_cannot_be_adjudicated() -> None:
    report = build_terminal_reconciliation(_lifecycle(), _closure_ledger())
    with pytest.raises(ValueError, match="REOPENED_INCONSISTENCY"):
        build_reopen_adjudication(
            report,
            _history(),
            fingerprint=FINGERPRINT,
            owner="Bryant",
            classification=ADMINISTRATIVE_NON_QUALITY,
            approved=True,
        )
