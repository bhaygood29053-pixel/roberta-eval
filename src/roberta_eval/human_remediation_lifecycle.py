from __future__ import annotations

import argparse
import hashlib
import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

from .github_promotion import HUMAN_REMEDIATION_REPOSITORY, load_jsonl
from .human_checkpoint_history import (
    load_human_checkpoint_history,
    validate_human_checkpoint_history,
)
from .human_remediation_promotion import (
    load_promotion_ledger,
    validate_human_remediation_proposal,
    validate_promotion_ledger,
)

LIFECYCLE_VERSION = "roberta_human_remediation_lifecycle/v1"

STAGES = (
    "DETECTED",
    "PROPOSED",
    "APPROVED",
    "GITHUB_ISSUE",
    "FIX_MERGED",
    "REPLAY_VERIFIED",
    "IMPROVED",
    "RESOLVED",
)


def default_lifecycle_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "human_remediation_lifecycle.json"


def empty_lifecycle() -> dict[str, Any]:
    return {
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
        "records": [],
    }


def load_lifecycle(path: Path | None = None) -> dict[str, Any]:
    source = path or default_lifecycle_path()
    lifecycle = json.loads(source.read_text(encoding="utf-8"))
    validate_lifecycle(lifecycle)
    return lifecycle


def write_lifecycle(path: Path, lifecycle: dict[str, Any]) -> None:
    validate_lifecycle(lifecycle)
    path.write_text(json.dumps(lifecycle, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _stable_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _proposal_digest(proposal: dict[str, Any]) -> str:
    return _stable_sha256(proposal)


def _event(kind: str, evidence: dict[str, Any]) -> dict[str, Any]:
    if kind not in STAGES:
        raise ValueError(f"unsupported Human remediation lifecycle stage: {kind}")
    return {"stage": kind, "evidence": deepcopy(evidence)}


def _append_event(record: dict[str, Any], kind: str, evidence: dict[str, Any]) -> None:
    entry = _event(kind, evidence)
    entry["sequence"] = len(record["events"]) + 1
    record["events"].append(entry)


def _find_record(lifecycle: dict[str, Any], fingerprint: str) -> dict[str, Any] | None:
    return next(
        (item for item in lifecycle["records"] if item["proposal_fingerprint"] == fingerprint),
        None,
    )


def _checkpoint_by_id(history: dict[str, Any], checkpoint_id: str) -> dict[str, Any]:
    for checkpoint in history["checkpoints"]:
        if checkpoint["checkpoint_id"] == checkpoint_id:
            return checkpoint
    raise ValueError(f"accepted Human checkpoint not found: {checkpoint_id}")


def validate_lifecycle(lifecycle: dict[str, Any]) -> None:
    if lifecycle.get("lifecycle_version") != LIFECYCLE_VERSION:
        raise ValueError("unsupported Human remediation lifecycle version")
    policy = lifecycle.get("policy")
    if not isinstance(policy, dict):
        raise ValueError("Human remediation lifecycle policy is required")
    required_policy = {
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
    }
    for key, expected in required_policy.items():
        if policy.get(key) != expected:
            raise ValueError(f"Human remediation lifecycle policy mismatch: {key}")

    records = lifecycle.get("records")
    if not isinstance(records, list):
        raise ValueError("Human remediation lifecycle records must be a list")

    fingerprints: set[str] = set()
    lifecycle_ids: set[str] = set()
    issue_ids: set[tuple[str, int]] = set()
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            raise ValueError("Human remediation lifecycle record must be an object")
        if record.get("sequence") != index:
            raise ValueError("Human remediation lifecycle record sequence must be contiguous")
        lifecycle_id = record.get("lifecycle_id")
        fingerprint = record.get("proposal_fingerprint")
        if not isinstance(lifecycle_id, str) or not lifecycle_id:
            raise ValueError("Human remediation lifecycle_id is required")
        if lifecycle_id in lifecycle_ids:
            raise ValueError("duplicate Human remediation lifecycle_id")
        lifecycle_ids.add(lifecycle_id)
        if not isinstance(fingerprint, str) or len(fingerprint) != 64:
            raise ValueError("Human remediation lifecycle proposal fingerprint is invalid")
        if fingerprint in fingerprints:
            raise ValueError("duplicate Human remediation proposal fingerprint in lifecycle")
        fingerprints.add(fingerprint)
        if record.get("target_repository") != HUMAN_REMEDIATION_REPOSITORY:
            raise ValueError("Human remediation lifecycle target repository mismatch")
        if record.get("status") not in STAGES:
            raise ValueError("Human remediation lifecycle status is invalid")
        for key in ("previous_snapshot_id", "current_snapshot_id", "failure_code"):
            if not isinstance(record.get(key), str) or not record[key]:
                raise ValueError(f"Human remediation lifecycle {key} is required")
        baseline_count = record.get("baseline_count")
        baseline_rate = record.get("baseline_rate")
        if not isinstance(baseline_count, int) or baseline_count <= 0:
            raise ValueError("Human remediation lifecycle baseline_count must be positive")
        if not isinstance(baseline_rate, (int, float)) or not (0 < float(baseline_rate) <= 1):
            raise ValueError("Human remediation lifecycle baseline_rate must be in (0, 1]")
        events = record.get("events")
        if not isinstance(events, list) or len(events) < 2:
            raise ValueError("Human remediation lifecycle requires DETECTED/PROPOSED events")
        if [events[0].get("stage"), events[1].get("stage")] != ["DETECTED", "PROPOSED"]:
            raise ValueError("Human remediation lifecycle must begin DETECTED then PROPOSED")
        for event_index, event in enumerate(events, start=1):
            if event.get("sequence") != event_index:
                raise ValueError("Human remediation event sequence must be contiguous")
            if event.get("stage") not in STAGES:
                raise ValueError("Human remediation event stage is invalid")
            if not isinstance(event.get("evidence"), dict):
                raise ValueError("Human remediation event evidence is required")

        issue_number = record.get("issue_number")
        issue_url = record.get("issue_url")
        if issue_number is not None:
            if not isinstance(issue_number, int) or issue_number <= 0:
                raise ValueError("Human remediation lifecycle issue_number is invalid")
            if not isinstance(issue_url, str) or not issue_url.startswith("https://github.com/"):
                raise ValueError("Human remediation lifecycle issue_url is invalid")
            issue_identity = (HUMAN_REMEDIATION_REPOSITORY, issue_number)
            if issue_identity in issue_ids:
                raise ValueError("duplicate Human remediation GitHub issue identity")
            issue_ids.add(issue_identity)
        elif issue_url is not None:
            raise ValueError("Human remediation issue_url requires issue_number")

        fix = record.get("fix")
        if fix is not None:
            if not isinstance(fix, dict):
                raise ValueError("Human remediation fix evidence must be an object")
            if fix.get("repository") != HUMAN_REMEDIATION_REPOSITORY:
                raise ValueError("Human remediation fix repository mismatch")
            if not isinstance(fix.get("pr_number"), int) or fix["pr_number"] <= 0:
                raise ValueError("Human remediation fix PR number is invalid")
            if not isinstance(fix.get("merge_sha"), str) or not re.fullmatch(r"[0-9a-fA-F]{40}", fix["merge_sha"]):
                raise ValueError("Human remediation fix merge SHA is invalid")
            if not isinstance(fix.get("verified_by"), str) or not fix["verified_by"].strip():
                raise ValueError("Human remediation fix verifier is required")
            floor = fix.get("verification_checkpoint_sequence_floor")
            if not isinstance(floor, int) or floor < 0:
                raise ValueError("Human remediation verification checkpoint floor is invalid")

        verifications = record.get("verifications", [])
        if not isinstance(verifications, list):
            raise ValueError("Human remediation verifications must be a list")
        last_sequence = 0
        ids: set[str] = set()
        for verification in verifications:
            checkpoint_id = verification.get("checkpoint_id")
            checkpoint_sequence = verification.get("checkpoint_sequence")
            if not isinstance(checkpoint_id, str) or not checkpoint_id:
                raise ValueError("Human remediation verification checkpoint_id is required")
            if checkpoint_id in ids:
                raise ValueError("duplicate Human remediation verification checkpoint")
            ids.add(checkpoint_id)
            if not isinstance(checkpoint_sequence, int) or checkpoint_sequence <= last_sequence:
                raise ValueError("Human remediation verification sequence must increase")
            last_sequence = checkpoint_sequence
            if verification.get("outcome") not in {"REPLAY_VERIFIED", "IMPROVED", "RESOLVED"}:
                raise ValueError("Human remediation verification outcome is invalid")
            count = verification.get("targeted_failure_count")
            rate = verification.get("targeted_failure_rate")
            if not isinstance(count, int) or count < 0:
                raise ValueError("Human remediation verification count is invalid")
            if not isinstance(rate, (int, float)) or not (0 <= float(rate) <= 1):
                raise ValueError("Human remediation verification rate is invalid")

        if record.get("production_code_mutation") is not False:
            raise ValueError("Human remediation lifecycle cannot authorize production mutation")
        if record.get("execution_authorized") is not False:
            raise ValueError("Human remediation lifecycle cannot authorize execution")


def register_proposals(
    lifecycle: dict[str, Any],
    proposals: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, int]]:
    validate_lifecycle(lifecycle)
    updated = deepcopy(lifecycle)
    appended = 0
    unchanged = 0
    for proposal in proposals:
        if proposal.get("proposal_kind") != "human_language_remediation":
            continue
        validate_human_remediation_proposal(proposal)
        fingerprint = proposal["proposal_fingerprint"]
        digest = _proposal_digest(proposal)
        existing = _find_record(updated, fingerprint)
        if existing is not None:
            if existing["proposal_sha256"] != digest:
                raise ValueError("existing lifecycle fingerprint conflicts with proposal content")
            unchanged += 1
            continue
        priority = proposal["human_priority"]
        evidence = {
            "proposal_fingerprint": fingerprint,
            "previous_snapshot_id": proposal["previous_snapshot_id"],
            "current_snapshot_id": proposal["current_snapshot_id"],
            "failure_code": priority["failure_code"],
            "service": priority.get("service"),
            "baseline_count": int(priority["current_count"]),
            "baseline_rate": float(priority["current_rate"]),
        }
        record = {
            "sequence": len(updated["records"]) + 1,
            "lifecycle_id": f"human-remediation::{fingerprint}",
            "proposal_fingerprint": fingerprint,
            "proposal_sha256": digest,
            "target_repository": HUMAN_REMEDIATION_REPOSITORY,
            "previous_snapshot_id": proposal["previous_snapshot_id"],
            "current_snapshot_id": proposal["current_snapshot_id"],
            "failure_code": str(priority["failure_code"]),
            "recurrence": str(priority["recurrence"]),
            "service": priority.get("service"),
            "baseline_count": int(priority["current_count"]),
            "baseline_rate": float(priority["current_rate"]),
            "status": "PROPOSED",
            "issue_number": None,
            "issue_url": None,
            "fix": None,
            "verifications": [],
            "events": [],
            "production_code_mutation": False,
            "execution_authorized": False,
        }
        _append_event(record, "DETECTED", evidence)
        _append_event(record, "PROPOSED", {**evidence, "proposal_sha256": digest})
        updated["records"].append(record)
        appended += 1
    validate_lifecycle(updated)
    return updated, {"appended": appended, "unchanged": unchanged}


def sync_promotion_ledger(
    lifecycle: dict[str, Any],
    promotion_ledger: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, int]]:
    validate_lifecycle(lifecycle)
    validate_promotion_ledger(promotion_ledger)
    updated = deepcopy(lifecycle)
    advanced = 0
    unchanged = 0
    unmatched = 0
    for promotion in promotion_ledger["promotions"]:
        fingerprint = promotion["proposal_fingerprint"]
        record = _find_record(updated, fingerprint)
        if record is None:
            unmatched += 1
            continue
        approval = promotion["approval"]
        if approval.get("proposal_sha256") != record["proposal_sha256"]:
            raise ValueError("promotion/lifecycle proposal digest mismatch")
        if approval.get("current_snapshot_id") != record["current_snapshot_id"]:
            raise ValueError("promotion/lifecycle current checkpoint mismatch")
        if approval.get("failure_code") != record["failure_code"]:
            raise ValueError("promotion/lifecycle failure code mismatch")
        stages = [event["stage"] for event in record["events"]]
        changed = False
        if "APPROVED" not in stages:
            _append_event(
                record,
                "APPROVED",
                {
                    "approved_by": approval["approved_by"],
                    "evidence_key": promotion["evidence_key"],
                    "proposal_fingerprint": fingerprint,
                },
            )
            changed = True
        if "GITHUB_ISSUE" not in stages:
            _append_event(
                record,
                "GITHUB_ISSUE",
                {
                    "repository": promotion["target_repository"],
                    "issue_number": promotion["issue_number"],
                    "issue_url": promotion["issue_url"],
                },
            )
            changed = True
        if record["issue_number"] is not None and record["issue_number"] != promotion["issue_number"]:
            raise ValueError("lifecycle promotion issue identity conflict")
        record["issue_number"] = promotion["issue_number"]
        record["issue_url"] = promotion["issue_url"]
        if record["status"] in {"PROPOSED", "APPROVED", "GITHUB_ISSUE"}:
            record["status"] = "GITHUB_ISSUE"
        if changed:
            advanced += 1
        else:
            unchanged += 1
    validate_lifecycle(updated)
    return updated, {"advanced": advanced, "unchanged": unchanged, "unmatched": unmatched}


def record_fix_merged(
    lifecycle: dict[str, Any],
    checkpoint_history: dict[str, Any],
    *,
    fingerprint: str,
    repository: str,
    pr_number: int,
    merge_sha: str,
    verified_by: str,
) -> tuple[dict[str, Any], str]:
    validate_lifecycle(lifecycle)
    validate_human_checkpoint_history(checkpoint_history)
    updated = deepcopy(lifecycle)
    record = _find_record(updated, fingerprint)
    if record is None:
        raise ValueError("Human remediation lifecycle record not found")
    if record["issue_number"] is None:
        raise ValueError("FIX_MERGED requires a promoted GitHub issue")
    if repository != HUMAN_REMEDIATION_REPOSITORY:
        raise ValueError("Human remediation fix repository is not allowed")
    if not isinstance(pr_number, int) or pr_number <= 0:
        raise ValueError("fix PR number must be positive")
    if not re.fullmatch(r"[0-9a-fA-F]{40}", merge_sha):
        raise ValueError("fix merge SHA must be a 40-character hexadecimal commit SHA")
    verified_by = verified_by.strip()
    if not verified_by:
        raise ValueError("fix verifier is required")
    floor = len(checkpoint_history["checkpoints"])
    latest_checkpoint_id = (
        checkpoint_history["checkpoints"][-1]["checkpoint_id"]
        if checkpoint_history["checkpoints"]
        else None
    )
    fix = {
        "repository": repository,
        "pr_number": pr_number,
        "merge_sha": merge_sha.lower(),
        "verified_by": verified_by,
        "verification_checkpoint_sequence_floor": floor,
        "latest_checkpoint_at_fix": latest_checkpoint_id,
    }
    if record["fix"] is not None:
        if record["fix"] == fix:
            return lifecycle, "UNCHANGED"
        raise ValueError("Human remediation fix evidence is immutable once recorded")
    record["fix"] = fix
    record["status"] = "FIX_MERGED"
    _append_event(record, "FIX_MERGED", fix)
    validate_lifecycle(updated)
    return updated, "APPENDED"


def verify_replay(
    lifecycle: dict[str, Any],
    checkpoint_history: dict[str, Any],
    *,
    fingerprint: str,
    checkpoint_id: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    validate_lifecycle(lifecycle)
    validate_human_checkpoint_history(checkpoint_history)
    updated = deepcopy(lifecycle)
    record = _find_record(updated, fingerprint)
    if record is None:
        raise ValueError("Human remediation lifecycle record not found")
    if record["fix"] is None:
        raise ValueError("replay verification requires FIX_MERGED evidence")
    if record["status"] == "RESOLVED":
        return lifecycle, {
            "status": "UNCHANGED",
            "outcome": "RESOLVED",
            "checkpoint_id": record["verifications"][-1]["checkpoint_id"],
        }
    if not checkpoint_history["checkpoints"]:
        raise ValueError("no accepted Human checkpoint is available for replay verification")
    candidate = (
        _checkpoint_by_id(checkpoint_history, checkpoint_id)
        if checkpoint_id
        else checkpoint_history["checkpoints"][-1]
    )
    floor = int(record["fix"]["verification_checkpoint_sequence_floor"])
    if candidate["sequence"] <= floor:
        raise ValueError("replay verification checkpoint must be accepted after FIX_MERGED")
    if record["verifications"] and candidate["sequence"] <= record["verifications"][-1]["checkpoint_sequence"]:
        raise ValueError("replay verification checkpoint must be newer than the prior verification")

    failure = candidate["snapshot"].get("failure_codes", {}).get(
        record["failure_code"],
        {"count": 0, "rate": 0.0},
    )
    count = int(failure.get("count", 0))
    rate = float(failure.get("rate", 0.0))
    if count == 0:
        outcome = "RESOLVED"
    elif rate < float(record["baseline_rate"]):
        outcome = "IMPROVED"
    else:
        outcome = "REPLAY_VERIFIED"

    verification = {
        "checkpoint_id": candidate["checkpoint_id"],
        "checkpoint_sequence": candidate["sequence"],
        "targeted_failure_count": count,
        "targeted_failure_rate": rate,
        "baseline_failure_count": record["baseline_count"],
        "baseline_failure_rate": record["baseline_rate"],
        "outcome": outcome,
        "zero_judge_tokens": True,
    }
    record["verifications"].append(verification)
    _append_event(record, "REPLAY_VERIFIED", verification)
    if outcome in {"IMPROVED", "RESOLVED"}:
        _append_event(record, outcome, verification)
    record["status"] = outcome
    validate_lifecycle(updated)
    return updated, {"status": "APPENDED", **verification}


def lifecycle_summary(lifecycle: dict[str, Any]) -> dict[str, Any]:
    validate_lifecycle(lifecycle)
    records = lifecycle["records"]
    counts = {stage: 0 for stage in STAGES}
    for record in records:
        counts[record["status"]] += 1
    active = [record for record in records if record["status"] != "RESOLVED"]
    verified = [
        record
        for record in records
        if record["status"] in {"REPLAY_VERIFIED", "IMPROVED", "RESOLVED"}
    ]
    return {
        "lifecycle_version": LIFECYCLE_VERSION,
        "record_count": len(records),
        "status_counts": counts,
        "active_count": len(active),
        "verified_count": len(verified),
        "improved_count": counts["IMPROVED"],
        "resolved_count": counts["RESOLVED"],
        "active": [
            {
                "proposal_fingerprint": record["proposal_fingerprint"],
                "failure_code": record["failure_code"],
                "service": record.get("service"),
                "status": record["status"],
                "issue_number": record.get("issue_number"),
                "baseline_rate": record["baseline_rate"],
                "latest_verification": (
                    deepcopy(record["verifications"][-1]) if record["verifications"] else None
                ),
            }
            for record in active[:10]
        ],
        "raw_responses_stored": False,
        "proposal_bodies_stored": False,
        "ai_judge_used": False,
        "judge_model_calls": 0,
        "external_calls": 0,
        "zero_judge_tokens": True,
        "production_code_mutation": False,
        "execution_authorized": False,
    }


def _save_if_changed(path: Path, before: dict[str, Any], after: dict[str, Any]) -> None:
    if before != after:
        write_lifecycle(path, after)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="roberta-eval-human-lifecycle")
    parser.add_argument("--ledger", default=None, help="optional Human remediation lifecycle JSON path")
    subparsers = parser.add_subparsers(dest="command", required=True)

    register = subparsers.add_parser("register", help="register Human remediation proposal(s)")
    register.add_argument("--proposals", required=True)

    sync = subparsers.add_parser("sync-promotion", help="sync accepted promotion evidence")
    sync.add_argument("--promotion-ledger", default=None)

    fix = subparsers.add_parser("record-fix", help="record verified merged fix evidence")
    fix.add_argument("--fingerprint", required=True)
    fix.add_argument("--repository", default=HUMAN_REMEDIATION_REPOSITORY)
    fix.add_argument("--pr-number", type=int, required=True)
    fix.add_argument("--merge-sha", required=True)
    fix.add_argument("--verified-by", required=True)
    fix.add_argument("--checkpoint-history", default=None)

    verify = subparsers.add_parser("verify-replay", help="verify a later accepted checkpoint")
    verify.add_argument("--fingerprint", required=True)
    verify.add_argument("--checkpoint-id", default=None)
    verify.add_argument("--checkpoint-history", default=None)

    subparsers.add_parser("summary", help="summarize Human remediation lifecycle")
    args = parser.parse_args(argv)

    path = Path(args.ledger) if args.ledger else default_lifecycle_path()
    lifecycle = load_lifecycle(path)

    if args.command == "register":
        proposals = load_jsonl(Path(args.proposals))
        updated, result = register_proposals(lifecycle, proposals)
        _save_if_changed(path, lifecycle, updated)
        payload = {"operation": "register", **result, "lifecycle": lifecycle_summary(updated)}
    elif args.command == "sync-promotion":
        promotion = load_promotion_ledger(
            Path(args.promotion_ledger) if args.promotion_ledger else None
        )
        updated, result = sync_promotion_ledger(lifecycle, promotion)
        _save_if_changed(path, lifecycle, updated)
        payload = {"operation": "sync-promotion", **result, "lifecycle": lifecycle_summary(updated)}
    elif args.command == "record-fix":
        history = load_human_checkpoint_history(
            Path(args.checkpoint_history) if args.checkpoint_history else None
        )
        updated, status = record_fix_merged(
            lifecycle,
            history,
            fingerprint=args.fingerprint,
            repository=args.repository,
            pr_number=args.pr_number,
            merge_sha=args.merge_sha,
            verified_by=args.verified_by,
        )
        _save_if_changed(path, lifecycle, updated)
        payload = {"operation": "record-fix", "status": status, "lifecycle": lifecycle_summary(updated)}
    elif args.command == "verify-replay":
        history = load_human_checkpoint_history(
            Path(args.checkpoint_history) if args.checkpoint_history else None
        )
        updated, result = verify_replay(
            lifecycle,
            history,
            fingerprint=args.fingerprint,
            checkpoint_id=args.checkpoint_id,
        )
        _save_if_changed(path, lifecycle, updated)
        payload = {"operation": "verify-replay", **result, "lifecycle": lifecycle_summary(updated)}
    else:
        payload = {"operation": "summary", "lifecycle": lifecycle_summary(lifecycle)}

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
