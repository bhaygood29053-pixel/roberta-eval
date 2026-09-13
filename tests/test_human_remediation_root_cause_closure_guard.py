from __future__ import annotations

import pytest

import roberta_eval.human_remediation_closure_guard as guard


def _args():
    return ({"records": []}, {"checkpoints": []}, {"approvals": []}, {"promotions": []}, {"promotions": []}, {"investigations": [], "dispositions": []})


def test_official_close_guard_blocks_before_closure_when_root_cause_gate_is_not_sufficient(monkeypatch) -> None:
    called = {"close": 0}
    monkeypatch.setattr(guard, "build_generational_lineage_report", lambda lifecycle, reopen: {"report": True})
    monkeypatch.setattr(
        guard,
        "root_cause_sufficiency_gate",
        lambda lineage, ledger, fingerprint: {
            "status": "BLOCKED_FINDINGS_UNADDRESSED",
            "closure_sufficient": False,
            "blockers": ["root-cause investigation findings are unaddressed"],
        },
    )

    def fake_close(*args, **kwargs):
        called["close"] += 1
        return {"status": "CLOSED"}

    monkeypatch.setattr(guard, "close_human_remediation", fake_close)
    lifecycle, history, approvals, promotions, reopen, root_cause = _args()
    with pytest.raises(ValueError, match="root-cause investigation gate"):
        guard.guarded_close_human_remediation(
            lifecycle,
            history,
            approvals,
            promotions,
            reopen,
            root_cause,
            fingerprint="a" * 64,
            reviewer="Bryant",
            approved=True,
            close_issue=True,
        )
    assert called["close"] == 0


def test_official_close_guard_allows_original_closure_only_after_sufficiency_passes(monkeypatch) -> None:
    called = {"close": 0}
    accepted_gate = {
        "status": "ROOT_CAUSE_FINDINGS_ADDRESSED",
        "closure_sufficient": True,
        "blockers": [],
        "package_id": "b" * 64,
        "disposition_id": "c" * 64,
    }
    monkeypatch.setattr(guard, "build_generational_lineage_report", lambda lifecycle, reopen: {"report": True})
    monkeypatch.setattr(
        guard,
        "root_cause_sufficiency_gate",
        lambda lineage, ledger, fingerprint: accepted_gate,
    )

    def fake_close(*args, **kwargs):
        called["close"] += 1
        return {"status": "APPROVED_DRY_RUN", "issue_closed": False}

    monkeypatch.setattr(guard, "close_human_remediation", fake_close)
    lifecycle, history, approvals, promotions, reopen, root_cause = _args()
    result = guard.guarded_close_human_remediation(
        lifecycle,
        history,
        approvals,
        promotions,
        reopen,
        root_cause,
        fingerprint="a" * 64,
        reviewer="Bryant",
        approved=True,
        close_issue=False,
    )
    assert called["close"] == 1
    assert result["status"] == "APPROVED_DRY_RUN"
    assert result["root_cause_sufficiency"] == accepted_gate
