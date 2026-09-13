from __future__ import annotations

import hashlib
import json

import pytest

from roberta_eval.github_promotion import HUMAN_REMEDIATION_REPOSITORY
from roberta_eval.human_remediation_lineage import (
    CHRONIC_REGRESSION,
    GENERATIONAL_LINEAGE_VERSION,
    HEALTH_STATES,
    LINEAGE_HEALTH_VERSION,
    RECURRENCE_OBSERVED,
    ROOT_CAUSE_WARNING,
    STABLE_ROOT,
    validate_generational_lineage_report,
)
from roberta_eval.human_remediation_lifecycle import LIFECYCLE_VERSION, validate_lifecycle
from roberta_eval.human_remediation_root_cause import build_investigation_package
from roberta_eval.human_root_cause_evidence_acquisition import (
    CORRELATION_VERSION,
    EVIDENCE_BUNDLE_VERSION,
    SOURCE_SNAPSHOT_VERSION,
    acquisition_summary,
    artifact_kind,
    build_evidence_bundle,
    build_lab81_package_from_bundle,
    build_source_snapshot,
    classify_artifact,
    validate_evidence_bundle,
    validate_source_snapshot,
)

FAILURE = "technical_language_leak"
SERVICE = "pre_trade"
FPS = ["a" * 64, "b" * 64, "c" * 64]
SHAS = ["1" * 40, "2" * 40, "3" * 40]


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
        "root_proposal_fingerprint": FPS[0],
        "root_lifecycle_id": f"human-remediation::{FPS[0]}",
        "failure_code": FAILURE,
        "service": SERVICE,
        "node_count": 3,
        "repeat_regression_count": 2,
        "deepest_generation": 2,
        "health": ROOT_CAUSE_WARNING,
        "root_cause_warning": True,
        "root_cause_interpretation": "Repeated accepted recurrence indicates a remediation-loop risk; it does not by itself prove the underlying causal root cause.",
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


def _event(sequence: int, stage: str) -> dict:
    return {"sequence": sequence, "stage": stage, "evidence": {"stage": stage}}


def _lifecycle(*, missing_fix_generation: int | None = None) -> dict:
    records = []
    for generation, (fp, merge_sha) in enumerate(zip(FPS, SHAS)):
        fix = None
        if generation != missing_fix_generation:
            fix = {
                "repository": HUMAN_REMEDIATION_REPOSITORY,
                "pr_number": 101 + generation,
                "merge_sha": merge_sha,
                "verified_by": "Bryant",
                "verification_checkpoint_sequence_floor": generation + 1,
                "latest_checkpoint_at_fix": f"cp-before-{generation}",
            }
        records.append(
            {
                "sequence": generation + 1,
                "lifecycle_id": f"human-remediation::{fp}",
                "proposal_fingerprint": fp,
                "proposal_sha256": _sha({"proposal": fp}),
                "target_repository": HUMAN_REMEDIATION_REPOSITORY,
                "previous_snapshot_id": f"cp-prev-{generation}",
                "current_snapshot_id": f"cp-base-{generation}",
                "failure_code": FAILURE,
                "recurrence": "NEW" if generation == 0 else "RECURRENT",
                "service": SERVICE,
                "baseline_count": 2,
                "baseline_rate": 0.2,
                "status": "RESOLVED",
                "issue_number": None,
                "issue_url": None,
                "fix": fix,
                "verifications": [
                    {
                        "checkpoint_id": f"cp-clean-{generation}",
                        "checkpoint_sequence": 10 + generation,
                        "outcome": "RESOLVED",
                        "targeted_failure_count": 0,
                        "targeted_failure_rate": 0.0,
                        "baseline_count": 2,
                        "baseline_rate": 0.2,
                    }
                ],
                "events": [_event(1, "DETECTED"), _event(2, "PROPOSED")],
                "production_code_mutation": False,
                "execution_authorized": False,
            }
        )
    lifecycle = {
        "lifecycle_version": LIFECYCLE_VERSION,
        "policy": {
            "proposal_registration_required": True,
            "promotion_evidence_source": "roberta_human_remediation_promotion_ledger/v1",
            "fix_merge_requires_explicit_evidence": True,
            "replay_verification_requires_later_accepted_checkpoint": True,
            "resolution_requires_zero_targeted_failure_count": True,
            "improvement_requires_lower_targeted_failure_rate": True,
            "raw_responses_stored": False,
            "proposal_bodies_stored": False,
            "production_code_mutation": False,
            "execution_authorized": False,
        },
        "records": records,
    }
    validate_lifecycle(lifecycle)
    return lifecycle


class FakeTransport:
    def __init__(self, *, bad_merge: bool = False, conflicting_file: bool = False) -> None:
        self.bad_merge = bad_merge
        self.conflicting_file = conflicting_file
        self.calls: list[tuple[str, int | str]] = []

    def get_pull_request(self, *, repository: str, pr_number: int) -> dict:
        self.calls.append(("pr", pr_number))
        generation = pr_number - 101
        sha = SHAS[generation]
        if self.bad_merge and generation == 1:
            sha = "f" * 40
        return {
            "number": pr_number,
            "merged": True,
            "merged_at": "2026-09-13T00:00:00Z",
            "merge_commit_sha": sha,
            "title": f"Human fix generation {generation}",
            "html_url": f"https://github.com/{repository}/pull/{pr_number}",
        }

    def list_pull_request_files(self, *, repository: str, pr_number: int) -> list[dict]:
        self.calls.append(("files", pr_number))
        generation = pr_number - 101
        rows = [
            {
                "filename": "src/roberta/human_response_renderer.py",
                "status": "modified",
                "sha": f"renderer-{generation}",
                "additions": 4,
                "deletions": 2,
                "changes": 6,
            },
            {
                "filename": "tests/test_human_response_renderer.py",
                "status": "modified",
                "sha": f"renderer-test-{generation}",
                "additions": 2,
                "deletions": 0,
                "changes": 2,
            },
        ]
        if generation == 1:
            rows.append(
                {
                    "filename": "src/roberta/recommendation_policy.py",
                    "status": "modified",
                    "sha": "policy-1",
                    "additions": 3,
                    "deletions": 1,
                    "changes": 4,
                }
            )
        if generation == 2:
            rows.extend(
                [
                    {
                        "filename": ".github/styles/RobertaHuman/TechnicalVocabulary.yml",
                        "status": "modified",
                        "sha": "vocab-2",
                        "additions": 3,
                        "deletions": 1,
                        "changes": 4,
                    },
                    {
                        "filename": "src/roberta/service_adapter.py",
                        "status": "modified",
                        "sha": "adapter-2",
                        "additions": 5,
                        "deletions": 1,
                        "changes": 6,
                    },
                    {
                        "filename": "src/roberta/prompts/human_system_prompt.txt",
                        "status": "modified",
                        "sha": "prompt-2",
                        "additions": 1,
                        "deletions": 1,
                        "changes": 2,
                    },
                ]
            )
        if self.conflicting_file and generation == 0:
            rows.append(
                {
                    "filename": "src/roberta/human_response_renderer.py",
                    "status": "modified",
                    "sha": "renderer-conflict",
                    "additions": 99,
                    "deletions": 0,
                    "changes": 99,
                }
            )
        return rows

    def list_commit_checks(self, *, repository: str, commit_sha: str) -> list[dict]:
        self.calls.append(("checks", commit_sha))
        return [
            {
                "name": "Human Language Acceptance",
                "status": "completed",
                "conclusion": "success",
                "details_url": f"https://github.com/{repository}/actions/runs/{commit_sha[0]}",
            }
        ]


def test_artifact_classifier_covers_all_six_human_domains() -> None:
    assert "renderer" in classify_artifact("src/roberta/human_response_renderer.py")
    assert "policy" in classify_artifact("src/roberta/recommendation_policy.py")
    assert "prompt" in classify_artifact("src/roberta/prompts/system_prompt.txt")
    assert "service_adapter" in classify_artifact("src/roberta/service_adapter.py")
    assert "vocabulary_replacement" in classify_artifact(".github/styles/RobertaHuman/TechnicalVocabulary.yml")
    assert "shared_human_layer" in classify_artifact("src/roberta/human_language_acceptance.py")
    assert artifact_kind("tests/test_human_response_renderer.py") == "TEST_ARTIFACT"


def test_source_snapshot_binds_pr_merge_files_checks_and_replays() -> None:
    transport = FakeTransport()
    snapshot = build_source_snapshot(_lineage_report(), _lifecycle(), transport=transport)
    validate_source_snapshot(snapshot)
    assert snapshot["source_snapshot_version"] == SOURCE_SNAPSHOT_VERSION
    assert snapshot["source_count"] == 3
    assert snapshot["external_calls"] == 9
    assert snapshot["source_transport_used"] is True
    assert snapshot["read_only"] is True
    assert snapshot["github_issue_mutation"] is False
    assert all(source["source_mode"] == "READ_ONLY_GITHUB_PR_AND_CHECKS" for source in snapshot["sources"])
    assert all(source["accepted_replays"][0]["outcome"] == "RESOLVED" for source in snapshot["sources"])


def test_repeated_renderer_changes_rank_high_but_never_gain_causal_authority() -> None:
    lineage = _lineage_report()
    snapshot = build_source_snapshot(lineage, _lifecycle(), transport=FakeTransport())
    bundle = build_evidence_bundle(lineage, snapshot, root_fingerprint=FPS[0])
    validate_evidence_bundle(bundle)
    assert bundle["evidence_bundle_version"] == EVIDENCE_BUNDLE_VERSION
    assert bundle["correlation"]["correlation_version"] == CORRELATION_VERSION
    assert bundle["correlation"]["causal_authority"] is False
    assert bundle["correlation_is_not_causation"] is True
    assert bundle["automatic_direct_evidence_count"] == 0
    assert all(item["strength"] == "INDIRECT" for item in bundle["lab81_evidence"])
    renderer = next(item for item in bundle["correlation"]["findings"] if item["domain"] == "renderer")
    assert renderer["signal"] == "REPEATED_CROSS_GENERATION_ASSOCIATION"
    assert renderer["implementation_generations"] == [0, 1, 2]
    assert renderer["causal_authority"] is False
    summary = acquisition_summary(bundle)
    assert summary["top_correlated_domain"] == "renderer"
    assert summary["causal_authority"] is False


def test_automatic_bundle_can_only_make_lab81_suspect_not_confirm_root_cause() -> None:
    lineage = _lineage_report()
    snapshot = build_source_snapshot(lineage, _lifecycle(), transport=FakeTransport())
    bundle = build_evidence_bundle(lineage, snapshot, root_fingerprint=FPS[0])
    package = build_lab81_package_from_bundle(lineage, bundle)
    assert package["confirmed_root_causes"] == []
    assert package["root_cause_named"] is False
    renderer = next(item for item in package["findings"] if item["domain"] == "renderer")
    assert renderer["state"] == "SUSPECTED"
    assert renderer["direct_support_count"] == 0


def test_lab81_direct_evidence_threshold_still_controls_confirmation() -> None:
    lineage = _lineage_report()
    snapshot = build_source_snapshot(lineage, _lifecycle(), transport=FakeTransport())
    bundle = build_evidence_bundle(lineage, snapshot, root_fingerprint=FPS[0])
    evidence = list(bundle["lab81_evidence"])
    evidence.extend(
        [
            {
                "domain": "renderer",
                "generation": 0,
                "direction": "SUPPORTS",
                "strength": "DIRECT",
                "source_ref": "accepted_test:renderer-generation-0",
                "artifact_sha256": _sha({"direct": 0}),
                "statement": "Direct accepted test isolates the renderer at generation 0.",
            },
            {
                "domain": "renderer",
                "generation": 2,
                "direction": "SUPPORTS",
                "strength": "DIRECT",
                "source_ref": "accepted_test:renderer-generation-2",
                "artifact_sha256": _sha({"direct": 2}),
                "statement": "Direct accepted test independently isolates the renderer at generation 2.",
            },
        ]
    )
    package = build_investigation_package(lineage, root_fingerprint=FPS[0], evidence=evidence)
    assert package["confirmed_root_causes"] == ["renderer"]
    assert package["root_cause_named"] is True


def test_missing_fix_or_offline_mode_does_not_invent_changed_files() -> None:
    lineage = _lineage_report()
    snapshot = build_source_snapshot(lineage, _lifecycle(missing_fix_generation=1), transport=None)
    assert snapshot["source_count"] == 2
    assert snapshot["external_calls"] == 0
    assert all(source["files"] == [] and source["checks"] == [] for source in snapshot["sources"])
    bundle = build_evidence_bundle(lineage, snapshot, root_fingerprint=FPS[0])
    assert bundle["lab81_evidence"] == []
    assert any(item["kind"] == "ACCEPTED_REPLAY" for item in bundle["context_records"])
    package = build_lab81_package_from_bundle(lineage, bundle)
    assert package["root_cause_named"] is False


def test_observed_pr_merge_sha_conflict_fails_closed() -> None:
    with pytest.raises(ValueError, match="merge SHA conflicts"):
        build_source_snapshot(_lineage_report(), _lifecycle(), transport=FakeTransport(bad_merge=True))


def test_conflicting_duplicate_file_identity_fails_closed_before_lab81() -> None:
    lineage = _lineage_report()
    snapshot = build_source_snapshot(
        lineage,
        _lifecycle(),
        transport=FakeTransport(conflicting_file=True),
    )
    with pytest.raises(ValueError, match="conflicting automatic LAB #81 evidence identity"):
        build_evidence_bundle(lineage, snapshot, root_fingerprint=FPS[0])


def test_bundle_is_deterministic_and_read_only() -> None:
    lineage = _lineage_report()
    lifecycle = _lifecycle()
    first_snapshot = build_source_snapshot(lineage, lifecycle, transport=FakeTransport())
    second_snapshot = build_source_snapshot(lineage, lifecycle, transport=FakeTransport())
    assert first_snapshot == second_snapshot
    first = build_evidence_bundle(lineage, first_snapshot, root_fingerprint=FPS[0])
    second = build_evidence_bundle(lineage, second_snapshot, root_fingerprint=FPS[0])
    assert first == second
    assert first["read_only"] is True
    assert first["production_code_mutation"] is False
    assert first["execution_authorized"] is False
