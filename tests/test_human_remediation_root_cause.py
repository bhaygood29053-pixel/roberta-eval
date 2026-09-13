from __future__ import annotations

import hashlib
import json

import pytest

from roberta_eval.human_remediation_lineage import (
    CHRONIC_REGRESSION,
    GENERATIONAL_LINEAGE_VERSION,
    HEALTH_STATES,
    LINEAGE_HEALTH_VERSION,
    RECURRENCE_OBSERVED,
    ROOT_CAUSE_WARNING,
    STABLE_ROOT,
)
from roberta_eval.human_remediation_root_cause import (
    DOMAINS,
    ROOT_CAUSE_INVESTIGATION_VERSION,
    address_investigation,
    build_investigation_package,
    empty_root_cause_ledger,
    register_investigation,
    root_cause_sufficiency_gate,
    validate_investigation_package,
    validate_root_cause_ledger,
)

ROOT = "a" * 64
FAILURE = "technical_language_leak"
SERVICE = "pre_trade"


def _sha(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _health(depth: int) -> str:
    if depth == 0:
        return STABLE_ROOT
    if depth == 1:
        return RECURRENCE_OBSERVED
    if depth == 2:
        return ROOT_CAUSE_WARNING
    return CHRONIC_REGRESSION


def _lineage(depth: int, *, statuses: list[str] | None = None) -> dict:
    nodes = []
    fingerprints = []
    lifecycle_ids = []
    node_statuses = statuses or ["RESOLVED"] * (depth + 1)
    for generation in range(depth + 1):
        fingerprint = chr(97 + generation) * 64
        fingerprints.append(fingerprint)
        lifecycle_id = f"human-remediation::{fingerprint}"
        lifecycle_ids.append(lifecycle_id)
        nodes.append(
            {
                "proposal_fingerprint": fingerprint,
                "lifecycle_id": lifecycle_id,
                "generation": generation,
                "parent_proposal_fingerprint": fingerprints[generation - 1] if generation else None,
                "status": node_statuses[generation],
                "failure_code": FAILURE,
                "service": SERVICE,
                "issue_number": 100 + generation,
                "reopen_event_key": _sha({"reopen": generation}) if generation else None,
                "fresh_checkpoint_id": f"cp-{generation}" if generation else None,
            }
        )
    family = {
        "root_proposal_fingerprint": ROOT,
        "root_lifecycle_id": f"human-remediation::{ROOT}",
        "failure_code": FAILURE,
        "service": SERVICE,
        "node_count": depth + 1,
        "repeat_regression_count": depth,
        "deepest_generation": depth,
        "health": _health(depth),
        "root_cause_warning": depth >= 2,
        "root_cause_interpretation": (
            "Repeated accepted recurrence indicates a remediation-loop risk; it does not by itself prove the underlying causal root cause."
            if depth >= 2
            else None
        ),
        "nodes": nodes,
        "paths": [
            {
                "leaf_proposal_fingerprint": fingerprints[-1],
                "depth": depth,
                "proposal_fingerprints": fingerprints,
                "lifecycle_ids": lifecycle_ids,
                "statuses": node_statuses,
            }
        ],
    }
    counts = {state: 0 for state in HEALTH_STATES}
    counts[_health(depth)] = 1
    core = {
        "lineage_version": GENERATIONAL_LINEAGE_VERSION,
        "health_version": LINEAGE_HEALTH_VERSION,
        "family_count": 1,
        "lineage_node_count": depth + 1,
        "reopen_edge_count": depth,
        "deepest_generation": depth,
        "repeat_regression_family_count": 1 if depth >= 2 else 0,
        "root_cause_warning_family_count": 1 if depth >= 2 else 0,
        "chronic_family_count": 1 if depth >= 3 else 0,
        "health_counts": counts,
        "families": [family],
        "acyclic": True,
        "one_parent_per_child": True,
        "generation_integrity": True,
        "failure_service_integrity": True,
        "read_only": True,
        "advisory_pattern_interpretation": True,
        "automatic_issue_creation": False,
        "lifecycle_mutation": False,
        "production_code_mutation": False,
        "execution_authorized": False,
    }
    core["report_sha256"] = _sha(core)
    return core


def _evidence(
    domain: str,
    generation: int,
    *,
    direction: str = "SUPPORTS",
    strength: str = "DIRECT",
    suffix: str = "a",
) -> dict:
    return {
        "domain": domain,
        "generation": generation,
        "direction": direction,
        "strength": strength,
        "source_ref": f"tests/{domain}-{generation}-{suffix}",
        "artifact_sha256": _sha({"artifact": domain, "generation": generation, "suffix": suffix}),
        "statement": f"Observed {direction.lower()} evidence for {domain} in generation {generation}.",
    }


def test_warning_family_creates_six_domain_package_and_no_evidence_does_not_name_root_cause() -> None:
    package = build_investigation_package(_lineage(2), root_fingerprint=ROOT, evidence=[])
    validate_investigation_package(package)
    assert package["investigation_version"] == ROOT_CAUSE_INVESTIGATION_VERSION
    assert package["investigation_required"] is True
    assert package["domains"] == list(DOMAINS)
    assert {item["domain"] for item in package["findings"]} == set(DOMAINS)
    assert package["root_cause_named"] is False
    assert package["confirmed_root_causes"] == []
    assert package["ordinary_symptom_fix_sufficient"] is False
    assert package["replay_success_alone_sufficient"] is False


def test_stable_and_first_recurrence_do_not_require_root_cause_gate() -> None:
    for depth in (0, 1):
        lineage = _lineage(depth)
        package = build_investigation_package(lineage, root_fingerprint=ROOT, evidence=[])
        assert package["investigation_required"] is False
        gate = root_cause_sufficiency_gate(
            lineage, empty_root_cause_ledger(), fingerprint=lineage["families"][0]["nodes"][-1]["proposal_fingerprint"]
        )
        assert gate["status"] == "NOT_REQUIRED"
        assert gate["closure_sufficient"] is True


def test_direct_cross_generation_support_confirms_root_cause_and_ranks_it_first() -> None:
    package = build_investigation_package(
        _lineage(2),
        root_fingerprint=ROOT,
        evidence=[
            _evidence("renderer", 1, suffix="one"),
            _evidence("renderer", 2, suffix="two"),
            _evidence("prompt", 2, strength="INDIRECT", suffix="hint"),
            _evidence("policy", 1, direction="CONTRADICTS", suffix="one"),
            _evidence("policy", 2, direction="CONTRADICTS", suffix="two"),
        ],
    )
    assert package["root_cause_named"] is True
    assert package["confirmed_root_causes"] == ["renderer"]
    assert package["findings"][0]["domain"] == "renderer"
    renderer = next(item for item in package["findings"] if item["domain"] == "renderer")
    policy = next(item for item in package["findings"] if item["domain"] == "policy")
    prompt = next(item for item in package["findings"] if item["domain"] == "prompt")
    assert renderer["state"] == "CONFIRMED_ROOT_CAUSE"
    assert renderer["support_generations"] == [1, 2]
    assert policy["state"] == "RULED_OUT"
    assert prompt["state"] == "SUSPECTED"


def test_contradictory_evidence_prevents_unsupported_root_cause_claim() -> None:
    package = build_investigation_package(
        _lineage(2),
        root_fingerprint=ROOT,
        evidence=[
            _evidence("renderer", 1, suffix="one"),
            _evidence("renderer", 2, suffix="two"),
            _evidence("renderer", 2, direction="CONTRADICTS", suffix="contradiction"),
        ],
    )
    renderer = next(item for item in package["findings"] if item["domain"] == "renderer")
    assert renderer["state"] != "CONFIRMED_ROOT_CAUSE"
    assert package["root_cause_named"] is False


def test_resolved_generation_two_is_still_blocked_until_investigation_is_addressed() -> None:
    lineage = _lineage(2, statuses=["RESOLVED", "RESOLVED", "RESOLVED"])
    fingerprint = lineage["families"][0]["nodes"][-1]["proposal_fingerprint"]
    ledger = empty_root_cause_ledger()
    gate = root_cause_sufficiency_gate(lineage, ledger, fingerprint=fingerprint)
    assert gate["status"] == "BLOCKED_INVESTIGATION_REQUIRED"
    assert gate["closure_sufficient"] is False
    assert gate["replay_success_alone_sufficient"] is False

    package = build_investigation_package(
        lineage,
        root_fingerprint=ROOT,
        evidence=[
            _evidence("renderer", 1, suffix="one"),
            _evidence("renderer", 2, suffix="two"),
        ],
    )
    ledger, status = register_investigation(ledger, package)
    assert status == "APPENDED"
    gate = root_cause_sufficiency_gate(lineage, ledger, fingerprint=fingerprint)
    assert gate["status"] == "BLOCKED_FINDINGS_UNADDRESSED"
    assert gate["closure_sufficient"] is False

    with pytest.raises(ValueError, match="explicit owner approval"):
        address_investigation(
            ledger,
            package_id=package["package_id"],
            owner="Bryant",
            mode="CONFIRMED_ROOT_CAUSE_ADDRESSED",
            addressed_domains=["renderer"],
            evidence_refs=["PR#123"],
            rationale="Renderer fix covered the repeated failure path.",
            approved=False,
        )

    ledger, disposition = address_investigation(
        ledger,
        package_id=package["package_id"],
        owner="Bryant",
        mode="CONFIRMED_ROOT_CAUSE_ADDRESSED",
        addressed_domains=["renderer"],
        evidence_refs=["PR#123", "test::renderer_regression"],
        rationale="Renderer fix and replay-specific regression evidence address the confirmed repeated failure path.",
        approved=True,
    )
    assert disposition["approved"] is True
    gate = root_cause_sufficiency_gate(lineage, ledger, fingerprint=fingerprint)
    assert gate["status"] == "ROOT_CAUSE_FINDINGS_ADDRESSED"
    assert gate["closure_sufficient"] is True
    validate_root_cause_ledger(ledger)


def test_inconclusive_no_evidence_investigation_cannot_be_marked_addressed() -> None:
    package = build_investigation_package(_lineage(2), root_fingerprint=ROOT, evidence=[])
    ledger, _ = register_investigation(empty_root_cause_ledger(), package)
    with pytest.raises(ValueError, match="no evidence-backed leading finding"):
        address_investigation(
            ledger,
            package_id=package["package_id"],
            owner="Bryant",
            mode="LEADING_FINDINGS_ADDRESSED",
            addressed_domains=["renderer"],
            evidence_refs=["PR#124"],
            rationale="Attempted mitigation.",
            approved=True,
        )


def test_suspected_leading_findings_can_be_evidence_backed_mitigated_without_false_root_cause_claim() -> None:
    lineage = _lineage(3)
    package = build_investigation_package(
        lineage,
        root_fingerprint=ROOT,
        evidence=[
            _evidence("prompt", 3, strength="DIRECT", suffix="one"),
            _evidence("shared_human_layer", 2, strength="INDIRECT", suffix="one"),
        ],
    )
    assert package["root_cause_named"] is False
    assert package["required_findings"]
    ledger, _ = register_investigation(empty_root_cause_ledger(), package)
    ledger, disposition = address_investigation(
        ledger,
        package_id=package["package_id"],
        owner="Bryant",
        mode="LEADING_FINDINGS_ADDRESSED",
        addressed_domains=package["required_findings"],
        evidence_refs=["PR#125", "test::shared_human_mitigation"],
        rationale="Leading evidence-backed findings were mitigated without claiming a proven causal root cause.",
        approved=True,
    )
    assert disposition["root_cause_named"] is False
    fingerprint = lineage["families"][0]["nodes"][-1]["proposal_fingerprint"]
    assert root_cause_sufficiency_gate(lineage, ledger, fingerprint=fingerprint)["closure_sufficient"] is True


def test_registration_is_idempotent_and_changed_family_requires_fresh_package() -> None:
    lineage = _lineage(2)
    package = build_investigation_package(
        lineage,
        root_fingerprint=ROOT,
        evidence=[_evidence("renderer", 2, suffix="one")],
    )
    ledger, status = register_investigation(empty_root_cause_ledger(), package)
    assert status == "APPENDED"
    same, status = register_investigation(ledger, package)
    assert same == ledger
    assert status == "UNCHANGED"

    changed = _lineage(3)
    fingerprint = changed["families"][0]["nodes"][-1]["proposal_fingerprint"]
    gate = root_cause_sufficiency_gate(changed, ledger, fingerprint=fingerprint)
    assert gate["status"] == "BLOCKED_INVESTIGATION_REQUIRED"
