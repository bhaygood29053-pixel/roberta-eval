from __future__ import annotations

import hashlib
import json
from copy import deepcopy

import pytest

from roberta_eval.github_promotion import HUMAN_REMEDIATION_REPOSITORY
from roberta_eval.human_remediation_lifecycle import empty_lifecycle
from roberta_eval.human_remediation_lineage import (
    CHRONIC_REGRESSION,
    RECURRENCE_OBSERVED,
    ROOT_CAUSE_WARNING,
    STABLE_ROOT,
    build_generational_lineage_report,
    validate_generational_lineage_report,
)
from roberta_eval.human_remediation_reopen_cycle import (
    REOPEN_CHILD_ORIGIN,
    REOPEN_CYCLE_PROMOTION_VERSION,
    empty_reopen_cycle_promotion_ledger,
)

FAILURE = "technical_language_leak"
SERVICE = "pre_trade"


def _sha(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _fp(letter: str) -> str:
    return letter * 64


def _record(
    fingerprint: str,
    *,
    sequence: int,
    status: str = "RESOLVED",
    issue_number: int | None = None,
    parent: dict | None = None,
    generation: int | None = None,
    failure_code: str = FAILURE,
    service: str | None = SERVICE,
) -> dict:
    evidence = {
        "proposal_fingerprint": fingerprint,
        "previous_snapshot_id": f"cp-{sequence}-previous",
        "current_snapshot_id": f"cp-{sequence}-current",
        "failure_code": failure_code,
        "service": service,
        "baseline_count": 2,
        "baseline_rate": 0.2,
    }
    record = {
        "sequence": sequence,
        "lifecycle_id": f"human-remediation::{fingerprint}",
        "proposal_fingerprint": fingerprint,
        "proposal_sha256": _fp(chr(96 + sequence) if sequence <= 26 else "f"),
        "target_repository": HUMAN_REMEDIATION_REPOSITORY,
        "previous_snapshot_id": evidence["previous_snapshot_id"],
        "current_snapshot_id": evidence["current_snapshot_id"],
        "failure_code": failure_code,
        "recurrence": "RECURRENT" if parent else "NEW",
        "service": service,
        "baseline_count": 2,
        "baseline_rate": 0.2,
        "status": status,
        "issue_number": issue_number,
        "issue_url": (
            f"https://github.com/{HUMAN_REMEDIATION_REPOSITORY}/issues/{issue_number}"
            if issue_number
            else None
        ),
        "fix": None,
        "verifications": [],
        "events": [
            {"sequence": 1, "stage": "DETECTED", "evidence": deepcopy(evidence)},
            {"sequence": 2, "stage": "PROPOSED", "evidence": deepcopy(evidence)},
        ],
        "production_code_mutation": False,
        "execution_authorized": False,
    }
    if parent:
        lineage = {
            "origin": REOPEN_CHILD_ORIGIN,
            "new_cycle_id": parent["new_cycle_id"],
            "parent_proposal_fingerprint": parent["parent_proposal_fingerprint"],
            "parent_lifecycle_id": parent["parent_lifecycle_id"],
            "child_proposal_fingerprint": fingerprint,
            "child_lifecycle_id": record["lifecycle_id"],
            "closure_evidence_key": parent["closure_evidence_key"],
            "reopen_event_key": parent["reopen_event_key"],
            "parent_issue_number": parent["parent_issue_number"],
            "parent_issue_url": parent["parent_issue_url"],
            "failure_code": failure_code,
            "service": service,
            "prior_resolved_checkpoint_id": parent["prior_resolved_checkpoint_id"],
            "prior_resolved_checkpoint_sequence": parent["prior_resolved_checkpoint_sequence"],
            "fresh_checkpoint_id": parent["fresh_checkpoint_id"],
            "fresh_checkpoint_sequence": parent["fresh_checkpoint_sequence"],
            "fresh_checkpoint_corpus_sha256": parent["fresh_checkpoint_corpus_sha256"],
            "targeted_failure_count": parent["targeted_failure_count"],
            "targeted_failure_rate": parent["targeted_failure_rate"],
            "adjudicated_by": parent["adjudicated_by"],
            "reopen_adjudication_sha256": parent["reopen_adjudication_sha256"],
            "cycle_promoted_by": parent["approved_by"],
        }
        if generation is not None:
            lineage["generation"] = generation
        record["origin_kind"] = REOPEN_CHILD_ORIGIN
        record["lineage"] = lineage
    return record


def _promotion(parent: dict, child: dict, *, sequence: int) -> dict:
    cycle = f"human-remediation-reopen::{_sha({'sequence': sequence, 'child': child['proposal_fingerprint']})}"
    entry = {
        "promotion_version": REOPEN_CYCLE_PROMOTION_VERSION,
        "approved": True,
        "approved_by": "Bryant",
        "new_cycle_id": cycle,
        "seed_sha256": _sha({"seed": sequence}),
        "parent_proposal_fingerprint": parent["proposal_fingerprint"],
        "parent_lifecycle_id": parent["lifecycle_id"],
        "child_proposal_fingerprint": child["proposal_fingerprint"],
        "child_lifecycle_id": child["lifecycle_id"],
        "child_proposal_sha256": child["proposal_sha256"],
        "closure_evidence_key": _sha({"closure": sequence}),
        "reopen_event_key": _sha({"reopen": sequence}),
        "reopen_adjudication_sha256": _sha({"adjudication": sequence}),
        "production_code_mutation": False,
        "execution_authorized": False,
        "target_repository": HUMAN_REMEDIATION_REPOSITORY,
        "parent_issue_number": parent.get("issue_number") or 100 + sequence,
        "parent_issue_url": parent.get("issue_url") or f"https://github.com/{HUMAN_REMEDIATION_REPOSITORY}/issues/{100 + sequence}",
        "failure_code": child["failure_code"],
        "service": child.get("service"),
        "prior_resolved_checkpoint_id": parent["current_snapshot_id"],
        "fresh_checkpoint_id": child["current_snapshot_id"],
        "fresh_checkpoint_sequence": sequence + 10,
        "targeted_failure_count": 2,
        "targeted_failure_rate": 0.2,
        "adjudicated_by": "Bryant",
        "child_instantiated": True,
        "automatic_issue_creation": False,
    }
    approval_payload = {
        key: value
        for key, value in entry.items()
        if key
        in {
            "promotion_version",
            "approved",
            "approved_by",
            "new_cycle_id",
            "seed_sha256",
            "parent_proposal_fingerprint",
            "parent_lifecycle_id",
            "child_proposal_fingerprint",
            "child_lifecycle_id",
            "child_proposal_sha256",
            "closure_evidence_key",
            "reopen_event_key",
            "reopen_adjudication_sha256",
            "production_code_mutation",
            "execution_authorized",
        }
    }
    entry["approval_sha256"] = _sha(approval_payload)
    entry["sequence"] = sequence
    return entry


def _link(parent: dict, child_fp: str, *, child_sequence: int, generation: int | None = None) -> tuple[dict, dict]:
    placeholder = _record(child_fp, sequence=child_sequence)
    promotion = _promotion(parent, placeholder, sequence=child_sequence - 1)
    parent_data = {
        **promotion,
        "prior_resolved_checkpoint_sequence": child_sequence + 5,
        "fresh_checkpoint_corpus_sha256": _sha({"corpus": child_sequence}),
    }
    child = _record(
        child_fp,
        sequence=child_sequence,
        parent=parent_data,
        generation=generation,
    )
    promotion["child_lifecycle_id"] = child["lifecycle_id"]
    promotion["child_proposal_sha256"] = child["proposal_sha256"]
    approval_payload = {
        key: value
        for key, value in promotion.items()
        if key
        in {
            "promotion_version",
            "approved",
            "approved_by",
            "new_cycle_id",
            "seed_sha256",
            "parent_proposal_fingerprint",
            "parent_lifecycle_id",
            "child_proposal_fingerprint",
            "child_lifecycle_id",
            "child_proposal_sha256",
            "closure_evidence_key",
            "reopen_event_key",
            "reopen_adjudication_sha256",
            "production_code_mutation",
            "execution_authorized",
        }
    }
    promotion["approval_sha256"] = _sha(approval_payload)
    return child, promotion


def _chain(length: int) -> tuple[dict, dict]:
    lifecycle = empty_lifecycle()
    ledger = empty_reopen_cycle_promotion_ledger()
    root = _record(_fp("a"), sequence=1, issue_number=101)
    lifecycle["records"].append(root)
    parent = root
    for index in range(2, length + 1):
        child, promotion = _link(parent, _fp(chr(96 + index)), child_sequence=index)
        lifecycle["records"].append(child)
        ledger["promotions"].append(promotion)
        parent = child
    return lifecycle, ledger


def test_root_only_is_generation_zero_and_stable() -> None:
    lifecycle, ledger = _chain(1)
    report = build_generational_lineage_report(lifecycle, ledger)
    validate_generational_lineage_report(report)
    family = report["families"][0]
    assert family["deepest_generation"] == 0
    assert family["repeat_regression_count"] == 0
    assert family["health"] == STABLE_ROOT
    assert family["nodes"][0]["generation"] == 0


def test_child_and_grandchild_are_numbered_and_warn_on_repeat_regression() -> None:
    lifecycle, ledger = _chain(3)
    report = build_generational_lineage_report(lifecycle, ledger)
    family = report["families"][0]
    assert [node["generation"] for node in family["nodes"]] == [0, 1, 2]
    assert family["repeat_regression_count"] == 2
    assert family["deepest_generation"] == 2
    assert family["health"] == ROOT_CAUSE_WARNING
    assert family["root_cause_warning"] is True
    assert report["repeat_regression_family_count"] == 1
    assert report["root_cause_warning_family_count"] == 1
    assert family["paths"][0]["depth"] == 2
    assert len(family["paths"][0]["proposal_fingerprints"]) == 3


def test_first_recurrence_is_observed_but_not_root_cause_warning() -> None:
    lifecycle, ledger = _chain(2)
    family = build_generational_lineage_report(lifecycle, ledger)["families"][0]
    assert family["health"] == RECURRENCE_OBSERVED
    assert family["repeat_regression_count"] == 1
    assert family["root_cause_warning"] is False


def test_three_recurrences_are_chronic() -> None:
    lifecycle, ledger = _chain(4)
    report = build_generational_lineage_report(lifecycle, ledger)
    family = report["families"][0]
    assert family["deepest_generation"] == 3
    assert family["repeat_regression_count"] == 3
    assert family["health"] == CHRONIC_REGRESSION
    assert report["chronic_family_count"] == 1


def test_stored_generation_mismatch_fails_closed() -> None:
    lifecycle, ledger = _chain(2)
    lifecycle["records"][1]["lineage"]["generation"] = 7
    with pytest.raises(ValueError, match="generation conflicts"):
        build_generational_lineage_report(lifecycle, ledger)


def test_missing_parent_fails_closed() -> None:
    lifecycle, ledger = _chain(2)
    ledger["promotions"][0]["parent_proposal_fingerprint"] = _fp("z")
    with pytest.raises(ValueError, match="missing parent"):
        build_generational_lineage_report(lifecycle, ledger)


def test_failure_code_and_service_drift_fail_closed() -> None:
    lifecycle, ledger = _chain(2)
    lifecycle["records"][1]["failure_code"] = "different_failure"
    with pytest.raises(ValueError, match="failure-code drift"):
        build_generational_lineage_report(lifecycle, ledger)

    lifecycle, ledger = _chain(2)
    lifecycle["records"][1]["service"] = "different_service"
    with pytest.raises(ValueError, match="service drift"):
        build_generational_lineage_report(lifecycle, ledger)


def test_cycle_fails_closed() -> None:
    lifecycle, ledger = _chain(2)
    root = lifecycle["records"][0]
    child = lifecycle["records"][1]
    reverse_promotion = _promotion(child, root, sequence=2)
    # Make the former root a structurally valid reopen child of its child so cycle detection,
    # rather than origin validation, is the boundary under test.
    parent_data = {
        **reverse_promotion,
        "prior_resolved_checkpoint_sequence": 99,
        "fresh_checkpoint_corpus_sha256": _sha({"cycle": True}),
    }
    replacement_root = _record(
        root["proposal_fingerprint"],
        sequence=1,
        issue_number=root["issue_number"],
        parent=parent_data,
    )
    replacement_root["proposal_sha256"] = root["proposal_sha256"]
    lifecycle["records"][0] = replacement_root
    reverse_promotion["child_proposal_sha256"] = replacement_root["proposal_sha256"]
    approval_payload = {
        key: value
        for key, value in reverse_promotion.items()
        if key
        in {
            "promotion_version", "approved", "approved_by", "new_cycle_id", "seed_sha256",
            "parent_proposal_fingerprint", "parent_lifecycle_id", "child_proposal_fingerprint",
            "child_lifecycle_id", "child_proposal_sha256", "closure_evidence_key",
            "reopen_event_key", "reopen_adjudication_sha256", "production_code_mutation",
            "execution_authorized",
        }
    }
    reverse_promotion["approval_sha256"] = _sha(approval_payload)
    ledger["promotions"].append(reverse_promotion)
    with pytest.raises(ValueError, match="cycle"):
        build_generational_lineage_report(lifecycle, ledger)


def test_report_is_read_only_and_deterministic() -> None:
    lifecycle, ledger = _chain(3)
    before_lifecycle = deepcopy(lifecycle)
    before_ledger = deepcopy(ledger)
    first = build_generational_lineage_report(lifecycle, ledger)
    second = build_generational_lineage_report(lifecycle, ledger)
    assert first == second
    assert first["read_only"] is True
    assert first["lifecycle_mutation"] is False
    assert first["automatic_issue_creation"] is False
    assert first["production_code_mutation"] is False
    assert first["execution_authorized"] is False
    assert lifecycle == before_lifecycle
    assert ledger == before_ledger
