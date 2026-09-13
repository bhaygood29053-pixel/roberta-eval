from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from .github_promotion import HUMAN_REMEDIATION_REPOSITORY
from .human_remediation_closure import (
    default_closure_ledger_path,
    load_closure_ledger,
    validate_closure_ledger,
)
from .human_remediation_lifecycle import (
    default_lifecycle_path,
    load_lifecycle,
    validate_lifecycle,
    write_lifecycle,
)
from .human_remediation_promotion import validate_human_remediation_proposal
from .human_remediation_reopen import (
    GENUINE_HUMAN_QUALITY_REGRESSION,
    REOPEN_CYCLE_SEED_VERSION,
    build_new_cycle_seed,
    default_reopen_adjudication_ledger_path,
    load_reopen_adjudication_ledger,
    validate_reopen_adjudication_ledger,
)

REOPEN_CYCLE_PROMOTION_VERSION = "roberta_human_remediation_reopen_cycle_promotion/v1"
REOPEN_CYCLE_PROMOTION_LEDGER_VERSION = "roberta_human_remediation_reopen_cycle_promotion_ledger/v1"
REOPEN_CYCLE_PROMOTION_RESULT_VERSION = "roberta_human_remediation_reopen_cycle_promotion_result/v1"
REOPEN_CHILD_ORIGIN = "REOPEN_REGRESSION"


def default_reopen_cycle_promotion_ledger_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "human_remediation_reopen_cycle_promotion_ledger.json"


def empty_reopen_cycle_promotion_ledger() -> dict[str, Any]:
    return {
        "ledger_version": REOPEN_CYCLE_PROMOTION_LEDGER_VERSION,
        "policy": {
            "explicit_owner_approval_required": True,
            "parent_closed_evidence_required": True,
            "duplicate_cycle_creation_prevented": True,
            "automatic_issue_creation": False,
            "production_code_mutation": False,
            "execution_authorized": False,
        },
        "promotions": [],
    }


def load_reopen_cycle_promotion_ledger(path: Path | None = None) -> dict[str, Any]:
    source = path or default_reopen_cycle_promotion_ledger_path()
    payload = json.loads(source.read_text(encoding="utf-8"))
    validate_reopen_cycle_promotion_ledger(payload)
    return payload


def write_reopen_cycle_promotion_ledger(path: Path, ledger: dict[str, Any]) -> None:
    validate_reopen_cycle_promotion_ledger(ledger)
    path.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _stable_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _find_parent(lifecycle: dict[str, Any], fingerprint: str) -> dict[str, Any]:
    record = next(
        (item for item in lifecycle["records"] if item["proposal_fingerprint"] == fingerprint),
        None,
    )
    if record is None:
        raise ValueError("reopen cycle promotion parent lifecycle was not found")
    if record.get("status") != "RESOLVED":
        raise ValueError("reopen cycle promotion requires parent lifecycle status RESOLVED")
    return record


def _find_adjudication(adjudication_ledger: dict[str, Any], fingerprint: str) -> dict[str, Any]:
    row = next(
        (item for item in adjudication_ledger["adjudications"] if item["proposal_fingerprint"] == fingerprint),
        None,
    )
    if row is None:
        raise ValueError("reopen cycle promotion requires a LAB #75 adjudication")
    if row.get("classification") != GENUINE_HUMAN_QUALITY_REGRESSION:
        raise ValueError("administrative/non-quality reopen cannot be promoted into a new remediation cycle")
    if row.get("new_cycle_eligible") is not True:
        raise ValueError("reopen adjudication is not eligible for a new remediation cycle")
    return row


def _find_closure(closure_ledger: dict[str, Any], seed: dict[str, Any]) -> dict[str, Any]:
    matches = [
        item
        for item in closure_ledger["closures"]
        if item.get("proposal_fingerprint") == seed["prior_proposal_fingerprint"]
        and item.get("closure_evidence_key") == seed["closure_evidence_key"]
    ]
    if len(matches) != 1:
        raise ValueError("reopen cycle promotion requires matching terminal closure evidence")
    closure = matches[0]
    if closure.get("issue_closed") is not True or closure.get("issue_state") != "closed":
        raise ValueError("reopen cycle promotion requires accepted CLOSED issue evidence")
    if closure.get("issue_number") != seed["issue_number"] or closure.get("issue_url") != seed["issue_url"]:
        raise ValueError("reopen cycle promotion closure issue identity mismatch")
    return closure


def _child_fingerprint(seed: dict[str, Any]) -> str:
    return _stable_sha256(
        {
            "origin": REOPEN_CHILD_ORIGIN,
            "new_cycle_id": seed["new_cycle_id"],
            "prior_proposal_fingerprint": seed["prior_proposal_fingerprint"],
            "reopen_event_key": seed["reopen_event_key"],
            "closure_evidence_key": seed["closure_evidence_key"],
            "failure_code": seed["failure_code"],
            "fresh_checkpoint_id": seed["fresh_checkpoint_id"],
            "fresh_checkpoint_sequence": seed["fresh_checkpoint_sequence"],
        }
    )


def _child_lifecycle_id(child_fingerprint: str) -> str:
    return f"human-remediation::{child_fingerprint}"


def build_child_proposal(seed: dict[str, Any]) -> dict[str, Any]:
    if seed.get("seed_version") != REOPEN_CYCLE_SEED_VERSION:
        raise ValueError("unsupported LAB #75 reopen cycle seed version")
    if seed.get("new_cycle_eligible") is not True:
        raise ValueError("reopen cycle seed is not eligible")
    if seed.get("automatic_new_cycle_creation") is not False:
        raise ValueError("reopen cycle seed cannot authorize automatic cycle creation")
    if seed.get("production_code_mutation") is not False or seed.get("execution_authorized") is not False:
        raise ValueError("reopen cycle seed exceeds the allowed authority boundary")

    fingerprint = _child_fingerprint(seed)
    service = seed.get("service")
    service_text = f" in {service}" if service else ""
    proposal = {
        "proposal_kind": "human_language_remediation",
        "proposal_fingerprint": fingerprint,
        "target_repository": HUMAN_REMEDIATION_REPOSITORY,
        "previous_snapshot_id": seed["prior_resolved_checkpoint_id"],
        "current_snapshot_id": seed["fresh_checkpoint_id"],
        "title": f"Human regression remediation — {seed['failure_code']}",
        "body": (
            f"A previously resolved Human-language defect `{seed['failure_code']}`{service_text} "
            f"recurred in accepted checkpoint `{seed['fresh_checkpoint_id']}`. "
            "This child remediation is linked to the prior CLOSED cycle and must pass the normal "
            "approval, issue, fix, replay, resolution and closure gates independently."
        ),
        "human_priority": {
            "failure_code": seed["failure_code"],
            "recurrence": "RECURRENT",
            "service": service,
            "current_count": int(seed["targeted_failure_count"]),
            "current_rate": float(seed["targeted_failure_rate"]),
        },
        "issue_created": False,
        "reviewable_proposal_only": True,
        "production_mutation": False,
        "execution_authorized": False,
        "ai_judge_used": False,
        "judge_model_calls": 0,
        "external_calls": 0,
    }
    validate_human_remediation_proposal(proposal)
    return proposal


def _lineage(
    *,
    seed: dict[str, Any],
    adjudication: dict[str, Any],
    parent: dict[str, Any],
    child_fingerprint: str,
    promoted_by: str,
) -> dict[str, Any]:
    fresh = adjudication["fresh_regression_evidence"]
    return {
        "origin": REOPEN_CHILD_ORIGIN,
        "new_cycle_id": seed["new_cycle_id"],
        "parent_proposal_fingerprint": seed["prior_proposal_fingerprint"],
        "parent_lifecycle_id": parent["lifecycle_id"],
        "child_proposal_fingerprint": child_fingerprint,
        "child_lifecycle_id": _child_lifecycle_id(child_fingerprint),
        "closure_evidence_key": seed["closure_evidence_key"],
        "reopen_event_key": seed["reopen_event_key"],
        "parent_issue_number": seed["issue_number"],
        "parent_issue_url": seed["issue_url"],
        "failure_code": seed["failure_code"],
        "service": seed.get("service"),
        "prior_resolved_checkpoint_id": seed["prior_resolved_checkpoint_id"],
        "prior_resolved_checkpoint_sequence": int(adjudication["prior_resolved_checkpoint_sequence"]),
        "fresh_checkpoint_id": seed["fresh_checkpoint_id"],
        "fresh_checkpoint_sequence": int(seed["fresh_checkpoint_sequence"]),
        "fresh_checkpoint_corpus_sha256": fresh["checkpoint_corpus_sha256"],
        "targeted_failure_count": int(seed["targeted_failure_count"]),
        "targeted_failure_rate": float(seed["targeted_failure_rate"]),
        "adjudicated_by": seed["adjudicated_by"],
        "reopen_adjudication_sha256": adjudication["decision_sha256"],
        "cycle_promoted_by": promoted_by,
    }


def _child_record(
    *,
    sequence: int,
    proposal: dict[str, Any],
    lineage: dict[str, Any],
) -> dict[str, Any]:
    priority = proposal["human_priority"]
    digest = _stable_sha256(proposal)
    base_evidence = {
        "origin": REOPEN_CHILD_ORIGIN,
        "new_cycle_id": lineage["new_cycle_id"],
        "parent_proposal_fingerprint": lineage["parent_proposal_fingerprint"],
        "closure_evidence_key": lineage["closure_evidence_key"],
        "reopen_event_key": lineage["reopen_event_key"],
        "fresh_checkpoint_id": lineage["fresh_checkpoint_id"],
        "fresh_checkpoint_sequence": lineage["fresh_checkpoint_sequence"],
        "failure_code": priority["failure_code"],
        "service": priority.get("service"),
        "baseline_count": int(priority["current_count"]),
        "baseline_rate": float(priority["current_rate"]),
    }
    return {
        "sequence": sequence,
        "lifecycle_id": lineage["child_lifecycle_id"],
        "proposal_fingerprint": proposal["proposal_fingerprint"],
        "proposal_sha256": digest,
        "target_repository": HUMAN_REMEDIATION_REPOSITORY,
        "previous_snapshot_id": proposal["previous_snapshot_id"],
        "current_snapshot_id": proposal["current_snapshot_id"],
        "failure_code": priority["failure_code"],
        "recurrence": "RECURRENT",
        "service": priority.get("service"),
        "baseline_count": int(priority["current_count"]),
        "baseline_rate": float(priority["current_rate"]),
        "status": "PROPOSED",
        "issue_number": None,
        "issue_url": None,
        "fix": None,
        "verifications": [],
        "events": [
            {"sequence": 1, "stage": "DETECTED", "evidence": deepcopy(base_evidence)},
            {
                "sequence": 2,
                "stage": "PROPOSED",
                "evidence": {**deepcopy(base_evidence), "proposal_sha256": digest},
            },
        ],
        "origin_kind": REOPEN_CHILD_ORIGIN,
        "lineage": deepcopy(lineage),
        "production_code_mutation": False,
        "execution_authorized": False,
    }


def _promotion_entry(
    *,
    seed: dict[str, Any],
    adjudication: dict[str, Any],
    parent: dict[str, Any],
    proposal: dict[str, Any],
    lineage: dict[str, Any],
    promoted_by: str,
) -> dict[str, Any]:
    seed_sha = _stable_sha256(seed)
    proposal_sha = _stable_sha256(proposal)
    approval_payload = {
        "promotion_version": REOPEN_CYCLE_PROMOTION_VERSION,
        "approved": True,
        "approved_by": promoted_by,
        "new_cycle_id": seed["new_cycle_id"],
        "seed_sha256": seed_sha,
        "parent_proposal_fingerprint": seed["prior_proposal_fingerprint"],
        "parent_lifecycle_id": parent["lifecycle_id"],
        "child_proposal_fingerprint": proposal["proposal_fingerprint"],
        "child_lifecycle_id": lineage["child_lifecycle_id"],
        "child_proposal_sha256": proposal_sha,
        "closure_evidence_key": seed["closure_evidence_key"],
        "reopen_event_key": seed["reopen_event_key"],
        "reopen_adjudication_sha256": adjudication["decision_sha256"],
        "production_code_mutation": False,
        "execution_authorized": False,
    }
    approval_sha = _stable_sha256(approval_payload)
    return {
        **approval_payload,
        "approval_sha256": approval_sha,
        "target_repository": HUMAN_REMEDIATION_REPOSITORY,
        "parent_issue_number": seed["issue_number"],
        "parent_issue_url": seed["issue_url"],
        "failure_code": seed["failure_code"],
        "service": seed.get("service"),
        "prior_resolved_checkpoint_id": seed["prior_resolved_checkpoint_id"],
        "fresh_checkpoint_id": seed["fresh_checkpoint_id"],
        "fresh_checkpoint_sequence": int(seed["fresh_checkpoint_sequence"]),
        "targeted_failure_count": int(seed["targeted_failure_count"]),
        "targeted_failure_rate": float(seed["targeted_failure_rate"]),
        "adjudicated_by": seed["adjudicated_by"],
        "child_instantiated": True,
        "automatic_issue_creation": False,
    }


def validate_reopen_cycle_promotion_ledger(ledger: dict[str, Any]) -> None:
    if ledger.get("ledger_version") != REOPEN_CYCLE_PROMOTION_LEDGER_VERSION:
        raise ValueError("unsupported Human remediation reopen cycle promotion ledger version")
    policy = ledger.get("policy")
    required_policy = {
        "explicit_owner_approval_required": True,
        "parent_closed_evidence_required": True,
        "duplicate_cycle_creation_prevented": True,
        "automatic_issue_creation": False,
        "production_code_mutation": False,
        "execution_authorized": False,
    }
    if not isinstance(policy, dict):
        raise ValueError("reopen cycle promotion ledger policy is required")
    for key, expected in required_policy.items():
        if policy.get(key) != expected:
            raise ValueError(f"reopen cycle promotion policy mismatch: {key}")

    rows = ledger.get("promotions")
    if not isinstance(rows, list):
        raise ValueError("reopen cycle promotions must be a list")
    cycle_ids: set[str] = set()
    event_keys: set[str] = set()
    child_fingerprints: set[str] = set()
    child_lifecycle_ids: set[str] = set()
    for sequence, row in enumerate(rows, start=1):
        if not isinstance(row, dict) or row.get("sequence") != sequence:
            raise ValueError("reopen cycle promotion sequence must be contiguous")
        for key in (
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
            "approval_sha256",
        ):
            value = row.get(key)
            if not isinstance(value, str) or not value:
                raise ValueError(f"reopen cycle promotion {key} is required")
        for key in (
            "seed_sha256",
            "parent_proposal_fingerprint",
            "child_proposal_fingerprint",
            "child_proposal_sha256",
            "closure_evidence_key",
            "reopen_event_key",
            "reopen_adjudication_sha256",
            "approval_sha256",
        ):
            if len(row[key]) != 64:
                raise ValueError(f"reopen cycle promotion {key} is invalid")
        if row.get("promotion_version") != REOPEN_CYCLE_PROMOTION_VERSION:
            raise ValueError("reopen cycle promotion version mismatch")
        if row.get("approved") is not True or not isinstance(row.get("approved_by"), str) or not row["approved_by"].strip():
            raise ValueError("reopen cycle promotion requires explicit owner approval")
        if row.get("target_repository") != HUMAN_REMEDIATION_REPOSITORY:
            raise ValueError("reopen cycle promotion target repository mismatch")
        if row.get("child_instantiated") is not True:
            raise ValueError("reopen cycle promotion ledger only stores instantiated child cycles")
        if row.get("automatic_issue_creation") is not False:
            raise ValueError("reopen cycle promotion cannot create GitHub issues automatically")
        if row.get("production_code_mutation") is not False or row.get("execution_authorized") is not False:
            raise ValueError("reopen cycle promotion exceeds authority boundary")
        if int(row.get("targeted_failure_count", 0)) <= 0 or float(row.get("targeted_failure_rate", 0.0)) <= 0.0:
            raise ValueError("reopen cycle promotion requires positive recurrence evidence")
        if row["new_cycle_id"] in cycle_ids or row["reopen_event_key"] in event_keys:
            raise ValueError("duplicate reopened remediation cycle identity")
        if row["child_proposal_fingerprint"] in child_fingerprints or row["child_lifecycle_id"] in child_lifecycle_ids:
            raise ValueError("duplicate reopened child remediation identity")
        cycle_ids.add(row["new_cycle_id"])
        event_keys.add(row["reopen_event_key"])
        child_fingerprints.add(row["child_proposal_fingerprint"])
        child_lifecycle_ids.add(row["child_lifecycle_id"])

        approval_payload = {
            key: value
            for key, value in row.items()
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
        if row["approval_sha256"] != _stable_sha256(approval_payload):
            raise ValueError("reopen cycle promotion approval digest mismatch")


def _find_existing_promotion(
    ledger: dict[str, Any], *, seed: dict[str, Any], child_fingerprint: str
) -> dict[str, Any] | None:
    matches = [
        row
        for row in ledger["promotions"]
        if row["new_cycle_id"] == seed["new_cycle_id"]
        or row["reopen_event_key"] == seed["reopen_event_key"]
        or row["child_proposal_fingerprint"] == child_fingerprint
    ]
    if not matches:
        return None
    first = matches[0]
    if any(item is not first and item != first for item in matches[1:]):
        raise ValueError("reopen cycle promotion ledger contains conflicting identities")
    return first


def _assert_child_matches(record: dict[str, Any], entry: dict[str, Any]) -> None:
    if record.get("proposal_fingerprint") != entry["child_proposal_fingerprint"]:
        raise ValueError("reopen child proposal fingerprint mismatch")
    if record.get("lifecycle_id") != entry["child_lifecycle_id"]:
        raise ValueError("reopen child lifecycle identity mismatch")
    if record.get("proposal_sha256") != entry["child_proposal_sha256"]:
        raise ValueError("reopen child proposal digest mismatch")
    if record.get("origin_kind") != REOPEN_CHILD_ORIGIN:
        raise ValueError("reopen child lifecycle origin mismatch")
    lineage = record.get("lineage")
    if not isinstance(lineage, dict):
        raise ValueError("reopen child lifecycle lineage is missing")
    checks = {
        "new_cycle_id": entry["new_cycle_id"],
        "parent_proposal_fingerprint": entry["parent_proposal_fingerprint"],
        "parent_lifecycle_id": entry["parent_lifecycle_id"],
        "child_proposal_fingerprint": entry["child_proposal_fingerprint"],
        "child_lifecycle_id": entry["child_lifecycle_id"],
        "closure_evidence_key": entry["closure_evidence_key"],
        "reopen_event_key": entry["reopen_event_key"],
        "failure_code": entry["failure_code"],
        "fresh_checkpoint_id": entry["fresh_checkpoint_id"],
        "fresh_checkpoint_sequence": entry["fresh_checkpoint_sequence"],
        "targeted_failure_count": entry["targeted_failure_count"],
        "targeted_failure_rate": entry["targeted_failure_rate"],
        "adjudicated_by": entry["adjudicated_by"],
        "cycle_promoted_by": entry["approved_by"],
    }
    for key, expected in checks.items():
        if lineage.get(key) != expected:
            raise ValueError(f"reopen child lifecycle lineage mismatch: {key}")
    stages = [event.get("stage") for event in record.get("events", [])[:2]]
    if stages != ["DETECTED", "PROPOSED"]:
        raise ValueError("reopen child lifecycle must begin DETECTED then PROPOSED")


def instantiate_reopen_cycle(
    lifecycle: dict[str, Any],
    promotion_ledger: dict[str, Any],
    adjudication_ledger: dict[str, Any],
    closure_ledger: dict[str, Any],
    *,
    parent_fingerprint: str,
    owner: str,
    approved: bool,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    validate_lifecycle(lifecycle)
    validate_reopen_cycle_promotion_ledger(promotion_ledger)
    validate_reopen_adjudication_ledger(adjudication_ledger)
    validate_closure_ledger(closure_ledger)
    owner = owner.strip()
    if not approved:
        raise ValueError("reopen cycle promotion requires explicit owner approval")
    if not owner:
        raise ValueError("reopen cycle promoter identity is required")

    adjudication = _find_adjudication(adjudication_ledger, parent_fingerprint)
    seed = build_new_cycle_seed(adjudication_ledger, fingerprint=parent_fingerprint)
    if seed.get("seed_version") != REOPEN_CYCLE_SEED_VERSION or seed.get("new_cycle_eligible") is not True:
        raise ValueError("LAB #75 reopen cycle seed is not eligible")
    parent = _find_parent(lifecycle, parent_fingerprint)
    closure = _find_closure(closure_ledger, seed)
    if parent.get("issue_number") != seed["issue_number"] or parent.get("issue_url") != seed["issue_url"]:
        raise ValueError("reopen cycle seed and parent lifecycle issue identity mismatch")
    if parent.get("failure_code") != seed["failure_code"]:
        raise ValueError("reopen cycle seed and parent lifecycle failure code mismatch")
    if closure["approval"].get("resolved_checkpoint_id") != seed["prior_resolved_checkpoint_id"]:
        raise ValueError("reopen cycle seed and closure resolved checkpoint mismatch")

    proposal = build_child_proposal(seed)
    child_fingerprint = proposal["proposal_fingerprint"]
    lineage = _lineage(
        seed=seed,
        adjudication=adjudication,
        parent=parent,
        child_fingerprint=child_fingerprint,
        promoted_by=owner,
    )
    entry = _promotion_entry(
        seed=seed,
        adjudication=adjudication,
        parent=parent,
        proposal=proposal,
        lineage=lineage,
        promoted_by=owner,
    )

    existing = _find_existing_promotion(
        promotion_ledger, seed=seed, child_fingerprint=child_fingerprint
    )
    child_existing = next(
        (item for item in lifecycle["records"] if item["proposal_fingerprint"] == child_fingerprint),
        None,
    )
    if existing is not None:
        expected = {key: value for key, value in existing.items() if key != "sequence"}
        if expected != entry:
            raise ValueError("reopen cycle seed already has a conflicting promotion")
        if child_existing is None:
            raise ValueError("reopen cycle promotion ledger references a missing child lifecycle")
        _assert_child_matches(child_existing, existing)
        return lifecycle, promotion_ledger, {
            "result_version": REOPEN_CYCLE_PROMOTION_RESULT_VERSION,
            "status": "UNCHANGED",
            "child_proposal": proposal,
            "promotion": deepcopy(existing),
            "lifecycle_mutated": False,
            "automatic_issue_creation": False,
            "production_code_mutation": False,
            "execution_authorized": False,
        }

    updated_lifecycle = deepcopy(lifecycle)
    if child_existing is not None:
        probe = {"sequence": 1, **entry}
        _assert_child_matches(child_existing, probe)
    else:
        child = _child_record(
            sequence=len(updated_lifecycle["records"]) + 1,
            proposal=proposal,
            lineage=lineage,
        )
        updated_lifecycle["records"].append(child)
    validate_lifecycle(updated_lifecycle)

    updated_ledger = deepcopy(promotion_ledger)
    stored = {"sequence": len(updated_ledger["promotions"]) + 1, **entry}
    updated_ledger["promotions"].append(stored)
    validate_reopen_cycle_promotion_ledger(updated_ledger)
    child_record = next(
        item
        for item in updated_lifecycle["records"]
        if item["proposal_fingerprint"] == child_fingerprint
    )
    _assert_child_matches(child_record, stored)

    return updated_lifecycle, updated_ledger, {
        "result_version": REOPEN_CYCLE_PROMOTION_RESULT_VERSION,
        "status": "APPENDED",
        "child_proposal": proposal,
        "promotion": deepcopy(stored),
        "lifecycle_mutated": child_existing is None,
        "automatic_issue_creation": False,
        "production_code_mutation": False,
        "execution_authorized": False,
    }


def reopen_cycle_summary(
    lifecycle: dict[str, Any], promotion_ledger: dict[str, Any]
) -> dict[str, Any]:
    validate_lifecycle(lifecycle)
    validate_reopen_cycle_promotion_ledger(promotion_ledger)
    lineages: list[dict[str, Any]] = []
    for row in promotion_ledger["promotions"]:
        child = next(
            (
                item
                for item in lifecycle["records"]
                if item["proposal_fingerprint"] == row["child_proposal_fingerprint"]
            ),
            None,
        )
        if child is None:
            raise ValueError("reopen cycle promotion references a missing child lifecycle")
        _assert_child_matches(child, row)
        lineages.append(
            {
                "parent_proposal_fingerprint": row["parent_proposal_fingerprint"],
                "parent_lifecycle_id": row["parent_lifecycle_id"],
                "child_proposal_fingerprint": row["child_proposal_fingerprint"],
                "child_lifecycle_id": row["child_lifecycle_id"],
                "new_cycle_id": row["new_cycle_id"],
                "closure_evidence_key": row["closure_evidence_key"],
                "reopen_event_key": row["reopen_event_key"],
                "failure_code": row["failure_code"],
                "service": row.get("service"),
                "fresh_checkpoint_id": row["fresh_checkpoint_id"],
                "fresh_checkpoint_sequence": row["fresh_checkpoint_sequence"],
                "child_status": child["status"],
                "child_issue_number": child.get("issue_number"),
                "promoted_by": row["approved_by"],
            }
        )
    return {
        "ledger_version": REOPEN_CYCLE_PROMOTION_LEDGER_VERSION,
        "promoted_cycle_count": len(lineages),
        "active_reopened_child_count": sum(1 for item in lineages if item["child_status"] != "RESOLVED"),
        "resolved_reopened_child_count": sum(1 for item in lineages if item["child_status"] == "RESOLVED"),
        "lineages": lineages,
        "explicit_owner_approval_required": True,
        "parent_closed_evidence_required": True,
        "duplicate_cycle_creation_prevented": True,
        "automatic_issue_creation": False,
        "production_code_mutation": False,
        "execution_authorized": False,
    }


def proposal_for_promoted_cycle(
    lifecycle: dict[str, Any], promotion_ledger: dict[str, Any], *, child_fingerprint: str
) -> dict[str, Any]:
    validate_lifecycle(lifecycle)
    validate_reopen_cycle_promotion_ledger(promotion_ledger)
    row = next(
        (
            item
            for item in promotion_ledger["promotions"]
            if item["child_proposal_fingerprint"] == child_fingerprint
        ),
        None,
    )
    if row is None:
        raise ValueError("promoted reopened child cycle was not found")
    seed = {
        "seed_version": REOPEN_CYCLE_SEED_VERSION,
        "new_cycle_id": row["new_cycle_id"],
        "prior_proposal_fingerprint": row["parent_proposal_fingerprint"],
        "reopen_event_key": row["reopen_event_key"],
        "closure_evidence_key": row["closure_evidence_key"],
        "issue_number": row["parent_issue_number"],
        "issue_url": row["parent_issue_url"],
        "failure_code": row["failure_code"],
        "service": row.get("service"),
        "fresh_checkpoint_id": row["fresh_checkpoint_id"],
        "fresh_checkpoint_sequence": row["fresh_checkpoint_sequence"],
        "targeted_failure_count": row["targeted_failure_count"],
        "targeted_failure_rate": row["targeted_failure_rate"],
        "adjudicated_by": row["adjudicated_by"],
        "prior_resolved_checkpoint_id": row["prior_resolved_checkpoint_id"],
        "new_cycle_eligible": True,
        "automatic_new_cycle_creation": False,
        "production_code_mutation": False,
        "execution_authorized": False,
    }
    proposal = build_child_proposal(seed)
    if proposal["proposal_fingerprint"] != child_fingerprint:
        raise ValueError("reopened child proposal regeneration identity mismatch")
    if _stable_sha256(proposal) != row["child_proposal_sha256"]:
        raise ValueError("reopened child proposal regeneration digest mismatch")
    return proposal


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="roberta-eval-human-reopen-cycle")
    parser.add_argument("--ledger", default=None)
    parser.add_argument("--lifecycle", default=None)
    parser.add_argument("--adjudication-ledger", default=None)
    parser.add_argument("--closure-ledger", default=None)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("summary", help="show parent→child reopened remediation lineage")

    promote = sub.add_parser("promote", help="instantiate an eligible LAB #75 reopen seed")
    promote.add_argument("--parent-fingerprint", required=True)
    promote.add_argument("--owner", required=True)
    promote.add_argument("--approve", action="store_true", required=True)

    proposal = sub.add_parser("proposal", help="emit the canonical proposal for a promoted child cycle")
    proposal.add_argument("--child-fingerprint", required=True)

    args = parser.parse_args(argv)
    ledger_path = Path(args.ledger) if args.ledger else default_reopen_cycle_promotion_ledger_path()
    lifecycle_path = Path(args.lifecycle) if args.lifecycle else default_lifecycle_path()
    promotion_ledger = load_reopen_cycle_promotion_ledger(ledger_path)
    lifecycle = load_lifecycle(lifecycle_path)

    if args.command == "summary":
        payload = reopen_cycle_summary(lifecycle, promotion_ledger)
    elif args.command == "proposal":
        payload = proposal_for_promoted_cycle(
            lifecycle,
            promotion_ledger,
            child_fingerprint=args.child_fingerprint,
        )
    else:
        adjudication_ledger = load_reopen_adjudication_ledger(
            Path(args.adjudication_ledger)
            if args.adjudication_ledger
            else default_reopen_adjudication_ledger_path()
        )
        closure_ledger = load_closure_ledger(
            Path(args.closure_ledger) if args.closure_ledger else default_closure_ledger_path()
        )
        updated_lifecycle, updated_ledger, payload = instantiate_reopen_cycle(
            lifecycle,
            promotion_ledger,
            adjudication_ledger,
            closure_ledger,
            parent_fingerprint=args.parent_fingerprint,
            owner=args.owner,
            approved=args.approve,
        )
        # Write lifecycle first. If ledger persistence is interrupted, retry is recoverable:
        # the deterministic child is recognized and the missing ledger entry can be appended.
        if updated_lifecycle != lifecycle:
            write_lifecycle(lifecycle_path, updated_lifecycle)
        if updated_ledger != promotion_ledger:
            write_reopen_cycle_promotion_ledger(ledger_path, updated_ledger)
        payload["summary"] = reopen_cycle_summary(updated_lifecycle, updated_ledger)

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
