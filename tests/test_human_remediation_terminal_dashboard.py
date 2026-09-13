from roberta_eval.dashboard import build_dashboard, render_markdown
from roberta_eval.stress import run_stress_qualification


def _terminal_queue(consistency: str = "NOT_CHECKED") -> dict:
    item = {
        "proposal_fingerprint": "a" * 64,
        "terminal_state": "CLOSED",
        "lifecycle_status": "RESOLVED",
        "failure_code": "technical_language_leak",
        "service": "pre_trade",
        "issue_number": 900,
        "issue_url": "https://github.com/bhaygood29053-pixel/roberta-langgraph/issues/900",
        "closure_evidence_key": "c" * 64,
        "closed_by": "Bryant",
        "resolved_checkpoint_id": "cp-clean",
        "resolved_checkpoint_sequence": 3,
        "targeted_failure_count": 0,
        "targeted_failure_rate": 0.0,
        "resolved_verification_sha256": "d" * 64,
        "observed_issue_state": "open" if consistency == "REOPENED_INCONSISTENCY" else None,
        "consistency": consistency,
        "evidence_preserved": True,
        "production_code_mutation": False,
        "execution_authorized": False,
    }
    return {
        "action_queue_version": "roberta_human_remediation_action_queue/v1",
        "record_count": 1,
        "active_count": 0,
        "closure_ready_count": 0,
        "action_counts": {
            "APPROVE_PROPOSAL": 0,
            "CREATE_ISSUE": 0,
            "FIX_ISSUE": 0,
            "ACCEPT_NEW_CHECKPOINT": 0,
            "REPLAY_AGAIN": 0,
            "CLOSE_AS_RESOLVED": 0,
        },
        "items": [],
        "terminal_closed_count": 1,
        "reopened_inconsistency_count": 1 if consistency == "REOPENED_INCONSISTENCY" else 0,
        "terminal": [item],
        "inconsistencies": [item] if consistency == "REOPENED_INCONSISTENCY" else [],
        "terminal_state": "CLOSED",
        "deterministic": True,
        "read_only": True,
        "ai_judge_used": False,
        "judge_model_calls": 0,
        "external_calls": 0,
        "zero_judge_tokens": True,
        "auto_close_issue": False,
        "production_code_mutation": False,
        "execution_authorized": False,
    }


def _lifecycle_summary() -> dict:
    return {
        "record_count": 1,
        "status_counts": {"RESOLVED": 1},
        "active_count": 0,
        "verified_count": 1,
        "improved_count": 0,
        "resolved_count": 1,
        "active": [],
    }


def test_dashboard_surfaces_terminal_closed_and_removes_active_action() -> None:
    view = build_dashboard(
        qualification=run_stress_qualification(limit=50),
        human_remediation_lifecycle=_lifecycle_summary(),
        human_remediation_action_queue=_terminal_queue(),
    )
    actions = view["human_remediation_actions"]
    assert actions["active_count"] == 0
    assert actions["terminal_closed_count"] == 1
    assert actions["items"] == []
    markdown = render_markdown(view)
    assert "Terminal CLOSED: 1" in markdown
    assert "### Terminal CLOSED remediations" in markdown
    assert "resolved checkpoint `cp-clean`" in markdown


def test_dashboard_surfaces_reopened_inconsistency_without_reactivating() -> None:
    view = build_dashboard(
        qualification=run_stress_qualification(limit=50),
        human_remediation_lifecycle=_lifecycle_summary(),
        human_remediation_action_queue=_terminal_queue("REOPENED_INCONSISTENCY"),
    )
    actions = view["human_remediation_actions"]
    assert actions["active_count"] == 0
    assert actions["terminal_closed_count"] == 1
    assert actions["reopened_inconsistency_count"] == 1
    markdown = render_markdown(view)
    assert "Reopened inconsistencies: 1" in markdown
    assert "REOPENED_INCONSISTENCY" in markdown
    assert "prior CLOSED/RESOLVED evidence is preserved" in markdown
