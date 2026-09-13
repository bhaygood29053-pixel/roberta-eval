from roberta_eval.dashboard import build_dashboard, render_markdown
from roberta_eval.stress import run_stress_qualification


def test_dashboard_surfaces_action_queue_and_closure_ready_count() -> None:
    lifecycle = {
        "lifecycle_version": "roberta_human_remediation_lifecycle/v1",
        "record_count": 2,
        "status_counts": {
            "DETECTED": 0,
            "PROPOSED": 0,
            "APPROVED": 0,
            "GITHUB_ISSUE": 1,
            "FIX_MERGED": 0,
            "REPLAY_VERIFIED": 0,
            "IMPROVED": 0,
            "RESOLVED": 1,
        },
        "active_count": 1,
        "verified_count": 1,
        "improved_count": 0,
        "resolved_count": 1,
        "active": [
            {
                "proposal_fingerprint": "a" * 64,
                "failure_code": "technical_language_leak",
                "service": "pre_trade",
                "status": "GITHUB_ISSUE",
                "issue_number": 90,
                "baseline_rate": 0.5,
                "latest_verification": None,
            }
        ],
        "raw_responses_stored": False,
        "proposal_bodies_stored": False,
        "ai_judge_used": False,
        "judge_model_calls": 0,
        "external_calls": 0,
        "zero_judge_tokens": True,
        "production_code_mutation": False,
        "execution_authorized": False,
    }
    actions = {
        "action_queue_version": "roberta_human_remediation_action_queue/v1",
        "record_count": 2,
        "active_count": 1,
        "closure_ready_count": 1,
        "action_counts": {
            "APPROVE_PROPOSAL": 0,
            "CREATE_ISSUE": 0,
            "FIX_ISSUE": 1,
            "ACCEPT_NEW_CHECKPOINT": 0,
            "REPLAY_AGAIN": 0,
            "CLOSE_AS_RESOLVED": 1,
        },
        "items": [
            {
                "proposal_fingerprint": "a" * 64,
                "failure_code": "technical_language_leak",
                "service": "pre_trade",
                "lifecycle_status": "GITHUB_ISSUE",
                "effective_stage": "GITHUB_ISSUE",
                "next_action": "FIX_ISSUE",
                "next_action_label": "Fix issue",
                "reason": "fix required",
                "issue_number": 90,
                "issue_url": "https://github.com/bhaygood29053-pixel/roberta-langgraph/issues/90",
                "latest_checkpoint_sequence": 2,
                "latest_verification_sequence": None,
                "closure_ready": False,
                "production_code_mutation": False,
                "execution_authorized": False,
            },
            {
                "proposal_fingerprint": "b" * 64,
                "failure_code": "report_style_status_dump",
                "service": "instant_scan",
                "lifecycle_status": "RESOLVED",
                "effective_stage": "RESOLVED",
                "next_action": "CLOSE_AS_RESOLVED",
                "next_action_label": "Close as resolved",
                "reason": "resolved",
                "issue_number": 91,
                "issue_url": "https://github.com/bhaygood29053-pixel/roberta-langgraph/issues/91",
                "latest_checkpoint_sequence": 3,
                "latest_verification_sequence": 3,
                "closure_ready": True,
                "production_code_mutation": False,
                "execution_authorized": False,
            },
        ],
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
    view = build_dashboard(
        qualification=run_stress_qualification(limit=50),
        human_checkpoint_history={
            "checkpoint_count": 0,
            "latest_checkpoint_id": None,
            "previous_checkpoint_id": None,
            "comparison_available": False,
        },
        human_remediation_lifecycle=lifecycle,
        human_remediation_action_queue=actions,
    )
    assert view["human_remediation_actions"]["closure_ready_count"] == 1
    markdown = render_markdown(view)
    assert "## Human remediation action queue" in markdown
    assert "Closure-ready issues: 1" in markdown
    assert "**Fix issue**" in markdown
    assert "**Close as resolved**" in markdown
    assert "only lifecycle status RESOLVED" in markdown
