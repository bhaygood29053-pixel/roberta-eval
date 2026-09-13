from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from .github_promotion import HUMAN_REMEDIATION_REPOSITORY
from .human_checkpoint_history import (
    default_human_checkpoint_history_path,
    load_human_checkpoint_history,
    validate_human_checkpoint_history,
)
from .human_remediation_lifecycle import (
    default_lifecycle_path,
    load_lifecycle,
    validate_lifecycle,
)
from .human_remediation_promotion import (
    PROMOTION_RESULT_VERSION,
    default_promotion_ledger_path,
    load_promotion_ledger,
    validate_promotion_ledger,
)

ACTION_QUEUE_VERSION = "roberta_human_remediation_action_queue/v1"
APPROVAL_REGISTRY_VERSION = "roberta_human_remediation_approval_registry/v1"
CLOSURE_GATE_VERSION = "roberta_human_remediation_closure_gate/v1"

ACTIONS = (
    "APPROVE_PROPOSAL",
    "CREATE_ISSUE",
    "FIX_ISSUE",
    "ACCEPT_NEW_CHECKPOINT",
    "REPLAY_AGAIN",
    "CLOSE_AS_RESOLVED",
)

ACTION_LABELS = {
    "APPROVE_PROPOSAL": "Approve proposal",
    "CREATE_ISSUE": "Create issue",
    "FIX_ISSUE": "Fix issue",
    "ACCEPT_NEW_CHECKPOINT": "Accept new checkpoint",
    "REPLAY_AGAIN": "Replay again",
    "CLOSE_AS_RESOLVED": "Close as resolved",
}


def default_approval_registry_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "human_remediation_approval_registry.json"


def empty_approval_registry() -> dict[str, Any]:
    return {
        "registry_version": APPROVAL_REGISTRY_VERSION,
        "policy": {
            "source_result": PROMOTION_RESULT_VERSION,
            "accepted_status": "APPROVED_DRY_RUN",
            "issue_created": False,
            "raw_responses_stored": False,
            "proposal_bodies_stored": False,
            "production_code_mutation": False,
            "execution_authorized": False,
        },
        "approvals": [],
    }


def load_approval_registry(path: Path | None = None) -> dict[str, Any]:
    source = path or default_approval_registry_path()
    payload = json.loads(source.read_text(encoding="utf-8"))
    validate_approval_registry(payload)
    return payload


def write_approval_registry(path: Path, registry: dict[str, Any]) -> None:
    validate_approval_registry(registry)
    path.write_text(json.dumps(registry, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def validate_approval_registry(registry: dict[str, Any]) -> None:
    if registry.get("registry_version") != APPROVAL_REGISTRY_VERSION:
        raise ValueError("unsupported Human remediation approval registry version")
    policy = registry.get("policy")
    if not isinstance(policy, dict):
        raise ValueError("Human remediation approval registry policy is required")
    required = {
        "source_result": PROMOTION_RESULT_VERSION,
        "accepted_status": "APPROVED_DRY_RUN",
        "issue_created": False,
        "raw_responses_stored": False,
        "proposal_bodies_stored": False,
        "production_code_mutation": False,
        "execution_authorized": False,
    }
    for key, expected in required.items():
        if policy.get(key) != expected:
            raise ValueError(f"Human remediation approval policy mismatch: {key}")
    approvals = registry.get("approvals")
    if not isinstance(approvals, list):
        raise ValueError("Human remediation approvals must be a list")
    fingerprints: set[str] = set()
    evidence_keys: set[str] = set()
    for index, approval in enumerate(approvals, start=1):
        if not isinstance(approval, dict):
            raise ValueError("Human remediation approval entry must be an object")
        if approval.get("sequence") != index:
            raise ValueError("Human remediation approval sequence must be contiguous")
        fingerprint = approval.get("proposal_fingerprint")
        evidence_key = approval.get("evidence_key")
        if not isinstance(fingerprint, str) or len(fingerprint) != 64:
            raise ValueError("Human remediation approval fingerprint is invalid")
        if not isinstance(evidence_key, str) or len(evidence_key) != 64:
            raise ValueError("Human remediation approval evidence_key is invalid")
        if fingerprint in fingerprints:
            raise ValueError("duplicate Human remediation approval fingerprint")
        if evidence_key in evidence_keys:
            raise ValueError("duplicate Human remediation approval evidence key")
        fingerprints.add(fingerprint)
        evidence_keys.add(evidence_key)
        if approval.get("approved") is not True:
            raise ValueError("Human remediation approval must be approved")
        if approval.get("target_repository") != HUMAN_REMEDIATION_REPOSITORY:
            raise ValueError("Human remediation approval target repository mismatch")
        if not isinstance(approval.get("approved_by"), str) or not approval["approved_by"].strip():
            raise ValueError("Human remediation approval reviewer is required")
        for key in ("proposal_sha256", "previous_snapshot_id", "current_snapshot_id", "failure_code", "recurrence"):
            if not isinstance(approval.get(key), str) or not approval[key]:
                raise ValueError(f"Human remediation approval {key} is required")
        if approval.get("production_code_mutation") is not False:
            raise ValueError("Human remediation approval cannot authorize production mutation")
        if approval.get("execution_authorized") is not False:
            raise ValueError("Human remediation approval cannot authorize execution")


def _normalize_approval_result(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("promotion_result_version") != PROMOTION_RESULT_VERSION:
        raise ValueError("unsupported Human remediation promotion result version")
    if result.get("status") != "APPROVED_DRY_RUN":
        raise ValueError("only APPROVED_DRY_RUN promotion results can be registered as approval evidence")
    if result.get("issue_created") is not False:
        raise ValueError("approval dry-run result cannot already contain a created issue")
    approval = result.get("approval")
    if not isinstance(approval, dict) or approval.get("approved") is not True:
        raise ValueError("approved Human remediation receipt is required")
    if approval.get("target_repository") != HUMAN_REMEDIATION_REPOSITORY:
        raise ValueError("Human remediation approval target repository mismatch")
    entry = {
        "proposal_fingerprint": approval.get("proposal_fingerprint"),
        "proposal_sha256": approval.get("proposal_sha256"),
        "evidence_key": approval.get("evidence_key"),
        "approved": True,
        "approved_by": approval.get("approved_by"),
        "target_repository": approval.get("target_repository"),
        "previous_snapshot_id": approval.get("previous_snapshot_id"),
        "current_snapshot_id": approval.get("current_snapshot_id"),
        "failure_code": approval.get("failure_code"),
        "recurrence": approval.get("recurrence"),
        "service": approval.get("service"),
        "production_code_mutation": False,
        "execution_authorized": False,
    }
    trial = empty_approval_registry()
    trial["approvals"] = [{"sequence": 1, **entry}]
    validate_approval_registry(trial)
    return entry


def register_approval_result(
    registry: dict[str, Any],
    result: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    validate_approval_registry(registry)
    entry = _normalize_approval_result(result)
    by_fingerprint = next(
        (item for item in registry["approvals"] if item["proposal_fingerprint"] == entry["proposal_fingerprint"]),
        None,
    )
    by_evidence = next(
        (item for item in registry["approvals"] if item["evidence_key"] == entry["evidence_key"]),
        None,
    )
    existing = by_fingerprint or by_evidence
    if by_fingerprint and by_evidence and by_fingerprint is not by_evidence:
        raise ValueError("Human remediation approval registry contains conflicting identity")
    if existing is not None:
        expected = {key: value for key, value in existing.items() if key != "sequence"}
        if expected == entry:
            return registry, "UNCHANGED"
        raise ValueError("Human remediation approval identity conflicts with existing evidence")
    updated = deepcopy(registry)
    updated["approvals"].append({"sequence": len(updated["approvals"]) + 1, **entry})
    validate_approval_registry(updated)
    return updated, "APPENDED"


def _approval_by_fingerprint(registry: dict[str, Any], fingerprint: str) -> dict[str, Any] | None:
    return next(
        (item for item in registry["approvals"] if item["proposal_fingerprint"] == fingerprint),
        None,
    )


def _promotion_by_fingerprint(ledger: dict[str, Any], fingerprint: str) -> dict[str, Any] | None:
    return next(
        (item for item in ledger["promotions"] if item["proposal_fingerprint"] == fingerprint),
        None,
    )


def _latest_checkpoint_sequence(history: dict[str, Any]) -> int:
    if not history["checkpoints"]:
        return 0
    return int(history["checkpoints"][-1]["sequence"])


def _issue_identity(record: dict[str, Any], promotion: dict[str, Any] | None) -> tuple[int | None, str | None]:
    lifecycle_number = record.get("issue_number")
    lifecycle_url = record.get("issue_url")
    if promotion is None:
        return lifecycle_number, lifecycle_url
    promoted_number = promotion.get("issue_number")
    promoted_url = promotion.get("issue_url")
    if lifecycle_number is not None and lifecycle_number != promoted_number:
        raise ValueError("Human remediation action queue issue identity conflict")
    if lifecycle_url is not None and lifecycle_url != promoted_url:
        raise ValueError("Human remediation action queue issue URL conflict")
    return promoted_number or lifecycle_number, promoted_url or lifecycle_url


def _next_action_for_record(
    record: dict[str, Any],
    *,
    checkpoint_history: dict[str, Any],
    approval: dict[str, Any] | None,
    promotion: dict[str, Any] | None,
) -> dict[str, Any]:
    fingerprint = record["proposal_fingerprint"]
    if approval is not None:
        if approval["proposal_sha256"] != record["proposal_sha256"]:
            raise ValueError("approval/action queue proposal digest mismatch")
        if approval["current_snapshot_id"] != record["current_snapshot_id"]:
            raise ValueError("approval/action queue checkpoint mismatch")
        if approval["failure_code"] != record["failure_code"]:
            raise ValueError("approval/action queue failure code mismatch")
    if promotion is not None:
        approval_receipt = promotion.get("approval") or {}
        if approval_receipt.get("proposal_sha256") != record["proposal_sha256"]:
            raise ValueError("promotion/action queue proposal digest mismatch")

    issue_number, issue_url = _issue_identity(record, promotion)
    lifecycle_status = record["status"]
    latest_checkpoint_sequence = _latest_checkpoint_sequence(checkpoint_history)
    latest_verification_sequence = (
        int(record["verifications"][-1]["checkpoint_sequence"])
        if record.get("verifications")
        else None
    )
    fix = record.get("fix")

    if lifecycle_status == "RESOLVED":
        action = "CLOSE_AS_RESOLVED"
        effective_stage = "RESOLVED"
        reason = "A later accepted post-fix checkpoint proved the targeted Human-language defect is absent."
    elif issue_number is not None:
        if fix is None:
            action = "FIX_ISSUE"
            effective_stage = "GITHUB_ISSUE"
            reason = "The remediation issue exists, but no merged-fix evidence has been recorded."
        else:
            floor = int(fix["verification_checkpoint_sequence_floor"])
            comparison_floor = latest_verification_sequence if latest_verification_sequence is not None else floor
            if latest_checkpoint_sequence > comparison_floor:
                action = "REPLAY_AGAIN"
                effective_stage = lifecycle_status
                reason = "A newer accepted Human checkpoint is available and must be replay-verified against this remediation."
            else:
                action = "ACCEPT_NEW_CHECKPOINT"
                effective_stage = lifecycle_status
                reason = "No accepted Human checkpoint newer than the latest required verification boundary is available."
    elif approval is not None or lifecycle_status == "APPROVED":
        action = "CREATE_ISSUE"
        effective_stage = "APPROVED"
        reason = "The proposal has explicit approval evidence, but no promoted GitHub issue exists yet."
    else:
        action = "APPROVE_PROPOSAL"
        effective_stage = lifecycle_status if lifecycle_status in {"DETECTED", "PROPOSED"} else "PROPOSED"
        reason = "The Human remediation proposal is registered but has no explicit approval evidence."

    if action not in ACTIONS:
        raise ValueError("unsupported Human remediation next action")
    closure_ready = action == "CLOSE_AS_RESOLVED" and lifecycle_status == "RESOLVED" and issue_number is not None
    return {
        "proposal_fingerprint": fingerprint,
        "failure_code": record["failure_code"],
        "service": record.get("service"),
        "lifecycle_status": lifecycle_status,
        "effective_stage": effective_stage,
        "next_action": action,
        "next_action_label": ACTION_LABELS[action],
        "reason": reason,
        "issue_number": issue_number,
        "issue_url": issue_url,
        "latest_checkpoint_sequence": latest_checkpoint_sequence,
        "latest_verification_sequence": latest_verification_sequence,
        "closure_ready": closure_ready,
        "production_code_mutation": False,
        "execution_authorized": False,
    }


def build_action_queue(
    lifecycle: dict[str, Any],
    checkpoint_history: dict[str, Any],
    approval_registry: dict[str, Any],
    promotion_ledger: dict[str, Any],
) -> dict[str, Any]:
    validate_lifecycle(lifecycle)
    validate_human_checkpoint_history(checkpoint_history)
    validate_approval_registry(approval_registry)
    validate_promotion_ledger(promotion_ledger)
    items = []
    for record in lifecycle["records"]:
        fingerprint = record["proposal_fingerprint"]
        items.append(
            _next_action_for_record(
                record,
                checkpoint_history=checkpoint_history,
                approval=_approval_by_fingerprint(approval_registry, fingerprint),
                promotion=_promotion_by_fingerprint(promotion_ledger, fingerprint),
            )
        )
    action_counts = {action: 0 for action in ACTIONS}
    for item in items:
        action_counts[item["next_action"]] += 1
    return {
        "action_queue_version": ACTION_QUEUE_VERSION,
        "record_count": len(items),
        "active_count": sum(1 for item in items if item["lifecycle_status"] != "RESOLVED"),
        "closure_ready_count": sum(1 for item in items if item["closure_ready"]),
        "action_counts": action_counts,
        "items": items,
        "deterministic": True,
        "read_only": True,
        "ai_judge_used": False,
        "judge_model_calls": 0,
        "external_calls": 0,
        "zero_judge_tokens": True,
        "auto_close_issue": False,
        "production_code_mutation": False,
        "execution_authorized": False,
    }


def closure_gate(
    lifecycle: dict[str, Any],
    checkpoint_history: dict[str, Any],
    approval_registry: dict[str, Any],
    promotion_ledger: dict[str, Any],
    *,
    fingerprint: str,
) -> dict[str, Any]:
    queue = build_action_queue(lifecycle, checkpoint_history, approval_registry, promotion_ledger)
    item = next((row for row in queue["items"] if row["proposal_fingerprint"] == fingerprint), None)
    if item is None:
        raise ValueError("Human remediation lifecycle record not found")
    ready = bool(item["closure_ready"])
    blockers: list[str] = []
    if item["lifecycle_status"] != "RESOLVED":
        blockers.append(f"lifecycle_status={item['lifecycle_status']} is not RESOLVED")
    if item["issue_number"] is None:
        blockers.append("no promoted GitHub issue identity is present")
    return {
        "closure_gate_version": CLOSURE_GATE_VERSION,
        "proposal_fingerprint": fingerprint,
        "status": "READY_TO_CLOSE" if ready else "BLOCKED",
        "closure_ready": ready,
        "issue_number": item["issue_number"],
        "issue_url": item["issue_url"],
        "lifecycle_status": item["lifecycle_status"],
        "next_action": item["next_action"],
        "next_action_label": item["next_action_label"],
        "blockers": blockers,
        "auto_close_issue": False,
        "read_only": True,
        "production_code_mutation": False,
        "execution_authorized": False,
    }


def _load_result(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Human remediation promotion result must be a JSON object")
    return payload


def _paths(args: argparse.Namespace) -> tuple[Path, Path, Path, Path]:
    return (
        Path(args.lifecycle) if args.lifecycle else default_lifecycle_path(),
        Path(args.checkpoint_history) if args.checkpoint_history else default_human_checkpoint_history_path(),
        Path(args.approval_registry) if args.approval_registry else default_approval_registry_path(),
        Path(args.promotion_ledger) if args.promotion_ledger else default_promotion_ledger_path(),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="roberta-eval-human-actions")
    parser.add_argument("--lifecycle", default=None)
    parser.add_argument("--checkpoint-history", default=None)
    parser.add_argument("--approval-registry", default=None)
    parser.add_argument("--promotion-ledger", default=None)
    subparsers = parser.add_subparsers(dest="command", required=True)

    record = subparsers.add_parser("record-approval", help="persist an APPROVED_DRY_RUN receipt")
    record.add_argument("--result", required=True)

    subparsers.add_parser("queue", help="show the exact next Human remediation action for every record")

    closure = subparsers.add_parser("closure-check", help="check whether a remediation issue is ready to close")
    closure.add_argument("--fingerprint", required=True)

    args = parser.parse_args(argv)
    lifecycle_path, history_path, approval_path, promotion_path = _paths(args)

    if args.command == "record-approval":
        registry = load_approval_registry(approval_path)
        updated, status = register_approval_result(registry, _load_result(Path(args.result)))
        if updated != registry:
            write_approval_registry(approval_path, updated)
        payload = {
            "operation": "record-approval",
            "status": status,
            "approval_count": len(updated["approvals"]),
            "production_code_mutation": False,
            "execution_authorized": False,
        }
    else:
        lifecycle = load_lifecycle(lifecycle_path)
        history = load_human_checkpoint_history(history_path)
        approvals = load_approval_registry(approval_path)
        promotions = load_promotion_ledger(promotion_path)
        if args.command == "queue":
            payload = build_action_queue(lifecycle, history, approvals, promotions)
        else:
            payload = closure_gate(
                lifecycle,
                history,
                approvals,
                promotions,
                fingerprint=args.fingerprint,
            )

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
