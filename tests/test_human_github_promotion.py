import copy

import pytest

from roberta_eval.dashboard import _human_priority
from roberta_eval.github_promotion import (
    build_human_language_issue_proposal,
    build_human_language_issue_proposals,
    proposal_summary,
)


def _report(*, recurring: bool = True, new: bool = True, no_defects: bool = False) -> dict:
    recurring_items = []
    failure_trends = {}
    worst_services = []
    if not no_defects:
        worst_services = [
            {
                "service": "pre_trade",
                "result_count": 10,
                "pass_count": 5,
                "defect_count": 5,
                "pass_rate": 0.5,
                "defect_rate": 0.5,
            }
        ]
        if recurring:
            recurring_items = [
                {
                    "code": "technical_language_leak",
                    "previous_count": 2,
                    "current_count": 4,
                    "previous_rate": 0.2,
                    "current_rate": 0.4,
                    "rate_delta_pp": 20.0,
                    "direction": "REGRESSED",
                    "recurrence": "RECURRENT",
                }
            ]
            failure_trends["technical_language_leak"] = dict(recurring_items[0])
        if new:
            failure_trends["report_style_status_dump"] = {
                "previous_count": 0,
                "current_count": 3,
                "previous_rate": 0.0,
                "current_rate": 0.3,
                "rate_delta_pp": 30.0,
                "direction": "REGRESSED",
                "recurrence": "NEW",
            }

    return {
        "human_trend_report_version": "roberta_human_language_trend_report/v1",
        "source_mode": "accepted_checkpoint_history",
        "previous": {"snapshot_id": "human-v2-001"},
        "current": {"snapshot_id": "human-v2-002"},
        "comparison": {
            "human_trend_comparison_version": "roberta_human_language_trend_comparison/v1",
            "previous_snapshot_id": "human-v2-001",
            "current_snapshot_id": "human-v2-002",
            "overall": {
                "previous_defect_rate": 0.2,
                "current_defect_rate": 0.4 if not no_defects else 0.0,
                "defect_rate_delta_pp": 20.0 if not no_defects else -20.0,
                "defect_direction": "REGRESSED" if not no_defects else "IMPROVED",
            },
            "service_trends": {},
            "response_depth_trends": {},
            "failure_code_trends": failure_trends,
            "worst_current_services": worst_services,
            "recurring_current_defects": recurring_items,
            "improved_services": [],
            "regressed_services": ["pre_trade"] if not no_defects else [],
            "deterministic": True,
            "advisory_only": True,
            "factual_authority": False,
            "ai_judge_used": False,
            "judge_model_calls": 0,
            "external_calls": 0,
            "zero_judge_tokens": True,
            "execution_authorized": False,
        },
    }


def test_human_proposal_uses_same_dashboard_priority() -> None:
    report = _report()
    dashboard_priority = _human_priority(report)
    proposal = build_human_language_issue_proposal(report)

    assert proposal is not None
    assert proposal["human_priority"] == dashboard_priority
    assert proposal["human_priority"]["failure_code"] == "technical_language_leak"
    assert proposal["human_priority"]["recurrence"] == "RECURRENT"
    assert proposal["human_priority"]["service"] == "pre_trade"


def test_human_proposal_routes_to_roberta_and_never_creates_issue() -> None:
    proposal = build_human_language_issue_proposal(_report())
    assert proposal is not None
    assert proposal["target_repository"] == "bhaygood29053-pixel/roberta-langgraph"
    assert proposal["routing_status"] == "routed"
    assert proposal["proposal_kind"] == "human_language_remediation"
    assert proposal["reviewable_proposal_only"] is True
    assert proposal["issue_created"] is False
    assert proposal["production_mutation"] is False
    assert proposal["execution_authorized"] is False
    assert proposal["judge_model_calls"] == 0
    assert proposal["external_calls"] == 0
    assert proposal["zero_judge_tokens"] is True


def test_recurring_defect_has_priority_over_higher_count_new_defect() -> None:
    report = _report()
    report["comparison"]["failure_code_trends"]["report_style_status_dump"]["current_count"] = 99
    report["comparison"]["failure_code_trends"]["report_style_status_dump"]["current_rate"] = 0.99
    proposal = build_human_language_issue_proposal(report)
    assert proposal is not None
    assert proposal["human_priority"]["failure_code"] == "technical_language_leak"
    assert proposal["human_priority"]["recurrence"] == "RECURRENT"


def test_new_defect_is_used_when_no_recurring_defect_exists() -> None:
    proposal = build_human_language_issue_proposal(_report(recurring=False, new=True))
    assert proposal is not None
    assert proposal["human_priority"]["failure_code"] == "report_style_status_dump"
    assert proposal["human_priority"]["recurrence"] == "NEW"


def test_no_current_human_defect_produces_zero_proposals() -> None:
    report = _report(recurring=False, new=False, no_defects=True)
    assert build_human_language_issue_proposal(report) is None
    assert build_human_language_issue_proposals(report) == []
    assert build_human_language_issue_proposals(None) == []


def test_proposal_fingerprint_is_stable_and_does_not_leak_local_paths() -> None:
    report = _report()
    report["previous"]["source"] = "/home/user/private/before.jsonl"
    report["current"]["source"] = "/home/user/private/after.jsonl"
    first = build_human_language_issue_proposal(report)
    second = build_human_language_issue_proposal(copy.deepcopy(report))
    assert first == second
    assert first is not None
    assert "/home/user/private" not in first["body"]
    assert first["previous_snapshot_id"] == "human-v2-001"
    assert first["current_snapshot_id"] == "human-v2-002"


def test_non_deterministic_or_external_comparison_fails_closed() -> None:
    report = _report()
    report["comparison"]["ai_judge_used"] = True
    with pytest.raises(ValueError, match="deterministic comparison"):
        build_human_language_issue_proposal(report)

    report = _report()
    report["comparison"]["external_calls"] = 1
    with pytest.raises(ValueError, match="zero-call comparison"):
        build_human_language_issue_proposal(report)

    report = _report()
    report["comparison"]["execution_authorized"] = True
    with pytest.raises(ValueError, match="execution authority"):
        build_human_language_issue_proposal(report)


def test_proposal_summary_exposes_human_and_zero_token_boundary() -> None:
    proposals = build_human_language_issue_proposals(_report())
    summary = proposal_summary(proposals)
    assert summary["proposal_count"] == 1
    assert summary["human_language_count"] == 1
    assert summary["issue_created_count"] == 0
    assert summary["reviewable_proposal_only"] is True
    assert summary["judge_model_calls"] == 0
    assert summary["external_calls"] == 0
    assert summary["zero_judge_tokens"] is True
