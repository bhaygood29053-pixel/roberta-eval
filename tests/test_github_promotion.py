import pytest

from roberta_eval.github_promotion import build_issue_proposal, build_issue_proposals


def _cluster(layer="roberta", **overrides):
    base = {
        "cluster_id": "cluster::abc",
        "category": "NUMERICAL_ERROR",
        "severity": "HIGH",
        "service": "market_report",
        "likely_layer": layer,
        "reason": "field_check_failed",
        "occurrence_count": 12,
        "member_finding_ids": ["a", "b"],
        "actionable_product_defect": True,
    }
    base.update(overrides)
    return base


@pytest.mark.parametrize(
    ("layer", "repo"),
    [
        ("provider", "bhaygood29053-pixel/cmis"),
        ("cmis", "bhaygood29053-pixel/cmis"),
        ("x1_scout", "bhaygood29053-pixel/roberta-langgraph"),
        ("roberta", "bhaygood29053-pixel/roberta-langgraph"),
        ("laboratory", "bhaygood29053-pixel/roberta-eval"),
    ],
)
def test_layer_routes_to_expected_repository(layer, repo) -> None:
    proposal = build_issue_proposal(_cluster(layer), confirmed=True)
    assert proposal["target_repository"] == repo
    assert proposal["routing_status"] == "routed"
    assert proposal["issue_created"] is False


def test_unknown_layer_remains_unassigned() -> None:
    proposal = build_issue_proposal(_cluster("unknown"), confirmed=True)
    assert proposal["target_repository"] is None
    assert proposal["routing_status"] == "needs_localization"


def test_unconfirmed_cluster_is_rejected() -> None:
    with pytest.raises(ValueError, match="confirmed=true"):
        build_issue_proposal(_cluster(), confirmed=False)


def test_evaluation_cluster_is_rejected() -> None:
    with pytest.raises(ValueError, match="not an actionable product defect"):
        build_issue_proposal(
            _cluster(
                category="EVALUATION_INCOMPLETE",
                actionable_product_defect=False,
            ),
            confirmed=True,
        )


def test_proposal_is_stable_and_contains_replay_guidance() -> None:
    first = build_issue_proposal(_cluster(), confirmed=True)
    second = build_issue_proposal(_cluster(), confirmed=True)
    assert first == second
    assert "permanent regression case" in first["body"]
    assert "cluster::abc" in first["body"]


def test_batch_only_promotes_confirmed_cluster_ids() -> None:
    clusters = [_cluster(), _cluster("cmis", cluster_id="cluster::def")]
    proposals = build_issue_proposals(
        clusters,
        confirmed_cluster_ids={"cluster::def"},
    )
    assert len(proposals) == 1
    assert proposals[0]["cluster_id"] == "cluster::def"
