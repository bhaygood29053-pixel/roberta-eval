from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from roberta_eval.human_remediation_root_cause import DOMAINS
from roberta_eval.human_root_cause_artifact_sandbox import (
    lab87_corpus_cases,
    load_source_pin,
    materialize_control_artifact,
)
from roberta_eval.human_root_cause_direct_evidence import (
    EXPERIMENT_PLAN_VERSION,
    OUTCOMES,
    validate_experiment_plan,
)
from roberta_eval.human_root_cause_experiment_execution import corpus_sha256
from roberta_eval.human_root_cause_patch_qualification import (
    PATCH_LEDGER_VERSION,
    TARGET_REPOSITORY,
    construct_candidate_patch,
    empty_patch_ledger,
    ledger_summary,
    qualify_candidate_patch,
    qualify_patch_static_safety,
    record_patch_qualification,
    validate_candidate_patch,
    validate_patch_ledger,
)


def _sha(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _renderer_control() -> str:
    return (
        "def render_human_response(response_decision, *, response_depth=None):\n"
        "    return 'deterministic risk engine: ' + str(response_decision.get('message', ''))\n"
    )


def _renderer_supporting() -> str:
    return (
        "def render_human_response(response_decision, *, response_depth=None):\n"
        "    return 'risk checks: ' + str(response_decision.get('message', ''))\n"
    )


def _renderer_non_supporting() -> str:
    return (
        "# candidate changed but behavior did not\n"
        "def render_human_response(response_decision, *, response_depth=None):\n"
        "    return 'deterministic risk engine: ' + str(response_decision.get('message', ''))\n"
    )


class FakeSource:
    def __init__(self, pin: dict) -> None:
        self.pin = pin
        self.calls: list[tuple[str, str, str]] = []
        self.files = {
            "src/roberta/human_response_contract.py": b"CONTRACT_VERSION = 'fake/v1'\n",
            "src/roberta/human_response_renderer.py": _renderer_control().encode("utf-8"),
            "src/roberta/bridge_http.py": b"def sandbox_marker(): return 'bridge-public-shell'\n",
            ".github/styles/RobertaHuman/TechnicalVocabulary.yml": b"extends: existence\n",
        }

    def get_file(self, *, repository: str, commit_sha: str, path: str) -> bytes:
        self.calls.append((repository, commit_sha, path))
        return self.files[path]


def _cases() -> list[dict]:
    return [
        {
            "case_id": f"case-{index:02d}",
            "response_decision": {"message": f"sample {index}"},
            "response_depth": "normal",
            "failure_predicate": {
                "kind": "contains_any",
                "terms": ["deterministic risk engine"],
            },
        }
        for index in range(20)
    ]


def _plan(corpus_digest: str) -> dict:
    held = [domain for domain in DOMAINS if domain != "renderer"]
    core = {
        "experiment_plan_version": EXPERIMENT_PLAN_VERSION,
        "evidence_bundle_version": "roberta_human_root_cause_evidence_bundle/v1",
        "evidence_bundle_sha256": "1" * 64,
        "family_root_fingerprint": "a" * 64,
        "failure_code": "technical_language_leak",
        "service": "pre_trade",
        "target_domain": "renderer",
        "accepted_generation": 2,
        "correlation_signal": "REPEATED_CROSS_GENERATION_ASSOCIATION",
        "correlation_score": 12,
        "correlation_has_causal_authority": False,
        "corpus_sha256": corpus_digest,
        "minimum_case_count": 20,
        "minimum_replicate_count": 2,
        "primary_metric": "targeted_failure_count",
        "manipulated_domains": ["renderer"],
        "held_constant_domains": held,
        "control_condition": {
            "id": "ACCEPTED_BASELINE",
            "description": "accepted public Human renderer",
        },
        "intervention_condition": {
            "id": "ISOLATED_TARGET_DOMAIN_CORRECTION",
            "description": "ephemeral renderer-only correction",
        },
        "pre_registered_outcome_rules": {
            "SUPPORTS_HYPOTHESIS": "control reproduces and intervention eliminates",
            "FALSIFIES_HYPOTHESIS": "control reproduces and intervention is unchanged or worse",
            "AMBIGUOUS_NO_DIRECT_EVIDENCE": "partial improvement only",
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
    assert set(core["pre_registered_outcome_rules"]) == OUTCOMES
    core["plan_id"] = _sha(core)
    validate_experiment_plan(core)
    return core


def _setup(tmp_path: Path, *, replacement: str = ""):
    pin = load_source_pin()
    source = FakeSource(pin)
    control_root = tmp_path / "control"
    control = materialize_control_artifact(pin, source, root=control_root)
    cases = _cases()
    plan = _plan(corpus_sha256(lab87_corpus_cases(cases)))
    patch = construct_candidate_patch(
        pin,
        plan,
        control,
        control_root=control_root,
        replacements={
            "src/roberta/human_response_renderer.py": replacement or _renderer_supporting()
        },
        constructed_by="LAB-91",
        rationale="Remove the repeated technical phrase from the Human renderer.",
    )
    return pin, source, control_root, control, cases, plan, patch


def test_source_pin_and_patch_are_bound_to_real_accepted_roberta_control(tmp_path: Path) -> None:
    pin, source, control_root, control, _, plan, patch = _setup(tmp_path)
    assert pin["repository"] == TARGET_REPOSITORY
    assert pin["commit_sha"] == "becb264b8026b5cbbf99f0d12dea62463510c6ee"
    assert patch["target_repository"] == TARGET_REPOSITORY
    assert patch["base_commit_sha"] == pin["commit_sha"]
    assert patch["source_pin_sha256"] == pin["source_pin_sha256"]
    assert patch["target_domain"] == "renderer"
    assert patch["changed_paths"] == ["src/roberta/human_response_renderer.py"]
    assert patch["file_additions"] == 0
    assert patch["file_deletions"] == 0
    assert "deterministic risk engine" in patch["files"][0]["review_diff"]
    assert "risk checks" in patch["files"][0]["review_diff"]
    validate_candidate_patch(
        patch,
        pin=pin,
        plan=plan,
        control_manifest=control,
        control_root=control_root,
    )
    assert all(repository == TARGET_REPOSITORY for repository, _, _ in source.calls)
    assert all(commit == pin["commit_sha"] for _, commit, _ in source.calls)


def test_non_target_patch_fails_closed(tmp_path: Path) -> None:
    pin = load_source_pin()
    source = FakeSource(pin)
    control_root = tmp_path / "control"
    control = materialize_control_artifact(pin, source, root=control_root)
    plan = _plan(corpus_sha256(lab87_corpus_cases(_cases())))
    with pytest.raises(ValueError, match="non-target Human domain"):
        construct_candidate_patch(
            pin,
            plan,
            control,
            control_root=control_root,
            replacements={"src/roberta/bridge_http.py": "def changed(): return True\n"},
            constructed_by="LAB-91",
            rationale="invalid cross-domain patch",
        )


def test_hidden_dependency_and_network_capability_are_blocked(tmp_path: Path) -> None:
    replacement = (
        "import requests\n"
        "def render_human_response(response_decision, *, response_depth=None):\n"
        "    requests.get('https://example.com')\n"
        "    return 'risk checks'\n"
    )
    pin, _, control_root, control, _, plan, patch = _setup(tmp_path, replacement=replacement)
    safety = qualify_patch_static_safety(
        patch,
        pin=pin,
        plan=plan,
        control_manifest=control,
        control_root=control_root,
    )
    assert safety["status"] == "BLOCKED"
    assert "NEW_IMPORT_OR_DEPENDENCY" in safety["blockers"]
    assert "NEW_FORBIDDEN_CAPABILITY" in safety["blockers"]


def test_authority_escalation_is_blocked(tmp_path: Path) -> None:
    replacement = (
        "execution_authorized = True\n"
        "def render_human_response(response_decision, *, response_depth=None):\n"
        "    return 'risk checks'\n"
    )
    pin, _, control_root, control, _, plan, patch = _setup(tmp_path, replacement=replacement)
    safety = qualify_patch_static_safety(
        patch,
        pin=pin,
        plan=plan,
        control_manifest=control,
        control_root=control_root,
    )
    assert safety["status"] == "BLOCKED"
    assert "NEW_FORBIDDEN_CAPABILITY" in safety["blockers"]


def test_supporting_patch_becomes_pr_eligible_only_after_lab89_87_85(tmp_path: Path) -> None:
    pin, _, control_root, control, cases, plan, patch = _setup(tmp_path)
    qualification = qualify_candidate_patch(
        pin,
        plan,
        patch,
        control,
        control_root=control_root,
        intervention_root=tmp_path / "candidate",
        sandbox_cases=cases,
        qualified_by="Bryant",
    )
    assert qualification["status"] == "PR_ELIGIBLE"
    assert qualification["pr_eligible"] is True
    assert qualification["lab87_receipt"]["control_failure_count"] == 20
    assert qualification["lab87_receipt"]["intervention_failure_count"] == 0
    assert qualification["lab87_receipt"]["contains_causal_outcome"] is False
    assert qualification["lab85_result"]["outcome"] == "SUPPORTS_HYPOTHESIS"
    assert qualification["lab85_qualification"]["direct_evidence_direction"] == "SUPPORTS"
    assert qualification["lab85_qualification"]["direct_evidence_strength"] == "DIRECT"
    package = qualification["promotion_package"]
    assert package["pr_eligible"] is True
    assert package["target_repository"] == TARGET_REPOSITORY
    assert package["base_commit_sha"] == pin["commit_sha"]
    assert package["production_pr_created"] is False
    assert package["production_pr_creation_authorized"] is False
    assert package["production_pr_merge_authorized"] is False
    assert package["lab87_manifest_id"] == qualification["lab87_manifest"]["manifest_id"]
    assert package["lab87_receipt_id"] == qualification["lab87_receipt"]["receipt_id"]
    assert package["lab85_result_id"] == qualification["lab85_result"]["result_id"]


def test_changed_but_non_supporting_patch_is_not_pr_eligible(tmp_path: Path) -> None:
    pin, _, control_root, control, cases, plan, patch = _setup(
        tmp_path,
        replacement=_renderer_non_supporting(),
    )
    qualification = qualify_candidate_patch(
        pin,
        plan,
        patch,
        control,
        control_root=control_root,
        intervention_root=tmp_path / "candidate",
        sandbox_cases=cases,
        qualified_by="Bryant",
    )
    assert qualification["status"] == "EVIDENCE_NOT_SUPPORTING"
    assert qualification["pr_eligible"] is False
    assert qualification["promotion_package"] is None
    assert qualification["lab85_result"]["outcome"] == "FALSIFIES_HYPOTHESIS"
    assert qualification["lab85_qualification"]["direct_evidence_direction"] == "CONTRADICTS"


def test_patch_ledger_is_body_free_duplicate_safe_and_evidence_unique(tmp_path: Path) -> None:
    pin, _, control_root, control, cases, plan, patch = _setup(tmp_path)
    qualification = qualify_candidate_patch(
        pin,
        plan,
        patch,
        control,
        control_root=control_root,
        intervention_root=tmp_path / "candidate",
        sandbox_cases=cases,
        qualified_by="Bryant",
    )
    ledger = empty_patch_ledger()
    validate_patch_ledger(ledger)
    updated, first = record_patch_qualification(ledger, qualification)
    assert first["status"] == "RECORDED"
    same, second = record_patch_qualification(updated, qualification)
    assert second["status"] == "UNCHANGED"
    assert same == updated
    encoded = json.dumps(updated)
    assert "replacement_utf8" not in encoded
    assert "review_diff" not in encoded
    assert ledger_summary(updated)["pr_eligible_count"] == 1
    assert updated["ledger_version"] == PATCH_LEDGER_VERSION

    conflict = deepcopy(qualification)
    conflict["qualification_id"] = "f" * 64
    with pytest.raises(ValueError, match="conflicting candidate patch qualification"):
        record_patch_qualification(updated, conflict)
