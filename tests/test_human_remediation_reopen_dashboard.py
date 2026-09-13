from roberta_eval.dashboard import build_dashboard, render_markdown
from roberta_eval.stress import run_stress_qualification


def _summary() -> dict:
    return {
        "ledger_version": "roberta_human_remediation_reopen_adjudication_ledger/v1",
        "adjudication_count": 2,
        "pending_adjudication_count": 1,
        "administrative_count": 1,
        "confirmed_regression_count": 1,
        "new_cycle_eligible_count": 1,
        "pending": [
            {
                "reopen_event_key": "e" * 64,
                "proposal_fingerprint": "f" * 64,
                "failure_code": "report_style_status_dump",
                "service": "instant_scan",
                "issue_number": 902,
                "issue_url": "https://github.com/bhaygood29053-pixel/roberta-langgraph/issues/902",
            }
        ],
        "adjudications": [
            {
                "classification": "ADMINISTRATIVE_NON_QUALITY",
                "failure_code": "technical_language_leak",
                "service": "pre_trade",
                "issue_number": 900,
                "fresh_regression_evidence": None,
                "new_cycle_eligible": False,
            },
            {
                "classification": "GENUINE_HUMAN_QUALITY_REGRESSION",
                "failure_code": "engineering_term_leak",
                "service": "instant_scan",
                "issue_number": 901,
                "fresh_regression_evidence": {
                    "checkpoint_id": "cp-fresh",
                    "checkpoint_sequence": 4,
                    "checkpoint_corpus_sha256": "a" * 64,
                    "targeted_failure_count": 2,
                    "targeted_failure_rate": 0.2,
                },
                "new_cycle_eligible": True,
            },
        ],
        "explicit_owner_adjudication_required": True,
        "fresh_checkpoint_required_for_regression": True,
        "automatic_new_cycle_creation": False,
        "production_code_mutation": False,
        "execution_authorized": False,
    }


def test_dashboard_surfaces_reopen_adjudication_and_cycle_eligibility() -> None:
    view = build_dashboard(
        qualification=run_stress_qualification(limit=50),
        human_remediation_lifecycle={
            "record_count": 0,
            "status_counts": {},
            "active_count": 0,
            "verified_count": 0,
            "improved_count": 0,
            "resolved_count": 0,
            "active": [],
        },
        human_remediation_action_queue={
            "record_count": 0,
            "active_count": 0,
            "closure_ready_count": 0,
            "action_counts": {},
            "items": [],
        },
        human_remediation_reopen_adjudication=_summary(),
    )
    reopen = view["human_remediation_reopen_adjudication"]
    assert reopen["pending_adjudication_count"] == 1
    assert reopen["administrative_count"] == 1
    assert reopen["confirmed_regression_count"] == 1
    assert reopen["new_cycle_eligible_count"] == 1

    markdown = render_markdown(view)
    assert "## Human remediation reopen adjudication" in markdown
    assert "Pending owner adjudication: 1" in markdown
    assert "Administrative / non-quality: 1" in markdown
    assert "Confirmed Human-quality regressions: 1" in markdown
    assert "New-cycle eligible: 1" in markdown
    assert "requires explicit owner classification" in markdown
    assert "fresh checkpoint `cp-fresh`" in markdown
    assert "A GitHub reopen is not proof of a Human-quality regression" in markdown
