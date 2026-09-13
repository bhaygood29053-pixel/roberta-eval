import pytest

from roberta_eval.github_promotion import HUMAN_REMEDIATION_REPOSITORY
from roberta_eval.human_checkpoint_history import empty_human_checkpoint_history
from roberta_eval.human_remediation_closure import empty_closure_ledger
from roberta_eval.human_remediation_lifecycle import empty_lifecycle, validate_lifecycle
from roberta_eval.human_remediation_reopen import (
    ADMINISTRATIVE_NON_QUALITY,
    GENUINE_HUMAN_QUALITY_REGRESSION,
    build_reopen_adjudication,
    empty_reopen_adjudication_ledger,
    register_reopen_adjudication,
)
from roberta_eval.human_remediation_reopen_cycle import (
    REOPEN_CHILD_ORIGIN,
    empty_reopen_cycle_promotion_ledger,
    instantiate_reopen_cycle,
    proposal_for_promoted_cycle,
    reopen_cycle_summary,
)
from roberta_eval.human_remediation_terminal import build_terminal_reconciliation

FINGERPRINT = "a" * 64
PROPOSAL_SHA = "b" * 64
CLOSURE_KEY = "c" * 64
VERIFICATION_SHA = "d" * 64
ISSUE_URL = "https://github.com/bhaygood29053-pixel/roberta-langgraph/issues/900"
FAILURE = "technical_language_leak"


def _snapshot(checkpoint_id: str, failure_count: int) -> dict:
    total = 2
    defect_rate = failure_count / total
    pass_count = total - failure_count
    return {
        "human_trend_version": "roberta_human_language_trend/v1",
        "snapshot_id": checkpoint_id,
        "source": f"accepted_checkpoint:{checkpoint_id}",
        "result_count": total,
        "pass_count": pass_count,
        "defect_count": failure_count,
        "pass_rate": pass_count / total,
        "defect_rate": defect_rate,
        "by_service": {
            "pre_trade": {
                "result_count": total,
                "pass_count": pass_count,
                "defect_count": failure_count,
                "pass_rate": pass_count / total,
                "defect_rate": defect_rate,
            }
        },
        "by_response_depth": {},
        "failure_codes": (
            {FAILURE: {"count": failure_count, "rate": defect_rate}}
            if failure_count
            else {}
        ),
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


def _history(fresh_count: int = 1) -> dict:
    history = empty_human_checkpoint_history()
    for sequence, (checkpoint_id, failure_count) in enumerate(
        [
            ("cp-before", 1),
            ("cp-base", 2),
            ("cp-clean", 0),
            ("cp-fresh", fresh_count),
        ],
        start=1,
    ):
        history["checkpoints"].append(
            {
                "sequence": sequence,
                "checkpoint_id": checkpoint_id,
                "corpus_sha256": str(sequence) * 64,
                "snapshot": _snapshot(checkpoint_id, failure_count),
                "quality": {
                    "result_count": 2,
                    "average_overall_score": 1.0,
                    "internal_leakage_count": 0,
                    "advisory_only": True,
                    "factual_authority": False,
                    "ai_judge_used": False,
                    "judge_model_calls": 0,
                    "zero_judge_tokens": True,
                },
            }
        )
    return history


def _parent_lifecycle() -> dict:
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
            "failure_code": FAILURE,
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
    validate_lifecycle(lifecycle)
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
        "failure_code": FAILURE,
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


def _terminal_reopened() -> dict:
    return build_terminal_reconciliation(
        _parent_lifecycle(),
        _closure_ledger(),
        observed_issue_states={900: "open"},
    )


def _adjudication_ledger(classification: str = GENUINE_HUMAN_QUALITY_REGRESSION) -> dict:
    checkpoint_id = "cp-fresh" if classification == GENUINE_HUMAN_QUALITY_REGRESSION else None
    adjudication = build_reopen_adjudication(
        _terminal_reopened(),
        _history(),
        fingerprint=FINGERPRINT,
        owner="Bryant",
        classification=classification,
        approved=True,
        checkpoint_id=checkpoint_id,
    )
    ledger, status = register_reopen_adjudication(
        empty_reopen_adjudication_ledger(), adjudication
    )
    assert status == "APPENDED"
    return ledger


def test_reopen_cycle_requires_explicit_owner_approval() -> None:
    with pytest.raises(ValueError, match="explicit owner approval"):
        instantiate_reopen_cycle(
            _parent_lifecycle(),
            empty_reopen_cycle_promotion_ledger(),
            _adjudication_ledger(),
            _closure_ledger(),
            parent_fingerprint=FINGERPRINT,
            owner="Bryant",
            approved=False,
        )


def test_administrative_reopen_cannot_create_child_cycle() -> None:
    with pytest.raises(ValueError, match="administrative/non-quality"):
        instantiate_reopen_cycle(
            _parent_lifecycle(),
            empty_reopen_cycle_promotion_ledger(),
            _adjudication_ledger(ADMINISTRATIVE_NON_QUALITY),
            _closure_ledger(),
            parent_fingerprint=FINGERPRINT,
            owner="Bryant",
            approved=True,
        )


def test_confirmed_regression_instantiates_one_linked_child_cycle() -> None:
    lifecycle, ledger, result = instantiate_reopen_cycle(
        _parent_lifecycle(),
        empty_reopen_cycle_promotion_ledger(),
        _adjudication_ledger(),
        _closure_ledger(),
        parent_fingerprint=FINGERPRINT,
        owner="Bryant",
        approved=True,
    )
    assert result["status"] == "APPENDED"
    assert result["lifecycle_mutated"] is True
    assert result["automatic_issue_creation"] is False
    assert len(lifecycle["records"]) == 2
    parent, child = lifecycle["records"]
    assert parent["status"] == "RESOLVED"
    assert child["status"] == "PROPOSED"
    assert child["origin_kind"] == REOPEN_CHILD_ORIGIN
    assert [event["stage"] for event in child["events"][:2]] == ["DETECTED", "PROPOSED"]
    lineage = child["lineage"]
    assert lineage["parent_proposal_fingerprint"] == FINGERPRINT
    assert lineage["parent_lifecycle_id"] == parent["lifecycle_id"]
    assert lineage["closure_evidence_key"] == CLOSURE_KEY
    assert lineage["fresh_checkpoint_id"] == "cp-fresh"
    assert lineage["fresh_checkpoint_sequence"] == 4
    assert lineage["targeted_failure_count"] == 1
    assert lineage["adjudicated_by"] == "Bryant"
    assert lineage["cycle_promoted_by"] == "Bryant"
    assert len(ledger["promotions"]) == 1

    proposal = result["child_proposal"]
    assert proposal["proposal_fingerprint"] == child["proposal_fingerprint"]
    assert proposal["human_priority"]["failure_code"] == FAILURE
    assert proposal["current_snapshot_id"] == "cp-fresh"

    summary = reopen_cycle_summary(lifecycle, ledger)
    assert summary["promoted_cycle_count"] == 1
    assert summary["active_reopened_child_count"] == 1
    assert summary["lineages"][0]["child_status"] == "PROPOSED"

    regenerated = proposal_for_promoted_cycle(
        lifecycle, ledger, child_fingerprint=child["proposal_fingerprint"]
    )
    assert regenerated == proposal


def test_exact_duplicate_is_idempotent_and_conflicting_owner_fails_closed() -> None:
    lifecycle, ledger, first = instantiate_reopen_cycle(
        _parent_lifecycle(),
        empty_reopen_cycle_promotion_ledger(),
        _adjudication_ledger(),
        _closure_ledger(),
        parent_fingerprint=FINGERPRINT,
        owner="Bryant",
        approved=True,
    )
    same_lifecycle, same_ledger, duplicate = instantiate_reopen_cycle(
        lifecycle,
        ledger,
        _adjudication_ledger(),
        _closure_ledger(),
        parent_fingerprint=FINGERPRINT,
        owner="Bryant",
        approved=True,
    )
    assert duplicate["status"] == "UNCHANGED"
    assert same_lifecycle == lifecycle
    assert same_ledger == ledger
    assert len(same_lifecycle["records"]) == 2
    assert len(same_ledger["promotions"]) == 1

    with pytest.raises(ValueError, match="conflicting promotion"):
        instantiate_reopen_cycle(
            lifecycle,
            ledger,
            _adjudication_ledger(),
            _closure_ledger(),
            parent_fingerprint=FINGERPRINT,
            owner="OtherOwner",
            approved=True,
        )
    assert first["promotion"]["approved_by"] == "Bryant"


def test_parent_must_remain_resolved_and_closed_evidence_must_match() -> None:
    lifecycle = _parent_lifecycle()
    lifecycle["records"][0]["status"] = "IMPROVED"
    with pytest.raises(ValueError, match="parent lifecycle status RESOLVED"):
        instantiate_reopen_cycle(
            lifecycle,
            empty_reopen_cycle_promotion_ledger(),
            _adjudication_ledger(),
            _closure_ledger(),
            parent_fingerprint=FINGERPRINT,
            owner="Bryant",
            approved=True,
        )

    closure = _closure_ledger()
    closure["closures"][0]["closure_evidence_key"] = "e" * 64
    closure["closures"][0]["approval"]["closure_evidence_key"] = "e" * 64
    with pytest.raises(ValueError, match="matching terminal closure evidence"):
        instantiate_reopen_cycle(
            _parent_lifecycle(),
            empty_reopen_cycle_promotion_ledger(),
            _adjudication_ledger(),
            closure,
            parent_fingerprint=FINGERPRINT,
            owner="Bryant",
            approved=True,
        )
