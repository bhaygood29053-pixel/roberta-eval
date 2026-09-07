from __future__ import annotations

import json
from pathlib import Path
from typing import Any

EXPECTED_CMIS_SERVICES = {
    "asset_lookup",
    "market_report",
    "rank",
    "historical_compare",
    "tokenomics",
    "burn_intelligence",
    "discovery_intelligence",
    "risk_check",
    "pre_trade_check",
    "verification_evidence",
    "concentration_change_intelligence",
    "concentration_warning_intelligence",
    "bridge_to_xdex_utilization",
    "cross_chain_asset_provenance",
    "trade_price_impact_intelligence",
    "large_trade_discovery",
    "regulatory_evidence",
    "instant_x1_scan",
}

EXPECTED_HUMAN_WORKFLOWS = {
    "instant_x1_scan",
    "x1_compare",
    "x1_burn_intelligence",
    "x1_discovery_intelligence",
    "x1_what_changed",
    "x1_concentration_warning_intelligence",
    "x1_cross_chain_asset_provenance",
    "x1_trade_price_impact_intelligence",
    "x1_large_trade_discovery",
    "x1_regulatory_intelligence",
}

FRESHNESS_POLICIES = {"required_for_current_claims", "evidence_scoped"}


def registry_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "capabilities.json"


def load_registry(path: Path | None = None) -> dict[str, Any]:
    source = path or registry_path()
    return json.loads(source.read_text(encoding="utf-8"))


def _unique_ids(items: list[dict[str, Any]], label: str) -> set[str]:
    ids = [str(item.get("id", "")) for item in items]
    if any(not value for value in ids):
        raise ValueError(f"{label} contains an empty id")
    if len(ids) != len(set(ids)):
        raise ValueError(f"{label} contains duplicate ids")
    return set(ids)


def validate_registry(registry: dict[str, Any]) -> None:
    if registry.get("registry_version") != "roberta_capability_registry/v1":
        raise ValueError("unsupported capability registry version")

    source = registry.get("generated_from")
    if not isinstance(source, dict) or source.get("repository") != "bhaygood29053-pixel/roberta-langgraph":
        raise ValueError("capability registry source repository is invalid")
    if not source.get("observed_commit"):
        raise ValueError("capability registry must record its observed source commit")

    services = registry.get("cmis_services")
    workflows = registry.get("human_workflows")
    if not isinstance(services, list) or not isinstance(workflows, list):
        raise ValueError("capability registry lists are missing")

    service_ids = _unique_ids(services, "cmis_services")
    workflow_ids = _unique_ids(workflows, "human_workflows")

    if service_ids != EXPECTED_CMIS_SERVICES:
        missing = sorted(EXPECTED_CMIS_SERVICES - service_ids)
        extra = sorted(service_ids - EXPECTED_CMIS_SERVICES)
        raise ValueError(f"CMIS service parity mismatch: missing={missing}, extra={extra}")

    if workflow_ids != EXPECTED_HUMAN_WORKFLOWS:
        missing = sorted(EXPECTED_HUMAN_WORKFLOWS - workflow_ids)
        extra = sorted(workflow_ids - EXPECTED_HUMAN_WORKFLOWS)
        raise ValueError(f"Human workflow parity mismatch: missing={missing}, extra={extra}")

    for service in services:
        if service.get("state") != "contract_exposed":
            raise ValueError(f"{service['id']}: invalid service state")
        if service.get("chain") != "x1":
            raise ValueError(f"{service['id']}: registry v1 is X1 scoped")
        if service.get("evidence_authority") != "cmis":
            raise ValueError(f"{service['id']}: CMIS must remain evidence authority")
        if service.get("freshness_policy") not in FRESHNESS_POLICIES:
            raise ValueError(f"{service['id']}: invalid freshness policy")
        if not service.get("question_families"):
            raise ValueError(f"{service['id']}: question families are required")
        if not service.get("allowed_conclusions"):
            raise ValueError(f"{service['id']}: allowed conclusions are required")
        if not service.get("forbidden_conclusions"):
            raise ValueError(f"{service['id']}: forbidden conclusions are required")
        if service.get("execution_authorized") is not False:
            raise ValueError(f"{service['id']}: execution must remain unauthorized")

    for workflow in workflows:
        if workflow.get("state") != "human_renderer_supported":
            raise ValueError(f"{workflow['id']}: invalid workflow state")
        if workflow.get("facts_authority") != "chain_scout_cmis":
            raise ValueError(f"{workflow['id']}: facts authority changed")
        if workflow.get("judgment_authority") != "roberta":
            raise ValueError(f"{workflow['id']}: judgment authority changed")
        if workflow.get("read_only") is not True:
            raise ValueError(f"{workflow['id']}: workflow must remain read-only")
        if workflow.get("execution_authorized") is not False:
            raise ValueError(f"{workflow['id']}: execution must remain unauthorized")

        mapped = set(workflow.get("cmis_services", []))
        unknown = mapped - service_ids
        if unknown:
            raise ValueError(f"{workflow['id']}: unknown CMIS mappings {sorted(unknown)}")


def registry_summary(registry: dict[str, Any]) -> dict[str, Any]:
    validate_registry(registry)
    return {
        "registry_version": registry["registry_version"],
        "source_repository": registry["generated_from"]["repository"],
        "source_commit": registry["generated_from"]["observed_commit"],
        "cmis_service_count": len(registry["cmis_services"]),
        "human_workflow_count": len(registry["human_workflows"]),
        "cmis_services": [item["id"] for item in registry["cmis_services"]],
        "human_workflows": [item["id"] for item in registry["human_workflows"]],
    }
