from __future__ import annotations

import hashlib
import json

import pytest

from roberta_eval.github_promotion import HUMAN_REMEDIATION_REPOSITORY
from roberta_eval.human_checkpoint_history import (
    append_human_checkpoint,
    empty_human_checkpoint_history,
)
from roberta_eval.human_remediation_actions import (
    empty_approval_registry,
    register_approval_result,
)
from roberta_eval.human_remediation_closure import (
    build_closure_approval,
    close_human_remediation,
    empty_closure_ledger,
    load_closure_ledger,
    write_closure_ledger,
)
from roberta_eval.human_remediation_lifecycle import (
    empty_lifecycle,
    record_fix_merged,
    register_proposals,
    sync_promotion_ledger,
    verify_replay,
)
from roberta_eval.human_remediation_promotion import (
    PROMOTION_RESULT_VERSION,
    empty_promotion_ledger,
)
from roberta_eval.human_trends import build_human_trend_snapshot

FINGERPRINT = "a" * 64
EVIDENCE_KEY = "b" * 64
FAILURE_CODE = "technical_language_leak"


def _record(record_id: str, reply: str) -> dict:
    return {
        "record_version": "roberta_eval_run_record/v1",
        "record_id": record_id,
        "case_id": record_id,
        "service": "pre_trade",
        "runtime_status": "ok",
        "response": {"reply": reply, "response_depth": "normal"},
    }


def _checkpoint(checkpoint_id: str, *, defective: bool) -> dict:
    records = [
        _record(
            checkpoint_id,
            "CMIS deterministic risk result says wait."
            if defective
            else "I would wait until I can verify the likely fill.",
        )
    ]
    snapshot = build_human_trend_snapshot(
        records,
        snapshot_id=checkpoint_id,
        source=f"accepted_checkpoint:{checkpoint_id}",
    )
    return {
        "checkpoint_id": checkpoint_id,
        "corpus_sha256": hashlib.sha256(checkpoint_id.encode()).hexdigest(),
        "snapshot": snapshot,
        "quality": {
            "result_count": 1,
            "average_overall_score": 100.0,
            "internal_leakage_count": 1 if defective else 0,
            "advisory_only": True,
            "factual_authority": False,
            "ai_judge_used": False,
            "judge_model_calls": 0,
            "zero_judge_tokens": True,
        },
    }


def _proposal() -> dict:
    return {
        "proposal_version": "roberta_github_defect_proposal/v1",
        "proposal_kind": "human_language_remediation",
        "proposal_fingerprint": FINGERPRINT,
        "target_repository": HUMAN_REMEDIATION_REPOSITORY,
        "routing_status": "routed",
        "title": "[ROBERTA Lab][Human v2] pre_trade: technical language",
        "body": "Human remediation proposal",
        "labels": ["roberta-lab", "human-v2"],
        "confirmed": True,
        "confirmation_basis": "accepted_human_checkpoint_or_explicit_trend",
        "human_priority": {
            "failure_code": FAILURE_CODE,
            "recurrence": "RECURRENT",
            "service": "pre_trade",
            "current_rate": 1.0,
            "current_count": 1,
        },
        "previous_snapshot_id": "cp-prev",
        "current_snapshot_id": "cp-base",
        "source_mode": "accepted_checkpoint_history",
        "reviewable_proposal_only": True,
        "issue_created": False,
        "production_mutation": False,
        "ai_judge_used": False,
        "judge_model_calls": 0,
        "external_calls": 0,
        "zero_judge_tokens": True,
        "execution_authorized": False,
    }


def _approval_result(proposal_sha: str) -> dict:
    return {
        "promotion_result_version": PROMOTION_RESULT_VERSION,
        "status": "APPROVED_DRY_RUN",
        "issue_created": False,
        "target_repository": HUMAN_REMEDIATION_REPOSITORY,
        "approval": {
            "approval_version": "roberta_human_remediation_approval/v1",
            "approved": True,
            "approved_by": "Bryant",
            "proposal_fingerprint": FINGERPRINT,
            "proposal_sha256": proposal_sha,
            "evidence_key": EVIDENCE_KEY,
            "target_repository": HUMAN_REMEDIATION_REPOSITORY,
            "previous_snapshot_id": "cp-prev",
            "current_snapshot_id": "cp-base",
            "failure_code": FAILURE_CODE,
            "recurrence": "RECURRENT",
            "service": "pre_trade",
            "production_code_mutation": False,
            "execution_authorized": False,
        },
        "production_code_mutation": False,
        "execution_authorized": False,
    }


def _promotion_ledger(proposal_sha: str) -> dict:
    ledger = empty_promotion_ledger()
    approval = _approval_result(proposal_sha)["approval"]
    ledger["promotions"].append(
        {
            "sequence": 1,
            "proposal_fingerprint": FINGERPRINT,
            "evidence_key": EVIDENCE_KEY,
            "proposal_sha256": proposal_sha,
            "approval": approval,
            "target_repository": HUMAN_REMEDIATION_REPOSITORY,
            "issue_created": True,
            "issue_number": 900,
            "issue_url": "https://github.com/bhaygood29053-pixel/roberta-langgraph/issues/900",
            "production_code_mutation": False,
            "execution_authorized": False,
        }
    )
    return ledger


def _resolved_state() -> tuple[dict, dict, dict, dict]:
    lifecycle, _ = register_proposals(empty_lifecycle(), [_proposal()])
    proposal_sha = lifecycle["records"][0]["proposal_sha256"]
    approvals, _ = register_approval_result(
        empty_approval_registry(), _approval_result(proposal_sha)
    )
    promotions = _promotion_ledger(proposal_sha)
    lifecycle, _ = sync_promotion_ledger(lifecycle, promotions)

    history = empty_human_checkpoint_history()
    history, _ = append_human_checkpoint(history, _checkpoint("cp-prev", defective=False))
    history, _ = append_human_checkpoint(history, _checkpoint("cp-base", defective=True))
    lifecycle, _ = record_fix_merged(
        lifecycle,
        history,
        fingerprint=FINGERPRINT,
        repository=HUMAN_REMEDIATION_REPOSITORY,
        pr_number=901,
        merge_sha="1" * 40,
        verified_by="Bryant",
    )
    history, _ = append_human_checkpoint(history, _checkpoint("cp-clean", defective=False))
    lifecycle, result = verify_replay(
        lifecycle, history, fingerprint=FINGERPRINT, checkpoint_id="cp-clean"
    )
    assert result["outcome"] == "RESOLVED"
    return lifecycle, history, approvals, promotions


class FakeCloser:
    def __init__(self, *, fail: bool = False) -> None:
        self.calls = 0
        self.fail = fail

    def close_issue(self, *, repository: str, issue_number: int) -> dict:
        self.calls += 1
        assert repository == HUMAN_REMEDIATION_REPOSITORY
        assert issue_number == 900
        if self.fail:
            raise RuntimeError("simulated GitHub close failure")
        return {
            "number": issue_number,
            "state": "closed",
            "state_reason": "completed",
            "html_url": f"https://github.com/{repository}/issues/{issue_number}",
        }


def _ledger_path(tmp_path):
    path = tmp_path / "closures.json"
    write_closure_ledger(path, empty_closure_ledger())
    return path


def test_non_resolved_remediation_cannot_be_approved_for_closure() -> None:
    lifecycle, _ = register_proposals(empty_lifecycle(), [_proposal()])
    history = empty_human_checkpoint_history()
    history, _ = append_human_checkpoint(history, _checkpoint("cp-prev", defective=False))
    history, _ = append_human_checkpoint(history, _checkpoint("cp-base", defective=True))
    proposal_sha = lifecycle["records"][0]["proposal_sha256"]
    approvals, _ = register_approval_result(empty_approval_registry(), _approval_result(proposal_sha))
    promotions = _promotion_ledger(proposal_sha)

    with pytest.raises(ValueError, match="premature"):
        build_closure_approval(
            lifecycle,
            history,
            approvals,
            promotions,
            fingerprint=FINGERPRINT,
            reviewer="Bryant",
            approved=True,
        )


def test_resolved_closure_dry_run_is_explicit_and_non_mutating(tmp_path) -> None:
    lifecycle, history, approvals, promotions = _resolved_state()
    closer = FakeCloser()
    path = _ledger_path(tmp_path)
    result = close_human_remediation(
        lifecycle,
        history,
        approvals,
        promotions,
        fingerprint=FINGERPRINT,
        reviewer="Bryant",
        approved=True,
        close_issue=False,
        closure_ledger_path=path,
        transport=closer,
    )
    assert result["status"] == "APPROVED_DRY_RUN"
    assert result["issue_closed"] is False
    assert result["github_issue_state_mutation"] is False
    assert result["approval"]["resolved_checkpoint_id"] == "cp-clean"
    assert result["approval"]["targeted_failure_count"] == 0
    assert closer.calls == 0
    assert load_closure_ledger(path)["closures"] == []


def test_explicit_close_writes_ledger_only_after_confirmed_close_and_is_idempotent(tmp_path) -> None:
    lifecycle, history, approvals, promotions = _resolved_state()
    closer = FakeCloser()
    path = _ledger_path(tmp_path)
    result = close_human_remediation(
        lifecycle,
        history,
        approvals,
        promotions,
        fingerprint=FINGERPRINT,
        reviewer="Bryant",
        approved=True,
        close_issue=True,
        closure_ledger_path=path,
        transport=closer,
    )
    assert result["status"] == "CLOSED"
    assert result["issue_closed"] is True
    assert result["github_issue_state_mutation"] is True
    assert result["external_calls"] == 1
    assert closer.calls == 1
    ledger = load_closure_ledger(path)
    assert ledger["closures"][0]["issue_state"] == "closed"
    assert ledger["closures"][0]["approval"]["resolved_checkpoint_id"] == "cp-clean"

    duplicate = close_human_remediation(
        lifecycle,
        history,
        approvals,
        promotions,
        fingerprint=FINGERPRINT,
        reviewer="Bryant",
        approved=True,
        close_issue=True,
        closure_ledger_path=path,
        transport=closer,
    )
    assert duplicate["status"] == "ALREADY_CLOSED"
    assert duplicate["github_issue_state_mutation"] is False
    assert closer.calls == 1


def test_conflicting_closure_evidence_fails_closed(tmp_path) -> None:
    lifecycle, history, approvals, promotions = _resolved_state()
    path = _ledger_path(tmp_path)
    closer = FakeCloser()
    close_human_remediation(
        lifecycle,
        history,
        approvals,
        promotions,
        fingerprint=FINGERPRINT,
        reviewer="Bryant",
        approved=True,
        close_issue=True,
        closure_ledger_path=path,
        transport=closer,
    )
    ledger = load_closure_ledger(path)
    ledger["closures"][0]["closure_evidence_key"] = "c" * 64
    ledger["closures"][0]["approval"]["closure_evidence_key"] = "c" * 64
    write_closure_ledger(path, ledger)

    with pytest.raises(ValueError, match="conflicts with current resolved evidence"):
        close_human_remediation(
            lifecycle,
            history,
            approvals,
            promotions,
            fingerprint=FINGERPRINT,
            reviewer="Bryant",
            approved=True,
            close_issue=True,
            closure_ledger_path=path,
            transport=closer,
        )
    assert closer.calls == 1


def test_failed_close_does_not_write_closure_ledger(tmp_path) -> None:
    lifecycle, history, approvals, promotions = _resolved_state()
    path = _ledger_path(tmp_path)
    closer = FakeCloser(fail=True)
    with pytest.raises(RuntimeError, match="simulated GitHub close failure"):
        close_human_remediation(
            lifecycle,
            history,
            approvals,
            promotions,
            fingerprint=FINGERPRINT,
            reviewer="Bryant",
            approved=True,
            close_issue=True,
            closure_ledger_path=path,
            transport=closer,
        )
    assert closer.calls == 1
    assert load_closure_ledger(path)["closures"] == []


def test_missing_explicit_approval_fails_before_any_close(tmp_path) -> None:
    lifecycle, history, approvals, promotions = _resolved_state()
    closer = FakeCloser()
    with pytest.raises(ValueError, match="explicit owner approval"):
        close_human_remediation(
            lifecycle,
            history,
            approvals,
            promotions,
            fingerprint=FINGERPRINT,
            reviewer="Bryant",
            approved=False,
            close_issue=True,
            closure_ledger_path=_ledger_path(tmp_path),
            transport=closer,
        )
    assert closer.calls == 0
