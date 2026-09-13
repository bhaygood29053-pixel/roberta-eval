from roberta_eval.dashboard import build_dashboard, render_markdown
from roberta_eval.stress import run_stress_qualification


def test_dashboard_surfaces_human_remediation_lifecycle_without_claiming_resolution():
    lifecycle = {
        "lifecycle_version": "roberta_human_remediation_lifecycle/v1",
        "record_count": 1,
        "status_counts": {
            "DETECTED": 0,
            "PROPOSED": 0,
            "APPROVED": 0,
            "GITHUB_ISSUE": 0,
            "FIX_MERGED": 1,
            "REPLAY_VERIFIED": 0,
            "IMPROVED": 0,
            "RESOLVED": 0,
        },
        "active_count": 1,
        "verified_count": 0,
        "improved_count": 0,
        "resolved_count": 0,
        "active": [
            {
                "proposal_fingerprint": "a" * 64,
                "failure_code": "technical_language_leak",
                "service": "pretrade",
                "status": "FIX_MERGED",
                "issue_number": 777,
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
    view = build_dashboard(
        qualification=run_stress_qualification(limit=50),
        human_remediation_lifecycle=lifecycle,
    )
    assert view["human_remediation_lifecycle"]["active_count"] == 1
    assert view["human_remediation_lifecycle"]["resolved_count"] == 0
    markdown = render_markdown(view)
    assert "## Human remediation lifecycle" in markdown
    assert "FIX_MERGED" in markdown
    assert "merged fix is not treated as resolved" in markdown
