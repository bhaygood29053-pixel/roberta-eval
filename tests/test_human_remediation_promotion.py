import json
from pathlib import Path

import pytest

from roberta_eval.human_remediation_promotion import (
    build_approval_receipt,
    empty_promotion_ledger,
    load_promotion_ledger,
    promote_human_proposal,
    promotion_ledger_summary,
    select_human_proposal,
    validate_human_remediation_proposal,
    write_promotion_ledger,
)


TARGET_REPO = "bhaygood29053-pixel/roberta-langgraph"


def _proposal(**overrides):
    base = {
        "proposal_version": "roberta_github_defect_proposal/v1",
        "proposal_kind": "human_language_remediation",
        "proposal_fingerprint": "a" * 64,
        "target_repository": TARGET_REPO,
        "routing_status": "routed",
        "title": "[ROBERTA Lab][Human v2] pre_trade: technical_language_leak (RECURRENT)",
        "body": "Human remediation proposal body",
        "labels": ["roberta-lab", "defect", "human-v2", "language-quality"],
        "confirmed": True,
        "confirmation_basis": "accepted_human_checkpoint_or_explicit_trend",
        "human_priority": {
            "failure_code": "technical_language_leak",
            "recurrence": "RECURRENT",
            "current_rate": 0.25,
            "current_count": 5,
            "service": "pre_trade",
        },
        "previous_snapshot_id": "human-v2-001",
        "current_snapshot_id": "human-v2-002",
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
    base.update(overrides)
    return base


def _ledger_path(tmp_path: Path) -> Path:
    path = tmp_path / "promotion-ledger.json"
    write_promotion_ledger(path, empty_promotion_ledger())
    return path


class FakeIssueTransport:
    def __init__(self, *, fail: bool = False):
        self.calls = []
        self.fail = fail

    def create_issue(self, *, repository: str, title: str, body: str):
        self.calls.append({"repository": repository, "title": title, "body": body})
        if self.fail:
            raise RuntimeError("simulated create failure")
        return {
            "number": 777,
            "html_url": "https://github.com/bhaygood29053-pixel/roberta-langgraph/issues/777",
        }


def test_unapproved_promotion_is_rejected(tmp_path: Path) -> None:
    path = _ledger_path(tmp_path)
    with pytest.raises(ValueError, match="explicit approval"):
        promote_human_proposal(
            _proposal(),
            reviewer="owner",
            approved=False,
            create_issue=False,
            ledger_path=path,
        )
    assert promotion_ledger_summary(load_promotion_ledger(path))["promotion_count"] == 0


def test_wrong_proposal_kind_or_repository_is_rejected() -> None:
    with pytest.raises(ValueError, match="not a Human language remediation"):
        validate_human_remediation_proposal(_proposal(proposal_kind="deterministic_defect_cluster"))
    with pytest.raises(ValueError, match="target repository is not allowed"):
        validate_human_remediation_proposal(_proposal(target_repository="bhaygood29053-pixel/cmis"))


def test_approval_receipt_binds_checkpoint_evidence() -> None:
    proposal = _proposal()
    receipt = build_approval_receipt(proposal, reviewer="Bryant", approved=True)
    assert receipt["approved"] is True
    assert receipt["approved_by"] == "Bryant"
    assert receipt["proposal_fingerprint"] == proposal["proposal_fingerprint"]
    assert receipt["previous_snapshot_id"] == "human-v2-001"
    assert receipt["current_snapshot_id"] == "human-v2-002"
    assert receipt["failure_code"] == "technical_language_leak"
    assert receipt["service"] == "pre_trade"
    assert len(receipt["proposal_sha256"]) == 64
    assert len(receipt["evidence_key"]) == 64
    assert receipt["production_code_mutation"] is False
    assert receipt["execution_authorized"] is False


def test_approved_dry_run_does_not_create_issue_or_write_ledger(tmp_path: Path) -> None:
    path = _ledger_path(tmp_path)
    result = promote_human_proposal(
        _proposal(),
        reviewer="Bryant",
        approved=True,
        create_issue=False,
        ledger_path=path,
    )
    assert result["status"] == "APPROVED_DRY_RUN"
    assert result["issue_created"] is False
    assert "Proposal fingerprint" in result["body"]
    assert "Approved by: `Bryant`" in result["body"]
    assert promotion_ledger_summary(load_promotion_ledger(path))["promotion_count"] == 0


def test_approved_create_writes_one_immutable_promotion(tmp_path: Path) -> None:
    path = _ledger_path(tmp_path)
    transport = FakeIssueTransport()
    result = promote_human_proposal(
        _proposal(),
        reviewer="Bryant",
        approved=True,
        create_issue=True,
        ledger_path=path,
        transport=transport,
    )
    assert result["status"] == "PROMOTED"
    assert result["issue_created"] is True
    assert result["issue_number"] == 777
    assert len(transport.calls) == 1
    assert transport.calls[0]["repository"] == TARGET_REPO
    assert "Current checkpoint: `human-v2-002`" in transport.calls[0]["body"]

    ledger = load_promotion_ledger(path)
    assert promotion_ledger_summary(ledger)["promotion_count"] == 1
    entry = ledger["promotions"][0]
    assert entry["proposal_fingerprint"] == "a" * 64
    assert entry["issue_number"] == 777
    assert entry["approval"]["approved_by"] == "Bryant"
    assert entry["production_code_mutation"] is False
    assert entry["execution_authorized"] is False
    serialized = json.dumps(ledger)
    assert "Human remediation proposal body" not in serialized


def test_duplicate_promotion_returns_existing_issue_without_second_create(tmp_path: Path) -> None:
    path = _ledger_path(tmp_path)
    first_transport = FakeIssueTransport()
    promote_human_proposal(
        _proposal(),
        reviewer="Bryant",
        approved=True,
        create_issue=True,
        ledger_path=path,
        transport=first_transport,
    )

    second_transport = FakeIssueTransport()
    second = promote_human_proposal(
        _proposal(),
        reviewer="Bryant",
        approved=True,
        create_issue=True,
        ledger_path=path,
        transport=second_transport,
    )
    assert second["status"] == "ALREADY_PROMOTED"
    assert second["issue_number"] == 777
    assert second_transport.calls == []
    assert promotion_ledger_summary(load_promotion_ledger(path))["promotion_count"] == 1


def test_conflicting_proposal_for_same_checkpoint_evidence_fails_closed(tmp_path: Path) -> None:
    path = _ledger_path(tmp_path)
    promote_human_proposal(
        _proposal(),
        reviewer="Bryant",
        approved=True,
        create_issue=True,
        ledger_path=path,
        transport=FakeIssueTransport(),
    )
    conflicting = _proposal(
        proposal_fingerprint="b" * 64,
        title="tampered title",
    )
    with pytest.raises(ValueError, match="conflicts with current proposal content"):
        promote_human_proposal(
            conflicting,
            reviewer="Bryant",
            approved=True,
            create_issue=True,
            ledger_path=path,
            transport=FakeIssueTransport(),
        )
    assert promotion_ledger_summary(load_promotion_ledger(path))["promotion_count"] == 1


def test_failed_issue_creation_does_not_write_promotion_ledger(tmp_path: Path) -> None:
    path = _ledger_path(tmp_path)
    with pytest.raises(RuntimeError, match="simulated create failure"):
        promote_human_proposal(
            _proposal(),
            reviewer="Bryant",
            approved=True,
            create_issue=True,
            ledger_path=path,
            transport=FakeIssueTransport(fail=True),
        )
    assert promotion_ledger_summary(load_promotion_ledger(path))["promotion_count"] == 0


def test_select_human_proposal_requires_fingerprint_when_ambiguous() -> None:
    proposals = [_proposal(), _proposal(proposal_fingerprint="b" * 64)]
    with pytest.raises(ValueError, match="fingerprint is required"):
        select_human_proposal(proposals)
    selected = select_human_proposal(proposals, fingerprint="b" * 64)
    assert selected["proposal_fingerprint"] == "b" * 64
