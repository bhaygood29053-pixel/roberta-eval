import copy

import pytest

from roberta_eval.registry import (
    EXPECTED_CMIS_SERVICES,
    EXPECTED_HUMAN_WORKFLOWS,
    load_registry,
    registry_summary,
    validate_registry,
)


def test_registry_matches_current_roberta_contract_surface() -> None:
    registry = load_registry()
    validate_registry(registry)
    assert {item["id"] for item in registry["cmis_services"]} == EXPECTED_CMIS_SERVICES
    assert {item["id"] for item in registry["human_workflows"]} == EXPECTED_HUMAN_WORKFLOWS


def test_registry_preserves_read_only_boundary() -> None:
    registry = load_registry()
    assert all(item["execution_authorized"] is False for item in registry["cmis_services"])
    assert all(item["execution_authorized"] is False for item in registry["human_workflows"])
    assert all(item["read_only"] is True for item in registry["human_workflows"])


def test_registry_distinguishes_contract_exposure_from_live_health() -> None:
    registry = load_registry()
    assert registry["semantics"]["contract_exposed"].startswith(
        "The service appears in the current ROBERTA-side CMIS contract."
    )


def test_registry_rejects_duplicate_service_ids() -> None:
    registry = load_registry()
    registry["cmis_services"].append(copy.deepcopy(registry["cmis_services"][0]))
    with pytest.raises(ValueError, match="duplicate ids"):
        validate_registry(registry)


def test_registry_rejects_execution_authorization() -> None:
    registry = load_registry()
    registry["cmis_services"][0]["execution_authorized"] = True
    with pytest.raises(ValueError, match="execution must remain unauthorized"):
        validate_registry(registry)


def test_registry_rejects_unknown_workflow_mapping() -> None:
    registry = load_registry()
    registry["human_workflows"][0]["cmis_services"] = ["not_a_real_service"]
    with pytest.raises(ValueError, match="unknown CMIS mappings"):
        validate_registry(registry)


def test_registry_summary_is_stable() -> None:
    summary = registry_summary(load_registry())
    assert summary["cmis_service_count"] == 18
    assert summary["human_workflow_count"] == 10
