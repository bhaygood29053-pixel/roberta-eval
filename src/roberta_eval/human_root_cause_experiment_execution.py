from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Protocol

from .human_remediation_root_cause import DOMAINS
from .human_root_cause_direct_evidence import (
    MINIMUM_MATCHED_CASE_COUNT,
    MINIMUM_REPLICATE_COUNT,
    qualify_experiment_result,
    record_experiment_result,
    validate_direct_evidence_ledger,
    validate_experiment_plan,
)

EXECUTION_ENVIRONMENT_VERSION = "roberta_human_root_cause_execution_environment/v1"
EXECUTION_MANIFEST_VERSION = "roberta_human_root_cause_execution_manifest/v1"
REPLICATE_RECEIPT_VERSION = "roberta_human_root_cause_replicate_receipt/v1"
EXECUTION_RECEIPT_VERSION = "roberta_human_root_cause_execution_receipt/v1"
REPRODUCIBILITY_VERSION = "roberta_human_root_cause_reproducibility/v1"
EXECUTION_LEDGER_VERSION = "roberta_human_root_cause_execution_ledger/v1"


def _stable_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(ch in "0123456789abcdefABCDEF" for ch in value)


def default_execution_ledger_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "human_root_cause_experiment_execution_ledger.json"


def empty_execution_ledger() -> dict[str, Any]:
    return {
        "ledger_version": EXECUTION_LEDGER_VERSION,
        "policy": {
            "experiment_definition_frozen": True,
            "one_execution_receipt_per_plan": True,
            "matched_ordered_corpus_required": True,
            "artifact_digest_verification_required": True,
            "deterministic_reproducibility_required": True,
            "runner_outcome_authority": False,
            "lab85_qualification_authority": True,
            "bounded_evaluation_execution": True,
            "external_calls_required": False,
            "production_code_mutation": False,
            "github_issue_mutation": False,
            "execution_authorized": False,
        },
        "executions": [],
    }


def load_execution_ledger(path: Path | None = None) -> dict[str, Any]:
    source = path or default_execution_ledger_path()
    payload = json.loads(source.read_text(encoding="utf-8"))
    validate_execution_ledger(payload)
    return payload


def write_execution_ledger(path: Path, ledger: dict[str, Any]) -> None:
    validate_execution_ledger(ledger)
    path.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def normalize_corpus_cases(cases: list[dict[str, Any]]) -> list[dict[str, str]]:
    if not isinstance(cases, list) or not cases:
        raise ValueError("controlled experiment corpus must be a non-empty list")
    normalized: list[dict[str, str]] = []
    ids: set[str] = set()
    for row in cases:
        if not isinstance(row, dict):
            raise ValueError("controlled experiment corpus case must be an object")
        case_id = row.get("case_id")
        input_sha = row.get("input_sha256")
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError("controlled experiment case_id is required")
        if case_id in ids:
            raise ValueError("controlled experiment corpus contains duplicate case_id")
        if not _is_sha256(input_sha):
            raise ValueError("controlled experiment case input_sha256 is invalid")
        ids.add(case_id)
        normalized.append({"case_id": case_id.strip(), "input_sha256": input_sha.lower()})
    return normalized


def corpus_sha256(cases: list[dict[str, Any]]) -> str:
    return _stable_sha256(normalize_corpus_cases(cases))


def _normalize_domain_digests(value: dict[str, str]) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != set(DOMAINS):
        raise ValueError("controlled experiment environment must provide every Human domain digest")
    normalized: dict[str, str] = {}
    for domain in DOMAINS:
        digest = value.get(domain)
        if not _is_sha256(digest):
            raise ValueError(f"controlled experiment artifact digest is invalid for domain: {domain}")
        normalized[domain] = digest.lower()
    return normalized


def _environment(
    *,
    arm: str,
    plan: dict[str, Any],
    runtime_sha256: str,
    domain_digests: dict[str, str],
) -> dict[str, Any]:
    if arm not in {"CONTROL", "INTERVENTION"}:
        raise ValueError("controlled experiment arm is invalid")
    if not _is_sha256(runtime_sha256):
        raise ValueError("controlled experiment runtime digest is invalid")
    core = {
        "execution_environment_version": EXECUTION_ENVIRONMENT_VERSION,
        "experiment_plan_id": plan["plan_id"],
        "arm": arm,
        "runtime_sha256": runtime_sha256.lower(),
        "domain_digests": _normalize_domain_digests(domain_digests),
        "ephemeral": True,
        "production_code_mutation": False,
        "execution_authorized": False,
    }
    core["environment_id"] = _stable_sha256(core)
    return core


def build_execution_manifest(
    plan: dict[str, Any],
    *,
    corpus_cases: list[dict[str, Any]],
    control_runtime_sha256: str,
    intervention_runtime_sha256: str,
    control_domain_digests: dict[str, str],
    intervention_domain_digests: dict[str, str],
) -> dict[str, Any]:
    validate_experiment_plan(plan)
    cases = normalize_corpus_cases(corpus_cases)
    observed_corpus_sha = corpus_sha256(cases)
    if observed_corpus_sha != plan["corpus_sha256"]:
        raise ValueError("controlled experiment corpus does not match the pre-registered plan digest")
    if len(cases) < int(plan["minimum_case_count"]):
        raise ValueError("controlled experiment corpus is below the pre-registered minimum case count")

    control = _environment(
        arm="CONTROL",
        plan=plan,
        runtime_sha256=control_runtime_sha256,
        domain_digests=control_domain_digests,
    )
    intervention = _environment(
        arm="INTERVENTION",
        plan=plan,
        runtime_sha256=intervention_runtime_sha256,
        domain_digests=intervention_domain_digests,
    )

    target = plan["target_domain"]
    if control["domain_digests"][target] == intervention["domain_digests"][target]:
        raise ValueError("controlled experiment target-domain artifact did not change")
    for domain in plan["held_constant_domains"]:
        if control["domain_digests"][domain] != intervention["domain_digests"][domain]:
            raise ValueError(f"controlled experiment non-target domain drift detected: {domain}")

    frozen_fields = {
        "experiment_plan_id": plan["plan_id"],
        "evidence_bundle_sha256": plan["evidence_bundle_sha256"],
        "family_root_fingerprint": plan["family_root_fingerprint"],
        "target_domain": plan["target_domain"],
        "accepted_generation": plan["accepted_generation"],
        "corpus_sha256": plan["corpus_sha256"],
        "minimum_case_count": plan["minimum_case_count"],
        "minimum_replicate_count": plan["minimum_replicate_count"],
        "manipulated_domains": deepcopy(plan["manipulated_domains"]),
        "held_constant_domains": deepcopy(plan["held_constant_domains"]),
        "pre_registered_outcome_rules": deepcopy(plan["pre_registered_outcome_rules"]),
    }
    core = {
        "execution_manifest_version": EXECUTION_MANIFEST_VERSION,
        "experiment_plan_id": plan["plan_id"],
        "plan_definition_sha256": _stable_sha256(plan),
        "frozen_plan_fields": frozen_fields,
        "corpus_sha256": observed_corpus_sha,
        "case_count": len(cases),
        "ordered_cases": cases,
        "control_environment": control,
        "intervention_environment": intervention,
        "replicate_count": int(plan["minimum_replicate_count"]),
        "seed_derivation": "sha256(plan_id:corpus_sha256:replicate_index)",
        "definition_frozen_before_execution": True,
        "runner_outcome_authority": False,
        "lab85_qualification_authority": True,
        "bounded_evaluation_execution": True,
        "production_code_mutation": False,
        "github_issue_mutation": False,
        "execution_authorized": False,
    }
    core["manifest_id"] = _stable_sha256(core)
    validate_execution_manifest(core, plan=plan)
    return core


def validate_execution_environment(environment: dict[str, Any], *, plan: dict[str, Any]) -> None:
    if environment.get("execution_environment_version") != EXECUTION_ENVIRONMENT_VERSION:
        raise ValueError("unsupported controlled experiment environment version")
    if environment.get("experiment_plan_id") != plan["plan_id"]:
        raise ValueError("controlled experiment environment plan identity mismatch")
    if environment.get("arm") not in {"CONTROL", "INTERVENTION"}:
        raise ValueError("controlled experiment environment arm is invalid")
    if not _is_sha256(environment.get("runtime_sha256")):
        raise ValueError("controlled experiment environment runtime digest is invalid")
    _normalize_domain_digests(environment.get("domain_digests"))
    if environment.get("ephemeral") is not True:
        raise ValueError("controlled experiment environment must be ephemeral")
    if environment.get("production_code_mutation") is not False or environment.get("execution_authorized") is not False:
        raise ValueError("controlled experiment environment exceeds authority boundary")
    expected = {key: value for key, value in environment.items() if key != "environment_id"}
    if environment.get("environment_id") != _stable_sha256(expected):
        raise ValueError("controlled experiment environment digest mismatch")


def validate_execution_manifest(manifest: dict[str, Any], *, plan: dict[str, Any]) -> None:
    validate_experiment_plan(plan)
    if manifest.get("execution_manifest_version") != EXECUTION_MANIFEST_VERSION:
        raise ValueError("unsupported controlled experiment manifest version")
    if manifest.get("experiment_plan_id") != plan["plan_id"]:
        raise ValueError("controlled experiment manifest plan identity mismatch")
    if manifest.get("plan_definition_sha256") != _stable_sha256(plan):
        raise ValueError("controlled experiment plan changed after pre-registration")
    frozen = manifest.get("frozen_plan_fields")
    expected_frozen = {
        "experiment_plan_id": plan["plan_id"],
        "evidence_bundle_sha256": plan["evidence_bundle_sha256"],
        "family_root_fingerprint": plan["family_root_fingerprint"],
        "target_domain": plan["target_domain"],
        "accepted_generation": plan["accepted_generation"],
        "corpus_sha256": plan["corpus_sha256"],
        "minimum_case_count": plan["minimum_case_count"],
        "minimum_replicate_count": plan["minimum_replicate_count"],
        "manipulated_domains": plan["manipulated_domains"],
        "held_constant_domains": plan["held_constant_domains"],
        "pre_registered_outcome_rules": plan["pre_registered_outcome_rules"],
    }
    if frozen != expected_frozen:
        raise ValueError("controlled experiment manifest altered frozen plan fields")
    cases = normalize_corpus_cases(manifest.get("ordered_cases"))
    if manifest.get("case_count") != len(cases) or len(cases) < int(plan["minimum_case_count"]):
        raise ValueError("controlled experiment manifest case count is invalid")
    if manifest.get("corpus_sha256") != corpus_sha256(cases) or manifest["corpus_sha256"] != plan["corpus_sha256"]:
        raise ValueError("controlled experiment manifest corpus identity mismatch")
    if manifest.get("replicate_count") != int(plan["minimum_replicate_count"]):
        raise ValueError("controlled experiment manifest replicate count differs from pre-registration")
    control = manifest.get("control_environment")
    intervention = manifest.get("intervention_environment")
    if not isinstance(control, dict) or not isinstance(intervention, dict):
        raise ValueError("controlled experiment manifest requires both environments")
    validate_execution_environment(control, plan=plan)
    validate_execution_environment(intervention, plan=plan)
    if control["arm"] != "CONTROL" or intervention["arm"] != "INTERVENTION":
        raise ValueError("controlled experiment environment arms are swapped")
    target = plan["target_domain"]
    if control["domain_digests"][target] == intervention["domain_digests"][target]:
        raise ValueError("controlled experiment manifest lacks target-domain artifact change")
    for domain in plan["held_constant_domains"]:
        if control["domain_digests"][domain] != intervention["domain_digests"][domain]:
            raise ValueError("controlled experiment manifest contains non-target artifact drift")
    for key, expected in {
        "definition_frozen_before_execution": True,
        "runner_outcome_authority": False,
        "lab85_qualification_authority": True,
        "bounded_evaluation_execution": True,
        "production_code_mutation": False,
        "github_issue_mutation": False,
        "execution_authorized": False,
    }.items():
        if manifest.get(key) != expected:
            raise ValueError(f"controlled experiment manifest policy mismatch: {key}")
    expected = {key: value for key, value in manifest.items() if key != "manifest_id"}
    if manifest.get("manifest_id") != _stable_sha256(expected):
        raise ValueError("controlled experiment manifest digest mismatch")


class ControlledExperimentAdapter(Protocol):
    def run_arm(
        self,
        *,
        plan: dict[str, Any],
        arm: str,
        environment: dict[str, Any],
        cases: list[dict[str, str]],
        deterministic_seed: str,
    ) -> dict[str, Any]: ...


def _replicate_seed(plan: dict[str, Any], manifest: dict[str, Any], replicate_index: int) -> str:
    return hashlib.sha256(
        f"{plan['plan_id']}:{manifest['corpus_sha256']}:{replicate_index}".encode("utf-8")
    ).hexdigest()


def _normalize_arm_observation(
    payload: dict[str, Any],
    *,
    arm: str,
    cases: list[dict[str, str]],
    seed: str,
    environment: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("controlled experiment adapter returned an invalid observation")
    if payload.get("arm") != arm:
        raise ValueError("controlled experiment adapter arm identity mismatch")
    if payload.get("runtime_status") != "PASS":
        raise ValueError("controlled experiment runtime did not pass")
    if payload.get("deterministic_seed") != seed:
        raise ValueError("controlled experiment adapter changed the deterministic seed")
    if payload.get("environment_id") != environment["environment_id"]:
        raise ValueError("controlled experiment adapter environment identity mismatch")
    rows = payload.get("case_results")
    if not isinstance(rows, list) or len(rows) != len(cases):
        raise ValueError("controlled experiment adapter returned missing or extra cases")
    normalized_rows: list[dict[str, Any]] = []
    for expected_case, row in zip(cases, rows):
        if not isinstance(row, dict):
            raise ValueError("controlled experiment case result must be an object")
        if row.get("case_id") != expected_case["case_id"]:
            raise ValueError("controlled experiment case order drift detected")
        if row.get("input_sha256") != expected_case["input_sha256"]:
            raise ValueError("controlled experiment case input digest drift detected")
        if not isinstance(row.get("targeted_failure"), bool):
            raise ValueError("controlled experiment targeted_failure must be boolean")
        if not _is_sha256(row.get("output_sha256")):
            raise ValueError("controlled experiment output digest is invalid")
        normalized_rows.append(
            {
                "case_id": expected_case["case_id"],
                "input_sha256": expected_case["input_sha256"],
                "targeted_failure": row["targeted_failure"],
                "output_sha256": row["output_sha256"].lower(),
            }
        )
    failure_ids = [row["case_id"] for row in normalized_rows if row["targeted_failure"]]
    core = {
        "arm": arm,
        "environment_id": environment["environment_id"],
        "runtime_status": "PASS",
        "deterministic_seed": seed,
        "case_count": len(normalized_rows),
        "failure_count": len(failure_ids),
        "failure_case_ids": failure_ids,
        "case_results": normalized_rows,
    }
    core["observation_sha256"] = _stable_sha256(core)
    return core


def _replicate_receipt(
    *,
    plan: dict[str, Any],
    manifest: dict[str, Any],
    replicate_index: int,
    seed: str,
    control: dict[str, Any],
    intervention: dict[str, Any],
) -> dict[str, Any]:
    core = {
        "replicate_receipt_version": REPLICATE_RECEIPT_VERSION,
        "experiment_plan_id": plan["plan_id"],
        "manifest_id": manifest["manifest_id"],
        "replicate_index": replicate_index,
        "deterministic_seed": seed,
        "control_observation": control,
        "intervention_observation": intervention,
        "runner_outcome_authority": False,
        "production_code_mutation": False,
        "execution_authorized": False,
    }
    core["replicate_receipt_id"] = _stable_sha256(core)
    return core


def _assert_replicate_consistency(replicates: list[dict[str, Any]], *, arm: str) -> dict[str, Any]:
    key = "control_observation" if arm == "CONTROL" else "intervention_observation"
    observations = [row[key] for row in replicates]
    first = observations[0]
    signature = {
        "failure_count": first["failure_count"],
        "failure_case_ids": first["failure_case_ids"],
        "case_results": [
            {
                "case_id": item["case_id"],
                "targeted_failure": item["targeted_failure"],
                "output_sha256": item["output_sha256"],
            }
            for item in first["case_results"]
        ],
    }
    for observation in observations[1:]:
        other = {
            "failure_count": observation["failure_count"],
            "failure_case_ids": observation["failure_case_ids"],
            "case_results": [
                {
                    "case_id": item["case_id"],
                    "targeted_failure": item["targeted_failure"],
                    "output_sha256": item["output_sha256"],
                }
                for item in observation["case_results"]
            ],
        }
        if other != signature:
            raise ValueError(f"controlled experiment {arm.lower()} replicates are not deterministic")
    return {
        "arm": arm,
        "replicate_count": len(observations),
        "failure_count": first["failure_count"],
        "failure_case_ids": first["failure_case_ids"],
        "deterministic": True,
        "reproducibility_sha256": _stable_sha256(signature),
    }


def execute_controlled_experiment(
    plan: dict[str, Any],
    manifest: dict[str, Any],
    adapter: ControlledExperimentAdapter,
    *,
    performed_by: str,
) -> dict[str, Any]:
    validate_execution_manifest(manifest, plan=plan)
    performed_by = performed_by.strip()
    if not performed_by:
        raise ValueError("controlled experiment performer identity is required")
    cases = manifest["ordered_cases"]
    replicates: list[dict[str, Any]] = []
    for replicate_index in range(1, int(manifest["replicate_count"]) + 1):
        seed = _replicate_seed(plan, manifest, replicate_index)
        control_raw = adapter.run_arm(
            plan=deepcopy(plan),
            arm="CONTROL",
            environment=deepcopy(manifest["control_environment"]),
            cases=deepcopy(cases),
            deterministic_seed=seed,
        )
        intervention_raw = adapter.run_arm(
            plan=deepcopy(plan),
            arm="INTERVENTION",
            environment=deepcopy(manifest["intervention_environment"]),
            cases=deepcopy(cases),
            deterministic_seed=seed,
        )
        control = _normalize_arm_observation(
            control_raw,
            arm="CONTROL",
            cases=cases,
            seed=seed,
            environment=manifest["control_environment"],
        )
        intervention = _normalize_arm_observation(
            intervention_raw,
            arm="INTERVENTION",
            cases=cases,
            seed=seed,
            environment=manifest["intervention_environment"],
        )
        replicates.append(
            _replicate_receipt(
                plan=plan,
                manifest=manifest,
                replicate_index=replicate_index,
                seed=seed,
                control=control,
                intervention=intervention,
            )
        )

    control_repro = _assert_replicate_consistency(replicates, arm="CONTROL")
    intervention_repro = _assert_replicate_consistency(replicates, arm="INTERVENTION")
    reproducibility = {
        "reproducibility_version": REPRODUCIBILITY_VERSION,
        "experiment_plan_id": plan["plan_id"],
        "manifest_id": manifest["manifest_id"],
        "replicate_count": len(replicates),
        "minimum_replicate_count": int(plan["minimum_replicate_count"]),
        "control": control_repro,
        "intervention": intervention_repro,
        "matched_ordered_corpus": True,
        "artifact_digest_verification": True,
        "replicate_consistent": True,
    }
    reproducibility["reproducibility_id"] = _stable_sha256(reproducibility)

    core = {
        "execution_receipt_version": EXECUTION_RECEIPT_VERSION,
        "experiment_plan_id": plan["plan_id"],
        "plan_definition_sha256": manifest["plan_definition_sha256"],
        "manifest_id": manifest["manifest_id"],
        "family_root_fingerprint": plan["family_root_fingerprint"],
        "target_domain": plan["target_domain"],
        "accepted_generation": plan["accepted_generation"],
        "corpus_sha256": plan["corpus_sha256"],
        "case_count": manifest["case_count"],
        "performed_by": performed_by,
        "control_environment_id": manifest["control_environment"]["environment_id"],
        "intervention_environment_id": manifest["intervention_environment"]["environment_id"],
        "replicates": replicates,
        "reproducibility": reproducibility,
        "control_failure_count": control_repro["failure_count"],
        "intervention_failure_count": intervention_repro["failure_count"],
        "observations_only": True,
        "contains_causal_outcome": False,
        "runner_outcome_authority": False,
        "lab85_qualification_authority": True,
        "definition_frozen_before_execution": True,
        "bounded_evaluation_execution": True,
        "external_call_count": 0,
        "production_code_mutation": False,
        "github_issue_mutation": False,
        "execution_authorized": False,
    }
    core["receipt_id"] = _stable_sha256(core)
    validate_execution_receipt(core, plan=plan, manifest=manifest)
    return core


def validate_execution_receipt(
    receipt: dict[str, Any],
    *,
    plan: dict[str, Any],
    manifest: dict[str, Any] | None = None,
) -> None:
    validate_experiment_plan(plan)
    if receipt.get("execution_receipt_version") != EXECUTION_RECEIPT_VERSION:
        raise ValueError("unsupported controlled experiment receipt version")
    if receipt.get("experiment_plan_id") != plan["plan_id"]:
        raise ValueError("controlled experiment receipt plan identity mismatch")
    if receipt.get("plan_definition_sha256") != _stable_sha256(plan):
        raise ValueError("controlled experiment receipt was produced from a modified plan")
    if receipt.get("target_domain") != plan["target_domain"] or receipt.get("accepted_generation") != plan["accepted_generation"]:
        raise ValueError("controlled experiment receipt target identity mismatch")
    if receipt.get("corpus_sha256") != plan["corpus_sha256"]:
        raise ValueError("controlled experiment receipt corpus identity mismatch")
    if not isinstance(receipt.get("performed_by"), str) or not receipt["performed_by"].strip():
        raise ValueError("controlled experiment receipt performer identity is required")
    if "outcome" in receipt or "direction" in receipt or "direct_evidence" in receipt:
        raise ValueError("controlled experiment runner cannot embed causal outcome semantics")
    for key, expected in {
        "observations_only": True,
        "contains_causal_outcome": False,
        "runner_outcome_authority": False,
        "lab85_qualification_authority": True,
        "definition_frozen_before_execution": True,
        "bounded_evaluation_execution": True,
        "external_call_count": 0,
        "production_code_mutation": False,
        "github_issue_mutation": False,
        "execution_authorized": False,
    }.items():
        if receipt.get(key) != expected:
            raise ValueError(f"controlled experiment receipt policy mismatch: {key}")
    replicates = receipt.get("replicates")
    if not isinstance(replicates, list) or len(replicates) != int(plan["minimum_replicate_count"]):
        raise ValueError("controlled experiment receipt replicate count mismatch")
    for index, row in enumerate(replicates, start=1):
        if row.get("replicate_receipt_version") != REPLICATE_RECEIPT_VERSION:
            raise ValueError("controlled experiment replicate receipt version mismatch")
        if row.get("experiment_plan_id") != plan["plan_id"] or row.get("replicate_index") != index:
            raise ValueError("controlled experiment replicate receipt identity mismatch")
        expected_row = {key: value for key, value in row.items() if key != "replicate_receipt_id"}
        if row.get("replicate_receipt_id") != _stable_sha256(expected_row):
            raise ValueError("controlled experiment replicate receipt digest mismatch")
    reproducibility = receipt.get("reproducibility")
    if not isinstance(reproducibility, dict) or reproducibility.get("reproducibility_version") != REPRODUCIBILITY_VERSION:
        raise ValueError("controlled experiment reproducibility evidence is invalid")
    if reproducibility.get("replicate_consistent") is not True or reproducibility.get("matched_ordered_corpus") is not True:
        raise ValueError("controlled experiment reproducibility evidence is insufficient")
    expected_repro = {key: value for key, value in reproducibility.items() if key != "reproducibility_id"}
    if reproducibility.get("reproducibility_id") != _stable_sha256(expected_repro):
        raise ValueError("controlled experiment reproducibility digest mismatch")
    if receipt.get("control_failure_count") != reproducibility["control"]["failure_count"]:
        raise ValueError("controlled experiment control count/reproducibility mismatch")
    if receipt.get("intervention_failure_count") != reproducibility["intervention"]["failure_count"]:
        raise ValueError("controlled experiment intervention count/reproducibility mismatch")
    if manifest is not None:
        validate_execution_manifest(manifest, plan=plan)
        if receipt.get("manifest_id") != manifest["manifest_id"]:
            raise ValueError("controlled experiment receipt manifest identity mismatch")
        if receipt.get("case_count") != manifest["case_count"]:
            raise ValueError("controlled experiment receipt case count mismatch")
        if receipt.get("control_environment_id") != manifest["control_environment"]["environment_id"]:
            raise ValueError("controlled experiment control environment receipt mismatch")
        if receipt.get("intervention_environment_id") != manifest["intervention_environment"]["environment_id"]:
            raise ValueError("controlled experiment intervention environment receipt mismatch")
    expected = {key: value for key, value in receipt.items() if key != "receipt_id"}
    if receipt.get("receipt_id") != _stable_sha256(expected):
        raise ValueError("controlled experiment receipt digest mismatch")


def receipt_to_lab85_result_input(
    plan: dict[str, Any],
    manifest: dict[str, Any],
    receipt: dict[str, Any],
) -> dict[str, Any]:
    validate_execution_receipt(receipt, plan=plan, manifest=manifest)
    control = manifest["control_environment"]["domain_digests"]
    intervention = manifest["intervention_environment"]["domain_digests"]
    non_target = {
        domain: {
            "control_sha256": control[domain],
            "intervention_sha256": intervention[domain],
        }
        for domain in plan["held_constant_domains"]
    }
    return {
        "experiment_plan_id": plan["plan_id"],
        "control_corpus_sha256": receipt["corpus_sha256"],
        "intervention_corpus_sha256": receipt["corpus_sha256"],
        "control_case_count": receipt["case_count"],
        "intervention_case_count": receipt["case_count"],
        "manipulated_domains": deepcopy(plan["manipulated_domains"]),
        "held_constant_domains": deepcopy(plan["held_constant_domains"]),
        "target_before_sha256": control[plan["target_domain"]],
        "target_after_sha256": intervention[plan["target_domain"]],
        "non_target_domain_digests": non_target,
        "control_runtime_status": "PASS",
        "intervention_runtime_status": "PASS",
        "replicate_count": receipt["reproducibility"]["replicate_count"],
        "replicate_consistent": True,
        "control_failure_count": receipt["control_failure_count"],
        "intervention_failure_count": receipt["intervention_failure_count"],
        "source_ref": f"controlled_execution_receipt:{receipt['receipt_id']}",
        "performed_by": receipt["performed_by"],
    }


def qualify_receipt_with_lab85(
    plan: dict[str, Any],
    manifest: dict[str, Any],
    receipt: dict[str, Any],
    *,
    verified_by: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    result_input = receipt_to_lab85_result_input(plan, manifest, receipt)
    return qualify_experiment_result(plan, result_input, verified_by=verified_by)


def submit_receipt_to_lab85(
    direct_evidence_ledger: dict[str, Any],
    plan: dict[str, Any],
    manifest: dict[str, Any],
    receipt: dict[str, Any],
    *,
    verified_by: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    validate_direct_evidence_ledger(direct_evidence_ledger)
    result_input = receipt_to_lab85_result_input(plan, manifest, receipt)
    return record_experiment_result(
        direct_evidence_ledger,
        plan_id=plan["plan_id"],
        result_input=result_input,
        verified_by=verified_by,
    )


def validate_execution_ledger(ledger: dict[str, Any]) -> None:
    if ledger.get("ledger_version") != EXECUTION_LEDGER_VERSION:
        raise ValueError("unsupported controlled experiment execution ledger version")
    required_policy = empty_execution_ledger()["policy"]
    policy = ledger.get("policy")
    if not isinstance(policy, dict):
        raise ValueError("controlled experiment execution ledger policy is required")
    for key, expected in required_policy.items():
        if policy.get(key) != expected:
            raise ValueError(f"controlled experiment execution ledger policy mismatch: {key}")
    executions = ledger.get("executions")
    if not isinstance(executions, list):
        raise ValueError("controlled experiment execution ledger executions must be a list")
    plans: set[str] = set()
    receipt_ids: set[str] = set()
    for sequence, entry in enumerate(executions, start=1):
        if entry.get("sequence") != sequence:
            raise ValueError("controlled experiment execution ledger sequence is invalid")
        plan = entry.get("plan")
        manifest = entry.get("manifest")
        receipt = entry.get("receipt")
        if not isinstance(plan, dict) or not isinstance(manifest, dict) or not isinstance(receipt, dict):
            raise ValueError("controlled experiment execution ledger entry is incomplete")
        validate_execution_receipt(receipt, plan=plan, manifest=manifest)
        plan_id = plan["plan_id"]
        if plan_id in plans:
            raise ValueError("one controlled experiment plan may have only one execution receipt")
        plans.add(plan_id)
        if receipt["receipt_id"] in receipt_ids:
            raise ValueError("duplicate controlled experiment execution receipt identity")
        receipt_ids.add(receipt["receipt_id"])
    if ledger.get("production_code_mutation", False) is not False or ledger.get("execution_authorized", False) is not False:
        raise ValueError("controlled experiment execution ledger exceeds authority boundary")


def record_execution_receipt(
    ledger: dict[str, Any],
    *,
    plan: dict[str, Any],
    manifest: dict[str, Any],
    receipt: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    validate_execution_ledger(ledger)
    validate_execution_receipt(receipt, plan=plan, manifest=manifest)
    existing = next((row for row in ledger["executions"] if row["plan"]["plan_id"] == plan["plan_id"]), None)
    if existing is not None:
        if existing["plan"] != plan or existing["manifest"] != manifest or existing["receipt"] != receipt:
            raise ValueError("conflicting controlled experiment rerun for frozen plan identity")
        return deepcopy(ledger), {"status": "UNCHANGED", "receipt_id": receipt["receipt_id"]}
    updated = deepcopy(ledger)
    updated["executions"].append(
        {
            "sequence": len(updated["executions"]) + 1,
            "plan": deepcopy(plan),
            "manifest": deepcopy(manifest),
            "receipt": deepcopy(receipt),
        }
    )
    validate_execution_ledger(updated)
    return updated, {"status": "RECORDED", "receipt_id": receipt["receipt_id"]}


def execution_summary(ledger: dict[str, Any]) -> dict[str, Any]:
    validate_execution_ledger(ledger)
    return {
        "ledger_version": EXECUTION_LEDGER_VERSION,
        "execution_count": len(ledger["executions"]),
        "experiment_definition_frozen": True,
        "runner_outcome_authority": False,
        "lab85_qualification_authority": True,
        "deterministic_reproducibility_required": True,
        "production_code_mutation": False,
        "execution_authorized": False,
    }


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JSON input must be an object")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="roberta-eval-human-root-cause-execute")
    sub = parser.add_subparsers(dest="command", required=True)

    manifest_cmd = sub.add_parser("manifest")
    manifest_cmd.add_argument("--plan", required=True)
    manifest_cmd.add_argument("--corpus", required=True)
    manifest_cmd.add_argument("--artifacts", required=True)
    manifest_cmd.add_argument("--output", default=None)

    validate_receipt_cmd = sub.add_parser("validate-receipt")
    validate_receipt_cmd.add_argument("--plan", required=True)
    validate_receipt_cmd.add_argument("--manifest", required=True)
    validate_receipt_cmd.add_argument("--receipt", required=True)

    to_lab85_cmd = sub.add_parser("to-lab85-input")
    to_lab85_cmd.add_argument("--plan", required=True)
    to_lab85_cmd.add_argument("--manifest", required=True)
    to_lab85_cmd.add_argument("--receipt", required=True)
    to_lab85_cmd.add_argument("--output", default=None)

    summary_cmd = sub.add_parser("summary")
    summary_cmd.add_argument("--ledger", default=None)
    args = parser.parse_args(argv)

    if args.command == "manifest":
        plan = _load_json(Path(args.plan))
        corpus_payload = _load_json(Path(args.corpus))
        artifacts = _load_json(Path(args.artifacts))
        cases = corpus_payload.get("cases")
        if not isinstance(cases, list):
            raise ValueError("corpus JSON must contain a cases list")
        payload = build_execution_manifest(
            plan,
            corpus_cases=cases,
            control_runtime_sha256=artifacts["control_runtime_sha256"],
            intervention_runtime_sha256=artifacts["intervention_runtime_sha256"],
            control_domain_digests=artifacts["control_domain_digests"],
            intervention_domain_digests=artifacts["intervention_domain_digests"],
        )
        if args.output:
            Path(args.output).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    if args.command == "validate-receipt":
        plan = _load_json(Path(args.plan))
        manifest = _load_json(Path(args.manifest))
        receipt = _load_json(Path(args.receipt))
        validate_execution_receipt(receipt, plan=plan, manifest=manifest)
        print(json.dumps({"status": "PASS", "receipt_id": receipt["receipt_id"]}, indent=2, sort_keys=True))
        return 0

    if args.command == "to-lab85-input":
        plan = _load_json(Path(args.plan))
        manifest = _load_json(Path(args.manifest))
        receipt = _load_json(Path(args.receipt))
        payload = receipt_to_lab85_result_input(plan, manifest, receipt)
        if args.output:
            Path(args.output).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    ledger_path = Path(args.ledger) if args.ledger else default_execution_ledger_path()
    ledger = load_execution_ledger(ledger_path)
    print(json.dumps(execution_summary(ledger), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
