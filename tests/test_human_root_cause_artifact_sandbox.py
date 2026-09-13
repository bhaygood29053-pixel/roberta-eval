from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from roberta_eval.human_remediation_root_cause import DOMAINS
from roberta_eval.human_root_cause_artifact_sandbox import (
    ARTIFACT_SANDBOX_LEDGER_VERSION,
    ROBERTA_RENDERER_ENTRYPOINT,
    ROBERTA_REPOSITORY,
    empty_artifact_sandbox_ledger,
    execute_materialized_sandbox,
    lab87_corpus_cases,
    load_source_pin,
    materialize_candidate_artifact,
    materialize_control_artifact,
    qualify_materialized_receipt_with_lab85,
    record_materialization,
    validate_artifact_sandbox_ledger,
    validate_source_pin,
)
from roberta_eval.human_root_cause_direct_evidence import (
    EXPERIMENT_PLAN_VERSION,
    OUTCOMES,
    validate_experiment_plan,
)
from roberta_eval.human_root_cause_experiment_execution import corpus_sha256


def _sha(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _renderer(control: bool) -> bytes:
    phrase = "deterministic risk engine" if control else "risk checks"
    return (
        "def render_human_response(response_decision, *, response_depth=None):\n"
        f"    return {phrase!r} + ': ' + str(response_decision.get('message', ''))\n"
    ).encode("utf-8")


class FakeSource:
    def __init__(self, pin: dict) -> None:
        self.pin = pin
        self.calls: list[tuple[str, str, str]] = []
        self.files = {
            "src/roberta/human_response_contract.py": b"CONTRACT_VERSION = 'fake/v1'\n",
            "src/roberta/human_response_renderer.py": _renderer(True),
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


def _materialize(tmp_path: Path):
    pin = load_source_pin()
    source = FakeSource(pin)
    cases = _cases()
    plan = _plan(corpus_sha256(lab87_corpus_cases(cases)))
    control_root = tmp_path / "control"
    intervention_root = tmp_path / "intervention"
    control = materialize_control_artifact(pin, source, root=control_root)
    control_renderer = next(
        item for item in control["files"] if item["path"] == "src/roberta/human_response_renderer.py"
    )
    overlay = [
        {
            "path": "src/roberta/human_response_renderer.py",
            "expected_control_sha256": control_renderer["sha256"],
            "content_utf8": _renderer(False).decode("utf-8"),
        }
    ]
    intervention, evidence = materialize_candidate_artifact(
        pin,
        plan,
        control,
        control_root=control_root,
        candidate_root=intervention_root,
        overlay=overlay,
    )
    return pin, source, cases, plan, control_root, intervention_root, control, intervention, evidence


def test_tracked_source_pin_binds_real_accepted_public_roberta_commit() -> None:
    pin = load_source_pin()
    validate_source_pin(pin)
    assert pin["repository"] == ROBERTA_REPOSITORY
    assert pin["commit_sha"] == "becb264b8026b5cbbf99f0d12dea62463510c6ee"
    assert pin["runtime_entrypoint"] == ROBERTA_RENDERER_ENTRYPOINT
    assert pin["accepted"] is True
    assert pin["floating_ref"] is False
    paths = {item["path"] for item in pin["files"]}
    assert "src/roberta/human_response_renderer.py" in paths
    assert "src/roberta/human_response_contract.py" in paths
    assert "src/roberta/__init__.py" not in paths
    assert "src/roberta/recommendation_policy.py" not in paths
    assert set(pin["empty_domains_allowed"]) == {"policy", "prompt"}


def test_control_materialization_is_commit_bound_and_reproducible(tmp_path: Path) -> None:
    pin = load_source_pin()
    source = FakeSource(pin)
    first = materialize_control_artifact(pin, source, root=tmp_path / "one")
    second = materialize_control_artifact(pin, source, root=tmp_path / "two")
    assert first["tree_sha256"] == second["tree_sha256"]
    assert first["domain_digests"] == second["domain_digests"]
    assert len(source.calls) == len(pin["files"]) * 2
    assert all(repository == ROBERTA_REPOSITORY for repository, _, _ in source.calls)
    assert all(commit == pin["commit_sha"] for _, commit, _ in source.calls)


def test_renderer_only_overlay_changes_only_target_domain(tmp_path: Path) -> None:
    *_, plan, _, _, control, intervention, evidence = _materialize(tmp_path)
    assert evidence["target_domain"] == "renderer"
    assert evidence["changed_paths"] == ["src/roberta/human_response_renderer.py"]
    assert control["domain_digests"]["renderer"] != intervention["domain_digests"]["renderer"]
    for domain in plan["held_constant_domains"]:
        assert control["domain_digests"][domain] == intervention["domain_digests"][domain]


def test_non_target_overlay_fails_closed(tmp_path: Path) -> None:
    pin = load_source_pin()
    source = FakeSource(pin)
    cases = _cases()
    plan = _plan(corpus_sha256(lab87_corpus_cases(cases)))
    control_root = tmp_path / "control"
    control = materialize_control_artifact(pin, source, root=control_root)
    bridge = next(item for item in control["files"] if item["path"] == "src/roberta/bridge_http.py")
    with pytest.raises(ValueError, match="non-target Human domain"):
        materialize_candidate_artifact(
            pin,
            plan,
            control,
            control_root=control_root,
            candidate_root=tmp_path / "intervention",
            overlay=[
                {
                    "path": "src/roberta/bridge_http.py",
                    "expected_control_sha256": bridge["sha256"],
                    "content_utf8": "changed = True\n",
                }
            ],
        )


def test_materialized_offline_sandbox_produces_lab87_receipt_and_lab85_support(tmp_path: Path) -> None:
    (
        pin,
        _,
        cases,
        plan,
        control_root,
        intervention_root,
        control,
        intervention,
        evidence,
    ) = _materialize(tmp_path)
    receipt, handoff = execute_materialized_sandbox(
        plan,
        pin,
        control,
        intervention,
        evidence,
        control_root=control_root,
        intervention_root=intervention_root,
        sandbox_cases=cases,
        performed_by="LAB-89",
    )
    assert receipt["control_failure_count"] == 20
    assert receipt["intervention_failure_count"] == 0
    assert receipt["contains_causal_outcome"] is False
    assert "outcome" not in receipt
    assert handoff["runner_outcome_authority"] is False
    assert handoff["lab85_qualification_authority"] is True
    result, qualification = qualify_materialized_receipt_with_lab85(
        plan,
        receipt,
        verified_by="Bryant",
    )
    assert result["outcome"] == "SUPPORTS_HYPOTHESIS"
    assert qualification["direct_evidence_direction"] == "SUPPORTS"
    assert qualification["direct_evidence_strength"] == "DIRECT"


def test_artifact_sandbox_ledger_is_duplicate_safe_and_conflict_closed(tmp_path: Path) -> None:
    *_, evidence = _materialize(tmp_path)
    ledger = empty_artifact_sandbox_ledger()
    validate_artifact_sandbox_ledger(ledger)
    updated, first = record_materialization(ledger, evidence)
    assert first["status"] == "RECORDED"
    same, second = record_materialization(updated, evidence)
    assert second["status"] == "UNCHANGED"
    assert same == updated
    conflict = deepcopy(evidence)
    conflict["overlay_sha256"] = "f" * 64
    conflict["materialization_id"] = _sha({key: value for key, value in conflict.items() if key != "materialization_id"})
    with pytest.raises(ValueError, match="conflicting artifact materialization"):
        record_materialization(updated, conflict)
    assert updated["ledger_version"] == ARTIFACT_SANDBOX_LEDGER_VERSION


def test_source_pin_tamper_fails_closed() -> None:
    pin = load_source_pin()
    tampered = deepcopy(pin)
    tampered["commit_sha"] = "f" * 40
    with pytest.raises(ValueError, match="digest mismatch"):
        validate_source_pin(tampered)
