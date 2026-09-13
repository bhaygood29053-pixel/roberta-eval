from __future__ import annotations

import hashlib

from roberta_eval.github_promotion import HUMAN_REMEDIATION_REPOSITORY
from roberta_eval.human_checkpoint_history import (
    append_human_checkpoint,
    empty_human_checkpoint_history,
)
from roberta_eval.human_remediation_actions import (
    build_action_queue,
    closure_gate,
    empty_approval_registry,
    register_approval_result,
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
        "corpus_sha256": hashlib.sha256(checkpoint_id.encode("utf-8")).hexdigest(),
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


def _history() -> dict:
    history = empty_human_checkpoint_history()
    history, _ = append_human_checkpoint(history, _checkpoint("cp-prev", defective=False))
    history, _ = append_human_checkpoint(history, _checkpoint("cp-base", defective=True))
    return history


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


def _approval_result(proposal_sha256: str) -> dict:
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
            "proposal_sha256": proposal_sha256,
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


def _promotion_ledger(proposal_sha256: str) -> dict:
    ledger = empty_promotion_ledger()
    approval = _approval_result(proposal_sha256)["approval"]
    ledger["promotions"].append(
        {
            "sequence": 1,
            "proposal_fingerprint": FINGERPRINT,
            "evidence_key": EVIDENCE_KEY,
            "proposal_sha256": proposal_sha256,
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


def _queue_action(lifecycle: dict, history: dict, approvals: dict, promotions: dict) -> dict:
    queue = build_action_queue(lifecycle, history, approvals, promotions)
    assert queue["record_count"] == 1
    assert queue["judge_model_calls"] == 0
    assert queue["external_calls"] == 0
    return queue["items"][0]


def test_action_queue_progression_and_closure_gate() -> None:
    proposal = _proposal()
    lifecycle, result = register_proposals(empty_lifecycle(), [proposal])
    assert result["appended"] == 1
    history = _history()
    approvals = empty_approval_registry()
    promotions = empty_promotion_ledger()

    item = _queue_action(lifecycle, history, approvals, promotions)
    assert item["next_action"] == "APPROVE_PROPOSAL"
    assert item["closure_ready"] is False

    proposal_sha = lifecycle["records"][0]["proposal_sha256"]
    approvals, status = register_approval_result(approvals, _approval_result(proposal_sha))
    assert status == "APPENDED"
    item = _queue_action(lifecycle, history, approvals, promotions)
    assert item["effective_stage"] == "APPROVED"
    assert item["next_action"] == "CREATE_ISSUE"

    promotions = _promotion_ledger(proposal_sha)
    item = _queue_action(lifecycle, history, approvals, promotions)
    assert item["next_action"] == "FIX_ISSUE"
    assert item["issue_number"] == 900

    lifecycle, sync = sync_promotion_ledger(lifecycle, promotions)
    assert sync["advanced"] == 1
    lifecycle, status = record_fix_merged(
        lifecycle,
        history,
        fingerprint=FINGERPRINT,
        repository=HUMAN_REMEDIATION_REPOSITORY,
        pr_number=901,
        merge_sha="1" * 40,
        verified_by="Bryant",
    )
    assert status == "APPENDED"
    item = _queue_action(lifecycle, history, approvals, promotions)
    assert item["next_action"] == "ACCEPT_NEW_CHECKPOINT"

    history, _ = append_human_checkpoint(history, _checkpoint("cp-after-defect", defective=True))
    item = _queue_action(lifecycle, history, approvals, promotions)
    assert item["next_action"] == "REPLAY_AGAIN"

    lifecycle, verification = verify_replay(
        lifecycle,
        history,
        fingerprint=FINGERPRINT,
        checkpoint_id="cp-after-defect",
    )
    assert verification["outcome"] == "REPLAY_VERIFIED"
    item = _queue_action(lifecycle, history, approvals, promotions)
    assert item["next_action"] == "ACCEPT_NEW_CHECKPOINT"

    blocked = closure_gate(
        lifecycle,
        history,
        approvals,
        promotions,
        fingerprint=FINGERPRINT,
    )
    assert blocked["status"] == "BLOCKED"
    assert blocked["closure_ready"] is False
    assert "is not RESOLVED" in blocked["blockers"][0]

    history, _ = append_human_checkpoint(history, _checkpoint("cp-clean", defective=False))
    item = _queue_action(lifecycle, history, approvals, promotions)
    assert item["next_action"] == "REPLAY_AGAIN"

    lifecycle, verification = verify_replay(
        lifecycle,
        history,
        fingerprint=FINGERPRINT,
        checkpoint_id="cp-clean",
    )
    assert verification["outcome"] == "RESOLVED"
    item = _queue_action(lifecycle, history, approvals, promotions)
    assert item["next_action"] == "CLOSE_AS_RESOLVED"
    assert item["closure_ready"] is True

    ready = closure_gate(
        lifecycle,
        history,
        approvals,
        promotions,
        fingerprint=FINGERPRINT,
    )
    assert ready["status"] == "READY_TO_CLOSE"
    assert ready["closure_ready"] is True
    assert ready["blockers"] == []


def test_approval_registry_is_idempotent_and_conflicts_fail_closed() -> None:
    lifecycle, _ = register_proposals(empty_lifecycle(), [_proposal()])
    proposal_sha = lifecycle["records"][0]["proposal_sha256"]
    result = _approval_result(proposal_sha)
    registry, status = register_approval_result(empty_approval_registry(), result)
    assert status == "APPENDED"
    same, status = register_approval_result(registry, result)
    assert status == "UNCHANGED"
    assert same == registry
