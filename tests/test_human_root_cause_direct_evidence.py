from __future__ import annotations

import hashlib
import json
from copy import deepcopy

import pytest

from roberta_eval.human_remediation_lineage import (
    CHRONIC_REGRESSION,
    GENERATIONAL_LINEAGE_VERSION,
    LINEAGE_HEALTH_VERSION,
    RECURRENCE_OBSERVED,
    ROOT_CAUSE_WARNING,
    STABLE_ROOT,
    validate_generational_lineage_report,
)
from roberta_eval.human_remediation_root_cause import DOMAINS
from roberta_eval.human_root_cause_direct_evidence import (
    DIRECT_EVIDENCE_BUNDLE_VERSION,
    EXPERIMENT_PLAN_VERSION,
    build_direct_evidence_bundle,
    build_lab81_package_with_direct_evidence,
    direct_evidence_summary,
    empty_direct_evidence_ledger,
    generate_experiment_plans,
    qualify_experiment_result,
    record_experiment_result,
    register_experiment_plans,
    validate_direct_evidence_bundle,
    validate_direct_evidence_ledger,
    validate_experiment_plan,
)
from roberta_eval.human_root_cause_evidence_acquisition import (
    CORRELATION_VERSION,
    EVIDENCE_ACQUISITION_VERSION,
    EVIDENCE_BUNDLE_VERSION,
    validate_evidence_bundle,
)

FAILURE = "technical_language_leak"
SERVICE = "pre_trade"
ROOT_FP = "a" * 64
FPS = [ROOT_FP, "b" * 64, "c" * 64]
CORPUS = "d" * 64


def _sha(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _lineage_report() -> dict:
    nodes = []
    for generation, fp in enumerate(FPS):
        nodes.append(
            {
                "proposal_fingerprint": fp,
                "lifecycle_id": f"human-remediation::{fp}",
                "generation": generation,
                "parent_proposal_fingerprint": FPS[generation - 1] if generation else None,
                "status": "RESOLVED",
                "failure_code": FAILURE,
                "service": SERVICE,
                "issue_number": None,
                "reopen_event_key": None,
                "fresh_checkpoint_id": None,
            }
        )
    family = {
        "root_proposal_fingerprint": ROOT_FP,
        "root_lifecycle_id": f"human-remediation::{ROOT_FP}",
        "failure_code": FAILURE,
        "service": SERVICE,
        "node_count": 3,
        "repeat_regression_count": 2,
        "deepest_generation": 2,
        "health": ROOT_CAUSE_WARNING,
        "root_cause_warning": True,
        "root_cause_interpretation": "Repeated recurrence is a remediation-loop signal, not causal proof.",
        "nodes": nodes,
        "paths": [
            {
                "leaf_proposal_fingerprint": FPS[-1],
                "depth": 2,
                "proposal_fingerprints": FPS,
                "lifecycle_ids": [f"human-remediation::{fp}" for fp in FPS],
                "statuses": ["RESOLVED", "RESOLVED", "RESOLVED"],
            }
        ],
    }
    core = {
        "lineage_version": GENERATIONAL_LINEAGE_VERSION,
        "health_version": LINEAGE_HEALTH_VERSION,
        "family_count": 1,
        "lineage_node_count": 3,
        "reopen_edge_count": 2,
        "deepest_generation": 2,
        "repeat_regression_family_count": 1,
        "root_cause_warning_family_count": 1,
        "chronic_family_count": 0,
        "health_counts": {
            STABLE_ROOT: 0,
            RECURRENCE_OBSERVED: 0,
            ROOT_CAUSE_WARNING: 1,
            CHRONIC_REGRESSION: 0,
        },
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
    validate_generational_lineage_report(core)
    return core


def _finding(domain: str) -> dict:
    if domain == "renderer":
        return {
            "domain": domain,
            "signal": "REPEATED_CROSS_GENERATION_ASSOCIATION",
            "score": 30,
            "implementation_change_count": 3,
            "implementation_generations": [0, 1, 2],
            "implementation_paths": ["src/roberta/human_response_renderer.py"],
            "test_change_count": 3,
            "test_generations": [0, 1, 2],
            "test_paths": ["tests/test_human_response_renderer.py"],
            "accepted_success_check_count": 3,
            "accepted_improved_or_resolved_replay_count": 3,
            "causal_authority": False,
        }
    return {
        "domain": domain,
        "signal": "NO_OBSERVED_ASSOCIATION",
        "score": 0,
        "implementation_change_count": 0,
        "implementation_generations": [],
        "implementation_paths": [],
        "test_change_count": 0,
        "test_generations": [],
        "test_paths": [],
        "accepted_success_check_count": 0,
        "accepted_improved_or_resolved_replay_count": 0,
        "causal_authority": False,
    }


def _acquisition_bundle() -> dict:
    lineage = _lineage_report()
    correlation = {
        "correlation_version": CORRELATION_VERSION,
        "family_root_fingerprint": ROOT_FP,
        "family_health": ROOT_CAUSE_WARNING,
        "deepest_generation": 2,
        "findings": [_finding(domain) for domain in DOMAINS],
        "causal_authority": False,
        "correlation_is_not_causation": True,
        "root_cause_confirmation_authority": "LAB_81_ONLY",
    }
    correlation["correlation_sha256"] = _sha(correlation)
    evidence = []
    for generation in (0, 1, 2):
        evidence.append(
            {
                "domain": "renderer",
                "generation": generation,
                "direction": "SUPPORTS",
                "strength": "INDIRECT",
                "source_ref": f"github:renderer:g{generation}",
                "artifact_sha256": _sha({"renderer": generation}),
                "statement": "Correlation-only renderer association; not causal proof.",
            }
        )
    core = {
        "evidence_bundle_version": EVIDENCE_BUNDLE_VERSION,
        "acquisition_version": EVIDENCE_ACQUISITION_VERSION,
        "source_snapshot_sha256": _sha("snapshot"),
        "lineage_report_sha256": lineage["report_sha256"],
        "family_root_fingerprint": ROOT_FP,
        "failure_code": FAILURE,
        "service": SERVICE,
        "health": ROOT_CAUSE_WARNING,
        "deepest_generation": 2,
        "investigation_required": True,
        "source_record_ids": [_sha("source-0"), _sha("source-1"), _sha("source-2")],
        "lab81_evidence": evidence,
        "context_records": [],
        "correlation": correlation,
        "automatic_evidence_strength": "INDIRECT_ONLY",
        "automatic_direct_evidence_count": 0,
        "causal_authority": False,
        "correlation_is_not_causation": True,
        "lab81_confirmation_threshold_preserved": True,
        "read_only": True,
        "github_issue_mutation": False,
        "production_code_mutation": False,
        "execution_authorized": False,
    }
    core["bundle_sha256"] = _sha(core)
    validate_evidence_bundle(core)
    return core


def _result_input(plan: dict, *, intervention_failures: int, control_failures: int = 4) -> dict:
    constant = {}
    for index, domain in enumerate(plan["held_constant_domains"]):
        digest = _sha({"constant": domain, "index": index})
        constant[domain] = {
            "control_sha256": digest,
            "intervention_sha256": digest,
        }
    return {
        "experiment_plan_id": plan["plan_id"],
        "control_corpus_sha256": plan["corpus_sha256"],
        "intervention_corpus_sha256": plan["corpus_sha256"],
        "control_case_count": 20,
        "intervention_case_count": 20,
        "control_failure_count": control_failures,
        "intervention_failure_count": intervention_failures,
        "manipulated_domains": [plan["target_domain"]],
        "held_constant_domains": list(plan["held_constant_domains"]),
        "target_before_sha256": _sha({"target": plan["target_domain"], "before": plan["accepted_generation"]}),
        "target_after_sha256": _sha({"target": plan["target_domain"], "after": plan["accepted_generation"]}),
        "non_target_domain_digests": constant,
        "control_runtime_status": "PASS",
        "intervention_runtime_status": "PASS",
        "replicate_count": 2,
        "replicate_consistent": True,
        "source_ref": f"accepted_isolation_test:{plan['target_domain']}:g{plan['accepted_generation']}",
        "performed_by": "ROBERTA Lab",
    }


def _renderer_plans() -> list[dict]:
    plans = generate_experiment_plans(_acquisition_bundle(), corpus_sha256=CORPUS, top_n=1)
    assert [plan["accepted_generation"] for plan in plans] == [0, 1, 2]
    assert all(plan["target_domain"] == "renderer" for plan in plans)
    return plans


def test_top_correlated_suspect_generates_pre_registered_cross_generation_isolation_plans() -> None:
    plans = _renderer_plans()
    assert all(plan["experiment_plan_version"] == EXPERIMENT_PLAN_VERSION for plan in plans)
    assert all(plan["manipulated_domains"] == ["renderer"] for plan in plans)
    assert all(set(plan["held_constant_domains"]) == set(DOMAINS) - {"renderer"} for plan in plans)
    assert all(plan["falsification_condition_required"] is True for plan in plans)
    assert all(plan["no_post_hoc_outcome_editing"] is True for plan in plans)
    assert all(plan["single_generation_confirmation"] is False for plan in plans)
    assert all(plan["correlation_has_causal_authority"] is False for plan in plans)


def test_weak_non_isolating_plan_is_rejected() -> None:
    plan = deepcopy(_renderer_plans()[0])
    plan["manipulated_domains"] = ["renderer", "policy"]
    with pytest.raises(ValueError, match="exactly one target domain"):
        validate_experiment_plan(plan)


def test_result_that_changes_non_target_domain_is_rejected() -> None:
    plan = _renderer_plans()[0]
    result = _result_input(plan, intervention_failures=0)
    domain = plan["held_constant_domains"][0]
    result["non_target_domain_digests"][domain]["intervention_sha256"] = _sha("changed")
    with pytest.raises(ValueError, match="changed a non-target domain"):
        qualify_experiment_result(plan, result, verified_by="Bryant")


def test_supportive_isolation_experiment_emits_admissible_direct_support() -> None:
    plan = _renderer_plans()[0]
    result, qualification = qualify_experiment_result(
        plan,
        _result_input(plan, intervention_failures=0),
        verified_by="Bryant",
    )
    assert result["outcome"] == "SUPPORTS_HYPOTHESIS"
    assert result["control_failure_count"] == 4
    assert result["intervention_failure_count"] == 0
    assert qualification["admissible_direct_evidence"] is True
    assert qualification["direct_evidence_direction"] == "SUPPORTS"
    assert qualification["direct_evidence_strength"] == "DIRECT"
    assert qualification["single_generation_confirmation"] is False


def test_falsification_is_retained_as_direct_contradiction() -> None:
    plan = _renderer_plans()[0]
    result, qualification = qualify_experiment_result(
        plan,
        _result_input(plan, intervention_failures=4),
        verified_by="Bryant",
    )
    assert result["outcome"] == "FALSIFIES_HYPOTHESIS"
    assert qualification["admissible_direct_evidence"] is True
    assert qualification["direct_evidence_direction"] == "CONTRADICTS"
    assert qualification["falsification_retained"] is True


def test_partial_improvement_is_ambiguous_and_emits_no_direct_evidence() -> None:
    plan = _renderer_plans()[0]
    result, qualification = qualify_experiment_result(
        plan,
        _result_input(plan, intervention_failures=2),
        verified_by="Bryant",
    )
    assert result["outcome"] == "AMBIGUOUS_NO_DIRECT_EVIDENCE"
    assert qualification["admissible_direct_evidence"] is False
    assert qualification["direct_evidence_direction"] is None
    assert qualification["direct_evidence_strength"] is None


def test_non_reproducing_control_emits_no_direct_evidence() -> None:
    plan = _renderer_plans()[0]
    result, qualification = qualify_experiment_result(
        plan,
        _result_input(plan, control_failures=0, intervention_failures=0),
        verified_by="Bryant",
    )
    assert result["outcome"] == "NON_REPRODUCING_CONTROL"
    assert qualification["admissible_direct_evidence"] is False


def test_single_generation_direct_support_cannot_confirm_root_cause() -> None:
    acquisition = _acquisition_bundle()
    plan = _renderer_plans()[0]
    ledger, _ = register_experiment_plans(empty_direct_evidence_ledger(), [plan])
    ledger, _ = record_experiment_result(
        ledger,
        plan_id=plan["plan_id"],
        result_input=_result_input(plan, intervention_failures=0),
        verified_by="Bryant",
    )
    direct = build_direct_evidence_bundle(acquisition, ledger)
    validate_direct_evidence_bundle(direct)
    renderer = next(item for item in direct["confirmation_findings"] if item["domain"] == "renderer")
    assert renderer["state"] == "SINGLE_GENERATION_SUPPORT_ONLY"
    assert renderer["lab81_confirmation_candidate"] is False
    assert direct["lab81_confirmation_candidate_domains"] == []
    package = build_lab81_package_with_direct_evidence(_lineage_report(), acquisition, direct)
    assert package["confirmed_root_causes"] == []


def test_two_independent_generations_can_satisfy_lab81_confirmation_threshold() -> None:
    acquisition = _acquisition_bundle()
    plans = _renderer_plans()
    selected = [plans[0], plans[2]]
    ledger, _ = register_experiment_plans(empty_direct_evidence_ledger(), selected)
    for plan in selected:
        ledger, _ = record_experiment_result(
            ledger,
            plan_id=plan["plan_id"],
            result_input=_result_input(plan, intervention_failures=0),
            verified_by="Bryant",
        )
    direct = build_direct_evidence_bundle(acquisition, ledger)
    assert direct["direct_evidence_bundle_version"] == DIRECT_EVIDENCE_BUNDLE_VERSION
    assert direct["lab81_confirmation_candidate_domains"] == ["renderer"]
    renderer = next(item for item in direct["confirmation_findings"] if item["domain"] == "renderer")
    assert renderer["direct_support_generations"] == [0, 2]
    assert renderer["zero_contradictions"] is True
    package = build_lab81_package_with_direct_evidence(_lineage_report(), acquisition, direct)
    assert package["confirmed_root_causes"] == ["renderer"]
    assert package["root_cause_named"] is True
    summary = direct_evidence_summary(direct)
    assert summary["single_generation_confirmation"] is False
    assert summary["causal_authority"] is False


def test_cross_generation_support_plus_falsification_blocks_confirmation() -> None:
    acquisition = _acquisition_bundle()
    plans = _renderer_plans()
    ledger, _ = register_experiment_plans(empty_direct_evidence_ledger(), plans)
    outcomes = {0: 0, 1: 4, 2: 0}
    for plan in plans:
        ledger, _ = record_experiment_result(
            ledger,
            plan_id=plan["plan_id"],
            result_input=_result_input(plan, intervention_failures=outcomes[plan["accepted_generation"]]),
            verified_by="Bryant",
        )
    direct = build_direct_evidence_bundle(acquisition, ledger)
    renderer = next(item for item in direct["confirmation_findings"] if item["domain"] == "renderer")
    assert renderer["state"] == "FALSIFIED_OR_CONTRADICTED"
    assert renderer["direct_support_generations"] == [0, 2]
    assert renderer["direct_contradiction_generations"] == [1]
    assert renderer["lab81_confirmation_candidate"] is False
    package = build_lab81_package_with_direct_evidence(_lineage_report(), acquisition, direct)
    assert package["confirmed_root_causes"] == []


def test_one_final_result_per_plan_prevents_outcome_shopping() -> None:
    plan = _renderer_plans()[0]
    ledger, _ = register_experiment_plans(empty_direct_evidence_ledger(), [plan])
    supportive = _result_input(plan, intervention_failures=0)
    ledger, first = record_experiment_result(
        ledger,
        plan_id=plan["plan_id"],
        result_input=supportive,
        verified_by="Bryant",
    )
    assert first["status"] == "RECORDED"
    unchanged, second = record_experiment_result(
        ledger,
        plan_id=plan["plan_id"],
        result_input=supportive,
        verified_by="Bryant",
    )
    assert second["status"] == "UNCHANGED"
    assert unchanged == ledger
    with pytest.raises(ValueError, match="conflicting final result"):
        record_experiment_result(
            ledger,
            plan_id=plan["plan_id"],
            result_input=_result_input(plan, intervention_failures=4),
            verified_by="Bryant",
        )


def test_tracked_ledger_contract_is_zero_authority_and_duplicate_safe() -> None:
    ledger = empty_direct_evidence_ledger()
    validate_direct_evidence_ledger(ledger)
    assert ledger["policy"]["pre_registration_required"] is True
    assert ledger["policy"]["one_final_result_per_plan"] is True
    assert ledger["policy"]["falsification_required"] is True
    assert ledger["policy"]["single_generation_confirmation"] is False
    assert ledger["policy"]["production_code_mutation"] is False
    assert ledger["policy"]["execution_authorized"] is False
