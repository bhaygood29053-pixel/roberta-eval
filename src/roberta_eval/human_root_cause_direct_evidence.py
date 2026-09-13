from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from .human_remediation_root_cause import (
    DOMAINS,
    build_investigation_package,
    validate_investigation_package,
)
from .human_root_cause_evidence_acquisition import (
    EVIDENCE_BUNDLE_VERSION,
    validate_evidence_bundle,
)

EXPERIMENT_PLAN_VERSION = "roberta_human_root_cause_experiment_plan/v1"
EXPERIMENT_RESULT_VERSION = "roberta_human_root_cause_experiment_result/v1"
EXPERIMENT_QUALIFICATION_VERSION = "roberta_human_root_cause_experiment_qualification/v1"
DIRECT_EVIDENCE_LEDGER_VERSION = "roberta_human_root_cause_direct_evidence_ledger/v1"
DIRECT_EVIDENCE_BUNDLE_VERSION = "roberta_human_root_cause_direct_evidence_bundle/v1"
DIRECT_CONFIRMATION_VERSION = "roberta_human_root_cause_direct_confirmation/v1"

MINIMUM_MATCHED_CASE_COUNT = 20
MINIMUM_REPLICATE_COUNT = 2
QUALIFIED_DIRECTIONS = {"SUPPORTS", "CONTRADICTS"}
OUTCOMES = {
    "SUPPORTS_HYPOTHESIS",
    "FALSIFIES_HYPOTHESIS",
    "AMBIGUOUS_NO_DIRECT_EVIDENCE",
    "NON_REPRODUCING_CONTROL",
}


def _stable_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(ch in "0123456789abcdefABCDEF" for ch in value)


def default_direct_evidence_ledger_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "human_root_cause_direct_evidence_ledger.json"


def empty_direct_evidence_ledger() -> dict[str, Any]:
    return {
        "ledger_version": DIRECT_EVIDENCE_LEDGER_VERSION,
        "policy": {
            "pre_registration_required": True,
            "one_final_result_per_plan": True,
            "single_target_domain_required": True,
            "matched_corpus_required": True,
            "non_target_domains_held_constant_required": True,
            "falsification_required": True,
            "minimum_matched_case_count": MINIMUM_MATCHED_CASE_COUNT,
            "minimum_replicate_count": MINIMUM_REPLICATE_COUNT,
            "direct_evidence_requires_qualified_experiment": True,
            "single_generation_confirmation": False,
            "cross_generation_confirmation_required": True,
            "lab81_confirmation_authority": True,
            "automatic_issue_creation": False,
            "production_code_mutation": False,
            "execution_authorized": False,
        },
        "plans": [],
        "results": [],
    }


def load_direct_evidence_ledger(path: Path | None = None) -> dict[str, Any]:
    source = path or default_direct_evidence_ledger_path()
    payload = json.loads(source.read_text(encoding="utf-8"))
    validate_direct_evidence_ledger(payload)
    return payload


def write_direct_evidence_ledger(path: Path, ledger: dict[str, Any]) -> None:
    validate_direct_evidence_ledger(ledger)
    path.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _positive_suspects(bundle: dict[str, Any], *, top_n: int) -> list[dict[str, Any]]:
    validate_evidence_bundle(bundle)
    if not isinstance(top_n, int) or top_n <= 0:
        raise ValueError("direct-evidence suspect limit must be positive")
    suspects = []
    for finding in bundle["correlation"]["findings"]:
        generations = finding.get("implementation_generations") or []
        if int(finding.get("score", 0)) <= 0 or not generations:
            continue
        if finding.get("domain") not in DOMAINS:
            raise ValueError("LAB #83 correlation contains an invalid Human domain")
        suspects.append(finding)
    return suspects[:top_n]


def build_experiment_plan(
    bundle: dict[str, Any],
    *,
    target_domain: str,
    accepted_generation: int,
    corpus_sha256: str,
    minimum_case_count: int = MINIMUM_MATCHED_CASE_COUNT,
) -> dict[str, Any]:
    validate_evidence_bundle(bundle)
    if target_domain not in DOMAINS:
        raise ValueError("direct-evidence experiment target domain is invalid")
    if not _is_sha256(corpus_sha256):
        raise ValueError("direct-evidence experiment corpus SHA-256 is invalid")
    if not isinstance(minimum_case_count, int) or minimum_case_count < MINIMUM_MATCHED_CASE_COUNT:
        raise ValueError("direct-evidence experiment case count is below the accepted minimum")

    finding = next(
        (item for item in bundle["correlation"]["findings"] if item["domain"] == target_domain),
        None,
    )
    if finding is None or int(finding.get("score", 0)) <= 0:
        raise ValueError("direct-evidence experiment requires a positive LAB #83 correlated suspect")
    generations = [int(value) for value in finding.get("implementation_generations") or []]
    if accepted_generation not in generations:
        raise ValueError("direct-evidence experiment generation is not associated with the suspect domain")

    held_constant = [domain for domain in DOMAINS if domain != target_domain]
    core = {
        "experiment_plan_version": EXPERIMENT_PLAN_VERSION,
        "evidence_bundle_version": EVIDENCE_BUNDLE_VERSION,
        "evidence_bundle_sha256": bundle["bundle_sha256"],
        "family_root_fingerprint": bundle["family_root_fingerprint"],
        "failure_code": bundle["failure_code"],
        "service": bundle.get("service"),
        "target_domain": target_domain,
        "accepted_generation": accepted_generation,
        "correlation_signal": finding["signal"],
        "correlation_score": int(finding["score"]),
        "correlation_has_causal_authority": False,
        "corpus_sha256": corpus_sha256.lower(),
        "minimum_case_count": minimum_case_count,
        "minimum_replicate_count": MINIMUM_REPLICATE_COUNT,
        "primary_metric": "targeted_failure_count",
        "manipulated_domains": [target_domain],
        "held_constant_domains": held_constant,
        "control_condition": {
            "id": "ACCEPTED_BASELINE",
            "description": "Run the accepted generation runtime against the fixed corpus without the target-domain intervention.",
        },
        "intervention_condition": {
            "id": "ISOLATED_TARGET_DOMAIN_CORRECTION",
            "description": (
                "Run the same fixed corpus with an ephemeral candidate correction in the target domain only; "
                "all other Human domains must remain artifact-identical to control."
            ),
        },
        "pre_registered_outcome_rules": {
            "SUPPORTS_HYPOTHESIS": (
                "control reproduces the targeted failure and intervention reduces targeted failure count to zero"
            ),
            "FALSIFIES_HYPOTHESIS": (
                "control reproduces the targeted failure and intervention targeted failure count is unchanged or worse"
            ),
            "AMBIGUOUS_NO_DIRECT_EVIDENCE": (
                "intervention partially improves but does not eliminate the targeted failure"
            ),
            "NON_REPRODUCING_CONTROL": "control does not reproduce the targeted failure",
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
    core["plan_id"] = _stable_sha256(core)
    validate_experiment_plan(core, bundle=bundle)
    return core


def validate_experiment_plan(plan: dict[str, Any], *, bundle: dict[str, Any] | None = None) -> None:
    if plan.get("experiment_plan_version") != EXPERIMENT_PLAN_VERSION:
        raise ValueError("unsupported Human root-cause experiment plan version")
    if plan.get("target_domain") not in DOMAINS:
        raise ValueError("Human root-cause experiment target domain is invalid")
    if plan.get("manipulated_domains") != [plan.get("target_domain")]:
        raise ValueError("Human root-cause experiment must manipulate exactly one target domain")
    expected_held = [domain for domain in DOMAINS if domain != plan["target_domain"]]
    if plan.get("held_constant_domains") != expected_held:
        raise ValueError("Human root-cause experiment must hold all non-target domains constant")
    if not isinstance(plan.get("accepted_generation"), int) or plan["accepted_generation"] < 0:
        raise ValueError("Human root-cause experiment generation is invalid")
    if not _is_sha256(plan.get("corpus_sha256")):
        raise ValueError("Human root-cause experiment corpus digest is invalid")
    if int(plan.get("minimum_case_count", 0)) < MINIMUM_MATCHED_CASE_COUNT:
        raise ValueError("Human root-cause experiment is too small for DIRECT evidence")
    if int(plan.get("minimum_replicate_count", 0)) < MINIMUM_REPLICATE_COUNT:
        raise ValueError("Human root-cause experiment requires deterministic replication")
    for key in (
        "single_manipulated_factor",
        "matched_corpus_required",
        "non_target_domains_held_constant_required",
        "target_artifact_change_required",
        "deterministic_inputs_required",
        "falsification_condition_required",
        "pre_registered",
        "no_post_hoc_outcome_editing",
        "one_final_result_per_plan",
    ):
        if plan.get(key) is not True:
            raise ValueError(f"Human root-cause experiment plan is missing required isolation control: {key}")
    rules = plan.get("pre_registered_outcome_rules")
    if not isinstance(rules, dict) or set(rules) != OUTCOMES:
        raise ValueError("Human root-cause experiment must pre-register support, falsification, ambiguity and control-failure outcomes")
    if plan.get("single_generation_confirmation") is not False:
        raise ValueError("a single Human root-cause experiment generation cannot confirm causation")
    if plan.get("correlation_has_causal_authority") is not False:
        raise ValueError("LAB #83 correlation cannot acquire causal authority in an experiment plan")
    if plan.get("root_cause_confirmation_authority") != "LAB_81_ONLY":
        raise ValueError("LAB #81 must remain the root-cause confirmation authority")
    if plan.get("read_only_plan") is not True:
        raise ValueError("Human root-cause experiment plan must remain read-only")
    if plan.get("production_code_mutation") is not False or plan.get("execution_authorized") is not False:
        raise ValueError("Human root-cause experiment plan exceeds authority boundary")
    expected = {key: value for key, value in plan.items() if key != "plan_id"}
    if plan.get("plan_id") != _stable_sha256(expected):
        raise ValueError("Human root-cause experiment plan digest mismatch")

    if bundle is not None:
        validate_evidence_bundle(bundle)
        if plan.get("evidence_bundle_sha256") != bundle["bundle_sha256"]:
            raise ValueError("Human root-cause experiment plan evidence-bundle identity mismatch")
        if plan.get("family_root_fingerprint") != bundle["family_root_fingerprint"]:
            raise ValueError("Human root-cause experiment plan family identity mismatch")
        finding = next(
            (item for item in bundle["correlation"]["findings"] if item["domain"] == plan["target_domain"]),
            None,
        )
        if finding is None or int(finding.get("score", 0)) <= 0:
            raise ValueError("Human root-cause experiment target is not a positive LAB #83 suspect")
        if plan["accepted_generation"] not in [int(v) for v in finding.get("implementation_generations") or []]:
            raise ValueError("Human root-cause experiment generation is not supported by LAB #83 association evidence")


def generate_experiment_plans(
    bundle: dict[str, Any],
    *,
    corpus_sha256: str,
    top_n: int = 3,
    minimum_case_count: int = MINIMUM_MATCHED_CASE_COUNT,
) -> list[dict[str, Any]]:
    suspects = _positive_suspects(bundle, top_n=top_n)
    plans: list[dict[str, Any]] = []
    for finding in suspects:
        for generation in sorted({int(value) for value in finding.get("implementation_generations") or []}):
            plans.append(
                build_experiment_plan(
                    bundle,
                    target_domain=finding["domain"],
                    accepted_generation=generation,
                    corpus_sha256=corpus_sha256,
                    minimum_case_count=minimum_case_count,
                )
            )
    plan_ids = [plan["plan_id"] for plan in plans]
    if len(plan_ids) != len(set(plan_ids)):
        raise ValueError("duplicate Human root-cause experiment plan identity")
    return plans


def _rate(count: int, total: int) -> float:
    return count / total if total else 0.0


def qualify_experiment_result(
    plan: dict[str, Any],
    result_input: dict[str, Any],
    *,
    verified_by: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    validate_experiment_plan(plan)
    verified_by = verified_by.strip()
    if not verified_by:
        raise ValueError("Human root-cause experiment result verifier identity is required")
    if result_input.get("experiment_plan_id") != plan["plan_id"]:
        raise ValueError("Human root-cause experiment result plan identity mismatch")

    for key in ("control_corpus_sha256", "intervention_corpus_sha256"):
        if result_input.get(key) != plan["corpus_sha256"]:
            raise ValueError("Human root-cause experiment must use the exact pre-registered corpus in both arms")
    control_cases = result_input.get("control_case_count")
    intervention_cases = result_input.get("intervention_case_count")
    if not isinstance(control_cases, int) or not isinstance(intervention_cases, int):
        raise ValueError("Human root-cause experiment matched case counts are required")
    if control_cases != intervention_cases or control_cases < int(plan["minimum_case_count"]):
        raise ValueError("Human root-cause experiment requires matched case counts at or above the pre-registered minimum")

    manipulated = result_input.get("manipulated_domains")
    if manipulated != [plan["target_domain"]]:
        raise ValueError("Human root-cause experiment result is non-isolating: multiple or wrong domains changed")
    held = result_input.get("held_constant_domains")
    if held != plan["held_constant_domains"]:
        raise ValueError("Human root-cause experiment result did not hold all non-target domains constant")

    target_before = result_input.get("target_before_sha256")
    target_after = result_input.get("target_after_sha256")
    if not _is_sha256(target_before) or not _is_sha256(target_after) or target_before == target_after:
        raise ValueError("Human root-cause experiment must prove the target artifact changed")
    non_target = result_input.get("non_target_domain_digests")
    if not isinstance(non_target, dict) or set(non_target) != set(plan["held_constant_domains"]):
        raise ValueError("Human root-cause experiment requires artifact proof for every held-constant domain")
    normalized_non_target: dict[str, dict[str, str]] = {}
    for domain in plan["held_constant_domains"]:
        proof = non_target.get(domain)
        if not isinstance(proof, dict):
            raise ValueError("Human root-cause held-constant domain proof is invalid")
        control_sha = proof.get("control_sha256")
        intervention_sha = proof.get("intervention_sha256")
        if not _is_sha256(control_sha) or not _is_sha256(intervention_sha) or control_sha != intervention_sha:
            raise ValueError("Human root-cause experiment changed a non-target domain")
        normalized_non_target[domain] = {
            "control_sha256": control_sha.lower(),
            "intervention_sha256": intervention_sha.lower(),
        }

    if result_input.get("control_runtime_status") != "PASS" or result_input.get("intervention_runtime_status") != "PASS":
        raise ValueError("Human root-cause experiment requires valid control and intervention runtimes")
    replicate_count = result_input.get("replicate_count")
    if not isinstance(replicate_count, int) or replicate_count < int(plan["minimum_replicate_count"]):
        raise ValueError("Human root-cause experiment lacks required deterministic replication")
    if result_input.get("replicate_consistent") is not True:
        raise ValueError("Human root-cause experiment replicates are inconsistent")

    control_failure_count = result_input.get("control_failure_count")
    intervention_failure_count = result_input.get("intervention_failure_count")
    if not isinstance(control_failure_count, int) or not isinstance(intervention_failure_count, int):
        raise ValueError("Human root-cause experiment failure counts are required")
    if not (0 <= control_failure_count <= control_cases) or not (0 <= intervention_failure_count <= intervention_cases):
        raise ValueError("Human root-cause experiment failure counts are outside matched case bounds")

    source_ref = result_input.get("source_ref")
    performed_by = result_input.get("performed_by")
    if not isinstance(source_ref, str) or not source_ref.strip():
        raise ValueError("Human root-cause experiment result source reference is required")
    if not isinstance(performed_by, str) or not performed_by.strip():
        raise ValueError("Human root-cause experiment performer identity is required")

    if control_failure_count == 0:
        outcome = "NON_REPRODUCING_CONTROL"
        direction = None
    elif intervention_failure_count == 0:
        outcome = "SUPPORTS_HYPOTHESIS"
        direction = "SUPPORTS"
    elif intervention_failure_count >= control_failure_count:
        outcome = "FALSIFIES_HYPOTHESIS"
        direction = "CONTRADICTS"
    else:
        outcome = "AMBIGUOUS_NO_DIRECT_EVIDENCE"
        direction = None

    result_core = {
        "experiment_result_version": EXPERIMENT_RESULT_VERSION,
        "experiment_plan_id": plan["plan_id"],
        "evidence_bundle_sha256": plan["evidence_bundle_sha256"],
        "family_root_fingerprint": plan["family_root_fingerprint"],
        "target_domain": plan["target_domain"],
        "accepted_generation": plan["accepted_generation"],
        "corpus_sha256": plan["corpus_sha256"],
        "control_case_count": control_cases,
        "intervention_case_count": intervention_cases,
        "control_failure_count": control_failure_count,
        "intervention_failure_count": intervention_failure_count,
        "control_failure_rate": _rate(control_failure_count, control_cases),
        "intervention_failure_rate": _rate(intervention_failure_count, intervention_cases),
        "manipulated_domains": manipulated,
        "held_constant_domains": held,
        "target_before_sha256": target_before.lower(),
        "target_after_sha256": target_after.lower(),
        "non_target_domain_digests": normalized_non_target,
        "control_runtime_status": "PASS",
        "intervention_runtime_status": "PASS",
        "replicate_count": replicate_count,
        "replicate_consistent": True,
        "source_ref": source_ref.strip(),
        "performed_by": performed_by.strip(),
        "verified_by": verified_by,
        "outcome": outcome,
        "pre_registered_rules_applied": True,
        "post_hoc_outcome_editing": False,
        "production_code_mutation": False,
        "execution_authorized": False,
    }
    result_core["result_id"] = _stable_sha256(result_core)

    qualification_core = {
        "experiment_qualification_version": EXPERIMENT_QUALIFICATION_VERSION,
        "experiment_plan_id": plan["plan_id"],
        "experiment_result_id": result_core["result_id"],
        "target_domain": plan["target_domain"],
        "accepted_generation": plan["accepted_generation"],
        "outcome": outcome,
        "admissible_direct_evidence": direction in QUALIFIED_DIRECTIONS,
        "direct_evidence_direction": direction,
        "direct_evidence_strength": "DIRECT" if direction in QUALIFIED_DIRECTIONS else None,
        "falsification_retained": outcome == "FALSIFIES_HYPOTHESIS",
        "single_generation_confirmation": False,
        "root_cause_confirmation_authority": "LAB_81_ONLY",
        "production_code_mutation": False,
        "execution_authorized": False,
    }
    qualification_core["qualification_id"] = _stable_sha256(qualification_core)
    validate_experiment_result(result_core, plan=plan)
    validate_experiment_qualification(qualification_core, result=result_core)
    return result_core, qualification_core


def validate_experiment_result(result: dict[str, Any], *, plan: dict[str, Any] | None = None) -> None:
    if result.get("experiment_result_version") != EXPERIMENT_RESULT_VERSION:
        raise ValueError("unsupported Human root-cause experiment result version")
    for key in ("experiment_plan_id", "result_id", "evidence_bundle_sha256", "family_root_fingerprint", "corpus_sha256"):
        if not _is_sha256(result.get(key)):
            raise ValueError(f"Human root-cause experiment result {key} is invalid")
    if result.get("target_domain") not in DOMAINS:
        raise ValueError("Human root-cause experiment result domain is invalid")
    if result.get("outcome") not in OUTCOMES:
        raise ValueError("Human root-cause experiment result outcome is invalid")
    if result.get("pre_registered_rules_applied") is not True or result.get("post_hoc_outcome_editing") is not False:
        raise ValueError("Human root-cause experiment result must use pre-registered outcome rules")
    if result.get("production_code_mutation") is not False or result.get("execution_authorized") is not False:
        raise ValueError("Human root-cause experiment result exceeds authority boundary")
    expected = {key: value for key, value in result.items() if key != "result_id"}
    if result["result_id"] != _stable_sha256(expected):
        raise ValueError("Human root-cause experiment result digest mismatch")
    if plan is not None:
        validate_experiment_plan(plan)
        if result["experiment_plan_id"] != plan["plan_id"]:
            raise ValueError("Human root-cause experiment result does not match plan")
        if result["target_domain"] != plan["target_domain"] or result["accepted_generation"] != plan["accepted_generation"]:
            raise ValueError("Human root-cause experiment result target identity mismatch")


def validate_experiment_qualification(qualification: dict[str, Any], *, result: dict[str, Any] | None = None) -> None:
    if qualification.get("experiment_qualification_version") != EXPERIMENT_QUALIFICATION_VERSION:
        raise ValueError("unsupported Human root-cause experiment qualification version")
    for key in ("experiment_plan_id", "experiment_result_id", "qualification_id"):
        if not _is_sha256(qualification.get(key)):
            raise ValueError(f"Human root-cause experiment qualification {key} is invalid")
    if qualification.get("outcome") not in OUTCOMES:
        raise ValueError("Human root-cause experiment qualification outcome is invalid")
    admissible = qualification.get("admissible_direct_evidence") is True
    direction = qualification.get("direct_evidence_direction")
    if admissible:
        if direction not in QUALIFIED_DIRECTIONS or qualification.get("direct_evidence_strength") != "DIRECT":
            raise ValueError("admissible Human root-cause experiment lacks DIRECT evidence semantics")
    else:
        if direction is not None or qualification.get("direct_evidence_strength") is not None:
            raise ValueError("non-admissible Human root-cause experiment cannot emit DIRECT evidence")
    if qualification.get("outcome") == "FALSIFIES_HYPOTHESIS" and qualification.get("falsification_retained") is not True:
        raise ValueError("Human root-cause falsifying evidence must be retained")
    if qualification.get("single_generation_confirmation") is not False:
        raise ValueError("Human root-cause experiment cannot confirm causation in one generation")
    if qualification.get("root_cause_confirmation_authority") != "LAB_81_ONLY":
        raise ValueError("LAB #81 must remain the Human root-cause confirmation authority")
    if qualification.get("production_code_mutation") is not False or qualification.get("execution_authorized") is not False:
        raise ValueError("Human root-cause experiment qualification exceeds authority boundary")
    expected = {key: value for key, value in qualification.items() if key != "qualification_id"}
    if qualification["qualification_id"] != _stable_sha256(expected):
        raise ValueError("Human root-cause experiment qualification digest mismatch")
    if result is not None:
        validate_experiment_result(result)
        if qualification["experiment_result_id"] != result["result_id"] or qualification["outcome"] != result["outcome"]:
            raise ValueError("Human root-cause qualification/result identity mismatch")


def _direct_evidence_item(plan: dict[str, Any], result: dict[str, Any], qualification: dict[str, Any]) -> dict[str, Any] | None:
    validate_experiment_plan(plan)
    validate_experiment_result(result, plan=plan)
    validate_experiment_qualification(qualification, result=result)
    if qualification["admissible_direct_evidence"] is not True:
        return None
    direction = qualification["direct_evidence_direction"]
    statement = (
        f"Qualified pre-registered isolation experiment {result['result_id']} at generation "
        f"{plan['accepted_generation']} manipulated only {plan['target_domain']}; matched control reproduced "
        f"{result['control_failure_count']} targeted failures and intervention produced "
        f"{result['intervention_failure_count']}. Outcome={result['outcome']}."
    )
    return {
        "domain": plan["target_domain"],
        "generation": plan["accepted_generation"],
        "direction": direction,
        "strength": "DIRECT",
        "source_ref": f"qualified_experiment:{result['result_id']}",
        "artifact_sha256": result["result_id"],
        "statement": statement,
    }


def validate_direct_evidence_ledger(ledger: dict[str, Any]) -> None:
    if ledger.get("ledger_version") != DIRECT_EVIDENCE_LEDGER_VERSION:
        raise ValueError("unsupported Human root-cause direct-evidence ledger version")
    required_policy = empty_direct_evidence_ledger()["policy"]
    policy = ledger.get("policy")
    if not isinstance(policy, dict):
        raise ValueError("Human root-cause direct-evidence ledger policy is required")
    for key, expected in required_policy.items():
        if policy.get(key) != expected:
            raise ValueError(f"Human root-cause direct-evidence ledger policy mismatch: {key}")
    plans = ledger.get("plans")
    results = ledger.get("results")
    if not isinstance(plans, list) or not isinstance(results, list):
        raise ValueError("Human root-cause direct-evidence ledger plans/results must be lists")
    plan_ids: set[str] = set()
    for sequence, entry in enumerate(plans, start=1):
        if entry.get("sequence") != sequence or not isinstance(entry.get("plan"), dict):
            raise ValueError("Human root-cause direct-evidence plan sequence is invalid")
        validate_experiment_plan(entry["plan"])
        plan_id = entry["plan"]["plan_id"]
        if plan_id in plan_ids:
            raise ValueError("duplicate Human root-cause experiment plan identity")
        plan_ids.add(plan_id)
    result_plan_ids: set[str] = set()
    result_ids: set[str] = set()
    plan_index = {entry["plan"]["plan_id"]: entry["plan"] for entry in plans}
    for sequence, entry in enumerate(results, start=1):
        if entry.get("sequence") != sequence:
            raise ValueError("Human root-cause direct-evidence result sequence is invalid")
        plan_id = entry.get("experiment_plan_id")
        plan = plan_index.get(plan_id)
        if plan is None:
            raise ValueError("Human root-cause experiment result references an unregistered plan")
        if plan_id in result_plan_ids:
            raise ValueError("one Human root-cause experiment plan may have only one final result")
        result_plan_ids.add(plan_id)
        result = entry.get("result")
        qualification = entry.get("qualification")
        if not isinstance(result, dict) or not isinstance(qualification, dict):
            raise ValueError("Human root-cause experiment ledger result/qualification is required")
        validate_experiment_result(result, plan=plan)
        validate_experiment_qualification(qualification, result=result)
        if result["result_id"] in result_ids:
            raise ValueError("duplicate Human root-cause experiment result identity")
        result_ids.add(result["result_id"])
        if entry.get("verified_by") != result.get("verified_by"):
            raise ValueError("Human root-cause experiment ledger verifier mismatch")
    if ledger.get("production_code_mutation", False) is not False or ledger.get("execution_authorized", False) is not False:
        raise ValueError("Human root-cause direct-evidence ledger exceeds authority boundary")


def register_experiment_plans(
    ledger: dict[str, Any], plans: list[dict[str, Any]]
) -> tuple[dict[str, Any], dict[str, int]]:
    validate_direct_evidence_ledger(ledger)
    updated = deepcopy(ledger)
    existing = {entry["plan"]["plan_id"]: entry["plan"] for entry in updated["plans"]}
    appended = 0
    unchanged = 0
    for plan in plans:
        validate_experiment_plan(plan)
        found = existing.get(plan["plan_id"])
        if found is not None:
            if found != plan:
                raise ValueError("conflicting Human root-cause experiment plan identity")
            unchanged += 1
            continue
        updated["plans"].append({"sequence": len(updated["plans"]) + 1, "plan": deepcopy(plan)})
        existing[plan["plan_id"]] = plan
        appended += 1
    validate_direct_evidence_ledger(updated)
    return updated, {"appended": appended, "unchanged": unchanged}


def record_experiment_result(
    ledger: dict[str, Any],
    *,
    plan_id: str,
    result_input: dict[str, Any],
    verified_by: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    validate_direct_evidence_ledger(ledger)
    plan_entry = next((entry for entry in ledger["plans"] if entry["plan"]["plan_id"] == plan_id), None)
    if plan_entry is None:
        raise ValueError("Human root-cause experiment plan is not registered")
    plan = plan_entry["plan"]
    result, qualification = qualify_experiment_result(plan, result_input, verified_by=verified_by)
    existing = next((entry for entry in ledger["results"] if entry["experiment_plan_id"] == plan_id), None)
    if existing is not None:
        if existing["result"] != result or existing["qualification"] != qualification:
            raise ValueError("conflicting final result for pre-registered Human root-cause experiment plan")
        return deepcopy(ledger), {
            "status": "UNCHANGED",
            "result": deepcopy(result),
            "qualification": deepcopy(qualification),
        }
    updated = deepcopy(ledger)
    updated["results"].append(
        {
            "sequence": len(updated["results"]) + 1,
            "experiment_plan_id": plan_id,
            "verified_by": result["verified_by"],
            "result": result,
            "qualification": qualification,
        }
    )
    validate_direct_evidence_ledger(updated)
    return updated, {
        "status": "RECORDED",
        "result": deepcopy(result),
        "qualification": deepcopy(qualification),
    }


def _confirmation_findings(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for domain in DOMAINS:
        items = [item for item in evidence if item["domain"] == domain]
        supports = [item for item in items if item["direction"] == "SUPPORTS"]
        contradicts = [item for item in items if item["direction"] == "CONTRADICTS"]
        support_generations = sorted({int(item["generation"]) for item in supports})
        contradiction_generations = sorted({int(item["generation"]) for item in contradicts})
        if contradicts:
            state = "FALSIFIED_OR_CONTRADICTED"
        elif len(support_generations) >= 2:
            state = "INDEPENDENT_CROSS_GENERATION_SUPPORT"
        elif len(support_generations) == 1:
            state = "SINGLE_GENERATION_SUPPORT_ONLY"
        else:
            state = "NO_DIRECT_EVIDENCE"
        findings.append(
            {
                "domain": domain,
                "state": state,
                "direct_support_count": len(supports),
                "direct_support_generations": support_generations,
                "direct_contradiction_count": len(contradicts),
                "direct_contradiction_generations": contradiction_generations,
                "independent_cross_generation_support": len(support_generations) >= 2,
                "zero_contradictions": len(contradicts) == 0,
                "lab81_confirmation_candidate": len(support_generations) >= 2 and not contradicts,
                "evidence_source_refs": [item["source_ref"] for item in items],
                "causal_authority": False,
            }
        )
    return findings


def build_direct_evidence_bundle(
    acquisition_bundle: dict[str, Any],
    ledger: dict[str, Any],
) -> dict[str, Any]:
    validate_evidence_bundle(acquisition_bundle)
    validate_direct_evidence_ledger(ledger)
    plan_index = {
        entry["plan"]["plan_id"]: entry["plan"]
        for entry in ledger["plans"]
        if entry["plan"]["evidence_bundle_sha256"] == acquisition_bundle["bundle_sha256"]
    }
    evidence: list[dict[str, Any]] = []
    qualification_ids: list[str] = []
    ambiguous_count = 0
    non_reproducing_control_count = 0
    for entry in ledger["results"]:
        plan = plan_index.get(entry["experiment_plan_id"])
        if plan is None:
            continue
        qualification = entry["qualification"]
        result = entry["result"]
        qualification_ids.append(qualification["qualification_id"])
        item = _direct_evidence_item(plan, result, qualification)
        if item is not None:
            evidence.append(item)
        elif qualification["outcome"] == "AMBIGUOUS_NO_DIRECT_EVIDENCE":
            ambiguous_count += 1
        elif qualification["outcome"] == "NON_REPRODUCING_CONTROL":
            non_reproducing_control_count += 1
    evidence.sort(key=lambda item: (item["generation"], item["domain"], item["source_ref"]))
    source_refs = [item["source_ref"] for item in evidence]
    if len(source_refs) != len(set(source_refs)):
        raise ValueError("duplicate qualified Human root-cause DIRECT evidence identity")
    findings = _confirmation_findings(evidence)
    candidates = [item["domain"] for item in findings if item["lab81_confirmation_candidate"]]
    core = {
        "direct_evidence_bundle_version": DIRECT_EVIDENCE_BUNDLE_VERSION,
        "direct_confirmation_version": DIRECT_CONFIRMATION_VERSION,
        "acquisition_bundle_sha256": acquisition_bundle["bundle_sha256"],
        "family_root_fingerprint": acquisition_bundle["family_root_fingerprint"],
        "failure_code": acquisition_bundle["failure_code"],
        "service": acquisition_bundle.get("service"),
        "qualified_direct_evidence": evidence,
        "qualification_ids": sorted(qualification_ids),
        "confirmation_findings": findings,
        "lab81_confirmation_candidate_domains": candidates,
        "ambiguous_result_count": ambiguous_count,
        "non_reproducing_control_count": non_reproducing_control_count,
        "direct_evidence_requires_qualified_experiment": True,
        "falsification_retained": True,
        "single_generation_confirmation": False,
        "cross_generation_confirmation_required": True,
        "lab81_confirmation_threshold_preserved": True,
        "causal_authority": False,
        "root_cause_confirmation_authority": "LAB_81_ONLY",
        "production_code_mutation": False,
        "execution_authorized": False,
    }
    core["direct_bundle_sha256"] = _stable_sha256(core)
    validate_direct_evidence_bundle(core)
    return core


def validate_direct_evidence_bundle(bundle: dict[str, Any]) -> None:
    if bundle.get("direct_evidence_bundle_version") != DIRECT_EVIDENCE_BUNDLE_VERSION:
        raise ValueError("unsupported Human root-cause DIRECT evidence bundle version")
    if bundle.get("direct_confirmation_version") != DIRECT_CONFIRMATION_VERSION:
        raise ValueError("unsupported Human root-cause direct confirmation version")
    for key in ("acquisition_bundle_sha256", "family_root_fingerprint", "direct_bundle_sha256"):
        if not _is_sha256(bundle.get(key)):
            raise ValueError(f"Human root-cause DIRECT evidence bundle {key} is invalid")
    evidence = bundle.get("qualified_direct_evidence")
    if not isinstance(evidence, list):
        raise ValueError("Human root-cause qualified DIRECT evidence must be a list")
    for item in evidence:
        if item.get("strength") != "DIRECT" or item.get("direction") not in QUALIFIED_DIRECTIONS:
            raise ValueError("Human root-cause DIRECT evidence bundle contains inadmissible evidence")
        if item.get("domain") not in DOMAINS or not _is_sha256(item.get("artifact_sha256")):
            raise ValueError("Human root-cause DIRECT evidence identity is invalid")
        if not str(item.get("source_ref", "")).startswith("qualified_experiment:"):
            raise ValueError("Human root-cause DIRECT evidence must originate from a qualified experiment")
    findings = bundle.get("confirmation_findings")
    if not isinstance(findings, list) or {item.get("domain") for item in findings} != set(DOMAINS):
        raise ValueError("Human root-cause direct confirmation findings must cover all domains")
    candidates = [item["domain"] for item in findings if item.get("lab81_confirmation_candidate") is True]
    if bundle.get("lab81_confirmation_candidate_domains") != candidates:
        raise ValueError("Human root-cause LAB #81 candidate summary mismatch")
    for finding in findings:
        if finding.get("lab81_confirmation_candidate") is True:
            if len(finding.get("direct_support_generations") or []) < 2 or finding.get("direct_contradiction_count") != 0:
                raise ValueError("Human root-cause confirmation candidate lacks independent cross-generation support")
    if bundle.get("single_generation_confirmation") is not False or bundle.get("cross_generation_confirmation_required") is not True:
        raise ValueError("Human root-cause confirmation generation policy mismatch")
    if bundle.get("lab81_confirmation_threshold_preserved") is not True:
        raise ValueError("LAB #81 confirmation threshold must remain preserved")
    if bundle.get("causal_authority") is not False or bundle.get("root_cause_confirmation_authority") != "LAB_81_ONLY":
        raise ValueError("Human root-cause DIRECT evidence bundle cannot name a root cause")
    if bundle.get("production_code_mutation") is not False or bundle.get("execution_authorized") is not False:
        raise ValueError("Human root-cause DIRECT evidence bundle exceeds authority boundary")
    expected = {key: value for key, value in bundle.items() if key != "direct_bundle_sha256"}
    if bundle["direct_bundle_sha256"] != _stable_sha256(expected):
        raise ValueError("Human root-cause DIRECT evidence bundle digest mismatch")


def build_lab81_package_with_direct_evidence(
    lineage_report: dict[str, Any],
    acquisition_bundle: dict[str, Any],
    direct_bundle: dict[str, Any],
) -> dict[str, Any]:
    validate_evidence_bundle(acquisition_bundle)
    validate_direct_evidence_bundle(direct_bundle)
    if direct_bundle["acquisition_bundle_sha256"] != acquisition_bundle["bundle_sha256"]:
        raise ValueError("Human root-cause direct/acquisition bundle identity mismatch")
    if direct_bundle["family_root_fingerprint"] != acquisition_bundle["family_root_fingerprint"]:
        raise ValueError("Human root-cause direct/acquisition family identity mismatch")
    evidence = list(acquisition_bundle["lab81_evidence"]) + list(direct_bundle["qualified_direct_evidence"])
    package = build_investigation_package(
        lineage_report,
        root_fingerprint=acquisition_bundle["family_root_fingerprint"],
        evidence=evidence,
    )
    validate_investigation_package(package)
    candidates = set(direct_bundle["lab81_confirmation_candidate_domains"])
    if any(domain not in candidates for domain in package["confirmed_root_causes"]):
        raise ValueError("LAB #81 confirmed a root cause without qualified independent experiment evidence")
    return package


def direct_evidence_summary(bundle: dict[str, Any]) -> dict[str, Any]:
    validate_direct_evidence_bundle(bundle)
    return {
        "direct_evidence_bundle_version": DIRECT_EVIDENCE_BUNDLE_VERSION,
        "family_root_fingerprint": bundle["family_root_fingerprint"],
        "qualified_direct_evidence_count": len(bundle["qualified_direct_evidence"]),
        "lab81_confirmation_candidate_domains": bundle["lab81_confirmation_candidate_domains"],
        "ambiguous_result_count": bundle["ambiguous_result_count"],
        "non_reproducing_control_count": bundle["non_reproducing_control_count"],
        "single_generation_confirmation": False,
        "cross_generation_confirmation_required": True,
        "causal_authority": False,
    }


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JSON input must be an object")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="roberta-eval-human-root-cause-direct")
    sub = parser.add_subparsers(dest="command", required=True)

    plans = sub.add_parser("plans")
    plans.add_argument("--acquisition-bundle", required=True)
    plans.add_argument("--corpus-sha256", required=True)
    plans.add_argument("--top-n", type=int, default=3)
    plans.add_argument("--output", default=None)

    register = sub.add_parser("register-plans")
    register.add_argument("--plans", required=True)
    register.add_argument("--ledger", default=None)

    record = sub.add_parser("record-result")
    record.add_argument("--plan-id", required=True)
    record.add_argument("--result", required=True)
    record.add_argument("--verified-by", required=True)
    record.add_argument("--ledger", default=None)

    bundle_parser = sub.add_parser("bundle")
    bundle_parser.add_argument("--acquisition-bundle", required=True)
    bundle_parser.add_argument("--ledger", default=None)
    bundle_parser.add_argument("--output", default=None)

    package_parser = sub.add_parser("lab81-package")
    package_parser.add_argument("--lineage-report", required=True)
    package_parser.add_argument("--acquisition-bundle", required=True)
    package_parser.add_argument("--ledger", default=None)
    package_parser.add_argument("--output", default=None)

    sub.add_parser("summary").add_argument("--ledger", default=None)
    args = parser.parse_args(argv)

    if args.command == "plans":
        acquisition = _load_json(Path(args.acquisition_bundle))
        generated = generate_experiment_plans(
            acquisition,
            corpus_sha256=args.corpus_sha256,
            top_n=args.top_n,
        )
        payload: Any = {"plans": generated}
        if args.output:
            Path(args.output).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    ledger_path = Path(args.ledger) if getattr(args, "ledger", None) else default_direct_evidence_ledger_path()
    ledger = load_direct_evidence_ledger(ledger_path)

    if args.command == "register-plans":
        payload = _load_json(Path(args.plans))
        plan_rows = payload.get("plans")
        if not isinstance(plan_rows, list):
            raise ValueError("plans JSON must contain a plans list")
        updated, result = register_experiment_plans(ledger, plan_rows)
        write_direct_evidence_ledger(ledger_path, updated)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    if args.command == "record-result":
        result_input = _load_json(Path(args.result))
        updated, result = record_experiment_result(
            ledger,
            plan_id=args.plan_id,
            result_input=result_input,
            verified_by=args.verified_by,
        )
        write_direct_evidence_ledger(ledger_path, updated)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    if args.command == "summary":
        print(
            json.dumps(
                {
                    "ledger_version": ledger["ledger_version"],
                    "plan_count": len(ledger["plans"]),
                    "result_count": len(ledger["results"]),
                    "pre_registration_required": True,
                    "one_final_result_per_plan": True,
                    "single_generation_confirmation": False,
                    "production_code_mutation": False,
                    "execution_authorized": False,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    acquisition = _load_json(Path(args.acquisition_bundle))
    direct = build_direct_evidence_bundle(acquisition, ledger)
    if args.command == "bundle":
        payload = direct
    else:
        lineage = _load_json(Path(args.lineage_report))
        payload = build_lab81_package_with_direct_evidence(lineage, acquisition, direct)
    if args.output:
        Path(args.output).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
