from __future__ import annotations

import hashlib

import pytest

from roberta_eval.human_checkpoint_history import append_human_checkpoint, empty_human_checkpoint_history
from roberta_eval.human_remediation_lifecycle import (
    empty_lifecycle,
    lifecycle_summary,
    record_fix_merged,
    register_proposals,
    sync_promotion_ledger,
    verify_replay,
)
from roberta_eval.human_remediation_promotion import build_approval_receipt, empty_promotion_ledger


def proposal():
    return {
        "proposal_version": "roberta_github_defect_proposal/v1",
        "proposal_kind": "human_language_remediation",
        "proposal_fingerprint": "a" * 64,
        "target_repository": "bhaygood29053-pixel/roberta-langgraph",
        "routing_status": "routed",
        "title": "Human v2 language remediation",
        "body": "review-only remediation proposal",
        "labels": ["human-v2"],
        "confirmed": True,
        "confirmation_basis": "accepted_human_checkpoint_or_explicit_trend",
        "human_priority": {
            "failure_code": "technical_language_leak",
            "recurrence": "RECURRENT",
            "current_rate": 0.5,
            "current_count": 5,
            "service": "pretrade",
        },
        "previous_snapshot_id": "human-001",
        "current_snapshot_id": "human-002",
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


def promotion_ledger(p):
    approval = build_approval_receipt(p, reviewer="owner", approved=True)
    ledger = empty_promotion_ledger()
    ledger["promotions"].append({
        "sequence": 1,
        "proposal_fingerprint": approval["proposal_fingerprint"],
        "evidence_key": approval["evidence_key"],
        "proposal_sha256": approval["proposal_sha256"],
        "approval": approval,
        "target_repository": "bhaygood29053-pixel/roberta-langgraph",
        "issue_created": True,
        "issue_number": 777,
        "issue_url": "https://github.com/bhaygood29053-pixel/roberta-langgraph/issues/777",
        "production_code_mutation": False,
        "execution_authorized": False,
    })
    return ledger


def checkpoint(checkpoint_id, count, rate):
    total = 10
    return {
        "checkpoint_id": checkpoint_id,
        "corpus_sha256": hashlib.sha256(checkpoint_id.encode()).hexdigest(),
        "snapshot": {
            "human_trend_version": "roberta_human_language_trend/v1",
            "snapshot_id": checkpoint_id,
            "source": f"accepted_checkpoint:{checkpoint_id}",
            "result_count": total,
            "pass_count": total - min(count, total),
            "defect_count": min(count, total),
            "pass_rate": round((total - min(count, total)) / total, 6),
            "defect_rate": round(min(count, total) / total, 6),
            "by_service": {},
            "by_response_depth": {},
            "failure_codes": ({"technical_language_leak": {"count": count, "rate": rate}} if count else {}),
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
        },
        "quality": {
            "result_count": total,
            "average_overall_score": 0.9,
            "internal_leakage_count": count,
            "advisory_only": True,
            "factual_authority": False,
            "ai_judge_used": False,
            "judge_model_calls": 0,
            "zero_judge_tokens": True,
        },
    }


def history(*rows):
    value = empty_human_checkpoint_history()
    for row in rows:
        value, status = append_human_checkpoint(value, row)
        assert status == "APPENDED"
    return value


def through_issue():
    p = proposal()
    lifecycle, _ = register_proposals(empty_lifecycle(), [p])
    lifecycle, _ = sync_promotion_ledger(lifecycle, promotion_ledger(p))
    return lifecycle


def test_register_and_promotion_stages():
    p = proposal()
    lifecycle, result = register_proposals(empty_lifecycle(), [p])
    assert result == {"appended": 1, "unchanged": 0}
    assert [e["stage"] for e in lifecycle["records"][0]["events"]] == ["DETECTED", "PROPOSED"]
    lifecycle, result = sync_promotion_ledger(lifecycle, promotion_ledger(p))
    assert result["advanced"] == 1
    record = lifecycle["records"][0]
    assert record["status"] == "GITHUB_ISSUE"
    assert [e["stage"] for e in record["events"]] == ["DETECTED", "PROPOSED", "APPROVED", "GITHUB_ISSUE"]


def test_fix_does_not_resolve_and_requires_later_checkpoint():
    lifecycle = through_issue()
    before = history(checkpoint("human-001", 4, 0.4), checkpoint("human-002", 5, 0.5))
    lifecycle, status = record_fix_merged(
        lifecycle, before, fingerprint="a" * 64,
        repository="bhaygood29053-pixel/roberta-langgraph",
        pr_number=888, merge_sha="b" * 40, verified_by="owner",
    )
    assert status == "APPENDED"
    assert lifecycle["records"][0]["status"] == "FIX_MERGED"
    assert lifecycle["records"][0]["fix"]["verification_checkpoint_sequence_floor"] == 2
    with pytest.raises(ValueError, match="accepted after FIX_MERGED"):
        verify_replay(lifecycle, before, fingerprint="a" * 64, checkpoint_id="human-002")


def test_later_checkpoint_can_improve_then_resolve():
    lifecycle = through_issue()
    before = history(checkpoint("human-001", 4, 0.4), checkpoint("human-002", 5, 0.5))
    lifecycle, _ = record_fix_merged(
        lifecycle, before, fingerprint="a" * 64,
        repository="bhaygood29053-pixel/roberta-langgraph",
        pr_number=888, merge_sha="b" * 40, verified_by="owner",
    )
    after = history(
        checkpoint("human-001", 4, 0.4), checkpoint("human-002", 5, 0.5),
        checkpoint("human-003", 2, 0.2),
    )
    lifecycle, result = verify_replay(lifecycle, after, fingerprint="a" * 64)
    assert result["outcome"] == "IMPROVED"
    assert lifecycle["records"][0]["status"] == "IMPROVED"

    resolved = history(
        checkpoint("human-001", 4, 0.4), checkpoint("human-002", 5, 0.5),
        checkpoint("human-003", 2, 0.2), checkpoint("human-004", 0, 0.0),
    )
    lifecycle, result = verify_replay(lifecycle, resolved, fingerprint="a" * 64)
    assert result["outcome"] == "RESOLVED"
    assert lifecycle["records"][0]["status"] == "RESOLVED"
    summary = lifecycle_summary(lifecycle)
    assert summary["resolved_count"] == 1
    assert summary["active_count"] == 0


def test_no_improvement_stays_replay_verified():
    lifecycle = through_issue()
    before = history(checkpoint("human-001", 4, 0.4), checkpoint("human-002", 5, 0.5))
    lifecycle, _ = record_fix_merged(
        lifecycle, before, fingerprint="a" * 64,
        repository="bhaygood29053-pixel/roberta-langgraph",
        pr_number=888, merge_sha="b" * 40, verified_by="owner",
    )
    after = history(
        checkpoint("human-001", 4, 0.4), checkpoint("human-002", 5, 0.5),
        checkpoint("human-003", 6, 0.6),
    )
    lifecycle, result = verify_replay(lifecycle, after, fingerprint="a" * 64)
    assert result["outcome"] == "REPLAY_VERIFIED"
    assert lifecycle["records"][0]["status"] == "REPLAY_VERIFIED"
