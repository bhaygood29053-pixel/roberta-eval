from __future__ import annotations

import hashlib
from copy import deepcopy

import pytest

from roberta_eval.human_remediation_root_cause import DOMAINS
from roberta_eval.human_root_cause_direct_evidence import (
    EXPERIMENT_PLAN_VERSION,
    empty_direct_evidence_ledger,
    register_experiment_plans,
)
from roberta_eval.human_root_cause_experiment_execution import (
    EXECUTION_LEDGER_VERSION,
    build_execution_manifest,
    corpus_sha256,
    empty_execution_ledger,
    execute_controlled_experiment,
    qualify_receipt_with_lab85,
    receipt_to_lab85_result_input,
    record_execution_receipt,
    submit_receipt_to_lab85,
    validate_execution_ledger,
    validate_execution_receipt,
)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _cases(count: int = 24) -> list[dict[str, str]]:
    return [
        {"case_id": f"case-{index:03d}", "input_sha256": _sha(f"input-{index}")}
        for index in range(count)
    ]


def _plan(cases: list[dict[str, str]]) -> dict:
    target = "renderer"
    held = [domain for domain in DOMAINS if domain != target]
    core = {
        "experiment_plan_version": EXPERIMENT_PLAN_VERSION,
        "evidence_bundle_version": "roberta_human_root_cause_evidence_bundle/v1",
        "evidence_bundle_sha256": _sha("bundle"),
        "family_root_fingerprint": _sha("family"),
        "failure_code": "technical_language_leak",
        "service": "pre_trade",
        "target_domain": target,
        "accepted_generation": 2,
        "correlation_signal": "REPEATED_CROSS_GENERATION_ASSOCIATION",
        "correlation_score": 20,
        "correlation_has_causal_authority": False,
        "corpus_sha256": corpus_sha256(cases),
        "minimum_case_count": 20,
        "minimum_replicate_count": 2,
        "primary_metric": "targeted_failure_count",
        "manipulated_domains": [target],
        "held_constant_domains": held,
        "control_condition": {
            "id": "ACCEPTED_BASELINE",
            "description": "Run accepted baseline.",
        },
        "intervention_condition": {
            "id": "ISOLATED_TARGET_DOMAIN_CORRECTION",
            "description": "Change renderer only.",
        },
        "pre_registered_outcome_rules": {
            "SUPPORTS_HYPOTHESIS": "control fails and intervention reaches zero",
            "FALSIFIES_HYPOTHESIS": "control fails and intervention is unchanged or worse",
            "AMBIGUOUS_NO_DIRECT_EVIDENCE": "partial improvement",
            "NON_REPRODUCING_CONTROL": "control does not reproduce",
        },
        "single_manipulated_factor": True,
        "matched_corpus_required": True,
        "non_target_domains_held_constant_required": True,
        "target_artifact_change_required": True,
        "deterministic_inputs_required": True,
        "falsification_condition_required": True,
        "pre_registered": True,
        "no_post_hoc_outcome_editing": True,
        "one_final_result_per_plan": True,
        "single_generation_confirmation": False,
        "direct_evidence_authority": "QUALIFIED_EXPERIMENT_ONLY",
        "root_cause_confirmation_authority": "LAB_81_ONLY",
        "read_only_plan": True,
        "production_code_mutation": False,
        "execution_authorized": False,
    }
    import json

    payload = json.dumps(core, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    core["plan_id"] = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return core


def _digests(*, target_after: str = "renderer-intervention") -> tuple[dict[str, str], dict[str, str]]:
    control = {domain: _sha(f"control-{domain}") for domain in DOMAINS}
    intervention = dict(control)
    intervention["renderer"] = _sha(target_after)
    return control, intervention


def _manifest(plan: dict, cases: list[dict[str, str]]) -> dict:
    control, intervention = _digests()
    return build_execution_manifest(
        plan,
        corpus_cases=cases,
        control_runtime_sha256=_sha("control-runtime"),
        intervention_runtime_sha256=_sha("intervention-runtime"),
        control_domain_digests=control,
        intervention_domain_digests=intervention,
    )


class FakeAdapter:
    def __init__(self, *, intervention_failures: int = 0, order_drift: bool = False, inconsistent: bool = False) -> None:
        self.intervention_failures = intervention_failures
        self.order_drift = order_drift
        self.inconsistent = inconsistent
        self.calls = {"CONTROL": 0, "INTERVENTION": 0}

    def run_arm(self, *, plan, arm, environment, cases, deterministic_seed):
        self.calls[arm] += 1
        failure_count = 4 if arm == "CONTROL" else self.intervention_failures
        rows = []
        for index, case in enumerate(cases):
            failed = index < failure_count
            if self.inconsistent and arm == "CONTROL" and self.calls[arm] > 1 and index == 0:
                failed = not failed
            rows.append(
                {
                    "case_id": case["case_id"],
                    "input_sha256": case["input_sha256"],
                    "targeted_failure": failed,
                    "output_sha256": _sha(f"{arm}:{case['case_id']}:{failed}"),
                }
            )
        if self.order_drift and arm == "INTERVENTION":
            rows = list(reversed(rows))
        return {
            "arm": arm,
            "runtime_status": "PASS",
            "deterministic_seed": deterministic_seed,
            "environment_id": environment["environment_id"],
            "case_results": rows,
        }


def test_manifest_freezes_plan_corpus_and_artifact_boundaries() -> None:
    cases = _cases()
    plan = _plan(cases)
    manifest = _manifest(plan, cases)
    assert manifest["experiment_plan_id"] == plan["plan_id"]
    assert manifest["corpus_sha256"] == plan["corpus_sha256"]
    assert manifest["definition_frozen_before_execution"] is True
    assert manifest["runner_outcome_authority"] is False
    assert manifest["control_environment"]["domain_digests"]["renderer"] != manifest["intervention_environment"]["domain_digests"]["renderer"]
    for domain in plan["held_constant_domains"]:
        assert manifest["control_environment"]["domain_digests"][domain] == manifest["intervention_environment"]["domain_digests"][domain]


def test_manifest_rejects_corpus_or_non_target_artifact_drift() -> None:
    cases = _cases()
    plan = _plan(cases)
    changed_cases = deepcopy(cases)
    changed_cases[0]["input_sha256"] = _sha("changed")
    control, intervention = _digests()
    with pytest.raises(ValueError, match="corpus"):
        build_execution_manifest(
            plan,
            corpus_cases=changed_cases,
            control_runtime_sha256=_sha("control-runtime"),
            intervention_runtime_sha256=_sha("intervention-runtime"),
            control_domain_digests=control,
            intervention_domain_digests=intervention,
        )
    intervention["policy"] = _sha("policy-drift")
    with pytest.raises(ValueError, match="non-target domain drift"):
        build_execution_manifest(
            plan,
            corpus_cases=cases,
            control_runtime_sha256=_sha("control-runtime"),
            intervention_runtime_sha256=_sha("intervention-runtime"),
            control_domain_digests=control,
            intervention_domain_digests=intervention,
        )


def test_execution_receipt_is_reproducible_observations_only() -> None:
    cases = _cases()
    plan = _plan(cases)
    manifest = _manifest(plan, cases)
    receipt = execute_controlled_experiment(plan, manifest, FakeAdapter(), performed_by="LAB")
    validate_execution_receipt(receipt, plan=plan, manifest=manifest)
    assert receipt["control_failure_count"] == 4
    assert receipt["intervention_failure_count"] == 0
    assert receipt["reproducibility"]["replicate_count"] == 2
    assert receipt["reproducibility"]["replicate_consistent"] is True
    assert receipt["observations_only"] is True
    assert receipt["runner_outcome_authority"] is False
    assert "outcome" not in receipt


def test_execution_rejects_case_order_and_replicate_drift() -> None:
    cases = _cases()
    plan = _plan(cases)
    manifest = _manifest(plan, cases)
    with pytest.raises(ValueError, match="case order drift"):
        execute_controlled_experiment(plan, manifest, FakeAdapter(order_drift=True), performed_by="LAB")
    with pytest.raises(ValueError, match="replicates are not deterministic"):
        execute_controlled_experiment(plan, manifest, FakeAdapter(inconsistent=True), performed_by="LAB")


def test_modified_plan_cannot_reuse_frozen_manifest() -> None:
    cases = _cases()
    plan = _plan(cases)
    manifest = _manifest(plan, cases)
    altered = deepcopy(plan)
    altered["minimum_case_count"] = 21
    with pytest.raises(ValueError):
        execute_controlled_experiment(altered, manifest, FakeAdapter(), performed_by="LAB")


def test_receipt_handoff_to_lab85_preserves_qualification_authority() -> None:
    cases = _cases()
    plan = _plan(cases)
    manifest = _manifest(plan, cases)
    receipt = execute_controlled_experiment(plan, manifest, FakeAdapter(), performed_by="LAB")
    result_input = receipt_to_lab85_result_input(plan, manifest, receipt)
    assert "outcome" not in result_input
    result, qualification = qualify_receipt_with_lab85(
        plan,
        manifest,
        receipt,
        verified_by="Bryant",
    )
    assert result["outcome"] == "SUPPORTS_HYPOTHESIS"
    assert qualification["admissible_direct_evidence"] is True
    assert qualification["direct_evidence_direction"] == "SUPPORTS"


def test_falsification_is_decided_by_lab85_not_runner() -> None:
    cases = _cases()
    plan = _plan(cases)
    manifest = _manifest(plan, cases)
    receipt = execute_controlled_experiment(
        plan,
        manifest,
        FakeAdapter(intervention_failures=4),
        performed_by="LAB",
    )
    assert "outcome" not in receipt
    result, qualification = qualify_receipt_with_lab85(plan, manifest, receipt, verified_by="Bryant")
    assert result["outcome"] == "FALSIFIES_HYPOTHESIS"
    assert qualification["direct_evidence_direction"] == "CONTRADICTS"
    assert qualification["falsification_retained"] is True


def test_receipt_can_be_submitted_to_existing_lab85_ledger_unchanged() -> None:
    cases = _cases()
    plan = _plan(cases)
    manifest = _manifest(plan, cases)
    receipt = execute_controlled_experiment(plan, manifest, FakeAdapter(), performed_by="LAB")
    direct, _ = register_experiment_plans(empty_direct_evidence_ledger(), [plan])
    updated, result = submit_receipt_to_lab85(
        direct,
        plan,
        manifest,
        receipt,
        verified_by="Bryant",
    )
    assert result["status"] == "RECORDED"
    assert result["qualification"]["direct_evidence_direction"] == "SUPPORTS"
    assert len(updated["results"]) == 1


def test_execution_ledger_is_immutable_and_conflicting_rerun_fails_closed() -> None:
    cases = _cases()
    plan = _plan(cases)
    manifest = _manifest(plan, cases)
    receipt = execute_controlled_experiment(plan, manifest, FakeAdapter(), performed_by="LAB")
    ledger, result = record_execution_receipt(
        empty_execution_ledger(),
        plan=plan,
        manifest=manifest,
        receipt=receipt,
    )
    assert result["status"] == "RECORDED"
    same, retry = record_execution_receipt(ledger, plan=plan, manifest=manifest, receipt=receipt)
    assert retry["status"] == "UNCHANGED"
    assert same == ledger
    conflicting = execute_controlled_experiment(plan, manifest, FakeAdapter(), performed_by="Other")
    with pytest.raises(ValueError, match="conflicting controlled experiment rerun"):
        record_execution_receipt(ledger, plan=plan, manifest=manifest, receipt=conflicting)


def test_tracked_execution_ledger_contract_is_zero_production_authority() -> None:
    ledger = empty_execution_ledger()
    validate_execution_ledger(ledger)
    assert ledger["ledger_version"] == EXECUTION_LEDGER_VERSION
    assert ledger["executions"] == []
    assert ledger["policy"]["runner_outcome_authority"] is False
    assert ledger["policy"]["lab85_qualification_authority"] is True
    assert ledger["policy"]["production_code_mutation"] is False
    assert ledger["policy"]["execution_authorized"] is False
