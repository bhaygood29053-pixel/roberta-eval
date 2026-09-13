from __future__ import annotations

from pathlib import Path
from typing import Any

from .human_root_cause_artifact_sandbox import (
    SANDBOX_HANDOFF_VERSION,
    MaterializedHumanSandboxAdapter,
    lab87_corpus_cases,
    validate_materialization,
)
from .human_root_cause_direct_evidence import (
    qualify_experiment_result,
    validate_direct_evidence_ledger,
)
from .human_root_cause_experiment_execution import (
    build_execution_manifest,
    corpus_sha256,
    execute_controlled_experiment,
    receipt_to_lab85_result_input,
    submit_receipt_to_lab85,
    validate_execution_receipt,
)


def _stable_sha256(value: Any) -> str:
    import hashlib
    import json

    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def execute_materialized_handoff(
    plan: dict[str, Any],
    pin: dict[str, Any],
    control_manifest: dict[str, Any],
    intervention_manifest: dict[str, Any],
    materialization: dict[str, Any],
    *,
    control_root: Path,
    intervention_root: Path,
    sandbox_cases: list[dict[str, Any]],
    performed_by: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Execute LAB #89 while preserving the exact LAB #87 manifest in the handoff."""

    validate_materialization(
        materialization,
        plan=plan,
        pin=pin,
        control=control_manifest,
        intervention=intervention_manifest,
    )
    cases = lab87_corpus_cases(sandbox_cases)
    if corpus_sha256(cases) != plan["corpus_sha256"]:
        raise ValueError("materialized sandbox corpus does not match pre-registered LAB #85 plan")
    manifest = build_execution_manifest(
        plan,
        corpus_cases=cases,
        control_runtime_sha256=control_manifest["tree_sha256"],
        intervention_runtime_sha256=intervention_manifest["tree_sha256"],
        control_domain_digests=control_manifest["domain_digests"],
        intervention_domain_digests=intervention_manifest["domain_digests"],
    )
    adapter = MaterializedHumanSandboxAdapter(
        pin=pin,
        control_root=control_root,
        intervention_root=intervention_root,
        sandbox_cases=sandbox_cases,
    )
    receipt = execute_controlled_experiment(plan, manifest, adapter, performed_by=performed_by)
    validate_execution_receipt(receipt, plan=plan, manifest=manifest)
    handoff = {
        "sandbox_handoff_version": SANDBOX_HANDOFF_VERSION,
        "experiment_plan_id": plan["plan_id"],
        "source_pin_sha256": pin["source_pin_sha256"],
        "materialization_id": materialization["materialization_id"],
        "lab87_manifest_id": manifest["manifest_id"],
        "lab87_receipt_id": receipt["receipt_id"],
        "manifest_preserved_for_lab85": True,
        "runner_outcome_authority": False,
        "lab85_qualification_authority": True,
        "production_runtime_touched": False,
        "production_code_mutation": False,
        "execution_authorized": False,
    }
    handoff["handoff_id"] = _stable_sha256(handoff)
    return manifest, receipt, handoff


def qualify_materialized_handoff_with_lab85(
    plan: dict[str, Any],
    manifest: dict[str, Any],
    receipt: dict[str, Any],
    *,
    verified_by: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    result_input = receipt_to_lab85_result_input(plan, manifest, receipt)
    return qualify_experiment_result(plan, result_input, verified_by=verified_by)


def submit_materialized_handoff_to_lab85(
    direct_evidence_ledger: dict[str, Any],
    plan: dict[str, Any],
    manifest: dict[str, Any],
    receipt: dict[str, Any],
    *,
    verified_by: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    validate_direct_evidence_ledger(direct_evidence_ledger)
    return submit_receipt_to_lab85(
        direct_evidence_ledger,
        plan,
        manifest,
        receipt,
        verified_by=verified_by,
    )
