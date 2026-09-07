import copy

import pytest

from roberta_eval.corpus import materialize_cases
from roberta_eval.regression_memory import (
    load_memory,
    memory_summary,
    promote_cluster,
    validate_memory,
)


def _cluster(**overrides):
    base = {
        "cluster_id": "cluster::abc",
        "category": "NUMERICAL_ERROR",
        "severity": "HIGH",
        "service": "market_report",
        "likely_layer": "roberta",
        "reason": "field_check_failed",
        "actionable_product_defect": True,
        "evaluation_incomplete": False,
    }
    base.update(overrides)
    return base


def _case():
    return next(
        case for case in materialize_cases()
        if case["service"] == "market_report"
    )


def test_empty_repository_memory_is_valid() -> None:
    memory = load_memory()
    validate_memory(memory)
    assert memory_summary(memory)["active_regression_count"] == 0


def test_confirmed_actionable_cluster_promotes_replayable_case() -> None:
    memory = promote_cluster(load_memory(), _cluster(), _case(), confirmed=True)
    assert len(memory["records"]) == 1
    record = memory["records"][0]
    assert record["replay_case"]["checks"] == _case()["checks"]
    assert record["execution_authorized"] is False


def test_promotion_is_idempotent() -> None:
    memory = promote_cluster(load_memory(), _cluster(), _case(), confirmed=True)
    memory = promote_cluster(memory, _cluster(), _case(), confirmed=True)
    assert len(memory["records"]) == 1


def test_unconfirmed_cluster_is_rejected() -> None:
    with pytest.raises(ValueError, match="confirmed=true"):
        promote_cluster(load_memory(), _cluster(), _case(), confirmed=False)


def test_evaluation_cluster_is_rejected() -> None:
    cluster = _cluster(
        category="EVALUATION_INCOMPLETE",
        actionable_product_defect=False,
        evaluation_incomplete=True,
    )
    with pytest.raises(ValueError, match="not an actionable product defect"):
        promote_cluster(load_memory(), cluster, _case(), confirmed=True)


def test_service_mismatch_is_rejected() -> None:
    with pytest.raises(ValueError, match="service does not match"):
        promote_cluster(
            load_memory(),
            _cluster(service="risk_check"),
            _case(),
            confirmed=True,
        )


def test_memory_rejects_execution_authorization() -> None:
    memory = promote_cluster(load_memory(), _cluster(), _case(), confirmed=True)
    memory["records"][0]["execution_authorized"] = True
    with pytest.raises(ValueError, match="execution must remain unauthorized"):
        validate_memory(memory)
