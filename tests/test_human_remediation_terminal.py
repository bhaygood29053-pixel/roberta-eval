import pytest

from roberta_eval.github_promotion import HUMAN_REMEDIATION_REPOSITORY
from roberta_eval.human_checkpoint_history import empty_human_checkpoint_history
from roberta_eval.human_remediation_actions import empty_approval_registry
from roberta_eval.human_remediation_closure import empty_closure_ledger
from roberta_eval.human_remediation_lifecycle import empty_lifecycle
from roberta_eval.human_remediation_promotion import empty_promotion_ledger
from roberta_eval.human_remediation_terminal import (
    build_terminal_action_queue,
    build_terminal_reconciliation,
    reconcile_github_issue_states,
)

FINGERPRINT = "a" * 64
PROPOSAL_SHA = "b" * 64
CLOSURE_KEY = "c" * 64
VERIFICATION_SHA = "d" * 64
ISSUE_URL = "https://github.com/bhaygood29053-pixel/roberta-langgraph/issues/900"


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
            "failure_code": "technical_language_leak",
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
        "failure_code": "technical_language_leak",
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


class FakeIssueState:
    def __init__(self, state: str) -> None:
        self.state = state
        self.calls = 0

    def get_issue(self, repository: str, issue_number: int) -> dict:
        self.calls += 1
        return {
            "repository": repository,
            "issue_number": issue_number,
            "issue_url": ISSUE_URL,
            "state": self.state,
        }


def test_closed_ledger_creates_terminal_record_and_removes_active_action() -> None:
    lifecycle = _lifecycle()
    ledger = _closure_ledger()
    terminal = build_terminal_reconciliation(lifecycle, ledger)
    assert terminal["closed_count"] == 1
    assert terminal["terminal"][0]["terminal_state"] == "CLOSED"
    assert terminal["terminal"][0]["consistency"] == "NOT_CHECKED"
    assert terminal["terminal"][0]["closure_evidence_key"] == CLOSURE_KEY
    assert terminal["terminal"][0]["resolved_checkpoint_id"] == "cp-clean"
    assert terminal["terminal"][0]["evidence_preserved"] is True

    queue = build_terminal_action_queue(
        lifecycle,
        empty_human_checkpoint_history(),
        empty_approval_registry(),
        empty_promotion_ledger(),
        ledger,
    )
    assert queue["record_count"] == 1
    assert queue["active_count"] == 0
    assert queue["items"] == []
    assert queue["terminal_closed_count"] == 1
    assert queue["closure_ready_count"] == 0
    assert queue["action_counts"]["CLOSE_AS_RESOLVED"] == 0


def test_explicit_reconciliation_detects_closed_and_reopened_without_rewriting_evidence() -> None:
    lifecycle = _lifecycle()
    ledger = _closure_ledger()

    closed_transport = FakeIssueState("closed")
    closed = reconcile_github_issue_states(lifecycle, ledger, closed_transport)
    assert closed_transport.calls == 1
    assert closed["terminal"][0]["consistency"] == "CONSISTENT_CLOSED"
    assert closed["reopened_inconsistency_count"] == 0

    open_transport = FakeIssueState("open")
    reopened = reconcile_github_issue_states(lifecycle, ledger, open_transport)
    assert open_transport.calls == 1
    assert reopened["terminal"][0]["terminal_state"] == "CLOSED"
    assert reopened["terminal"][0]["consistency"] == "REOPENED_INCONSISTENCY"
    assert reopened["reopened_inconsistency_count"] == 1
    assert reopened["evidence_rewritten"] is False
    assert reopened["terminal"][0]["closure_evidence_key"] == CLOSURE_KEY


def test_conflicting_closure_identity_fails_closed() -> None:
    lifecycle = _lifecycle()
    ledger = _closure_ledger()
    ledger["closures"][0]["issue_number"] = 901
    ledger["closures"][0]["approval"]["issue_number"] = 901
    with pytest.raises(ValueError, match="issue number mismatch"):
        build_terminal_reconciliation(lifecycle, ledger)
