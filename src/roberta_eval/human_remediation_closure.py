from __future__ import annotations

import argparse
import hashlib
import json
import os
import urllib.error
import urllib.request
from copy import deepcopy
from pathlib import Path
from typing import Any, Protocol

from .github_promotion import HUMAN_REMEDIATION_REPOSITORY
from .human_checkpoint_history import (
    default_human_checkpoint_history_path,
    load_human_checkpoint_history,
    validate_human_checkpoint_history,
)
from .human_remediation_actions import (
    CLOSURE_GATE_VERSION,
    closure_gate,
    default_approval_registry_path,
    load_approval_registry,
    validate_approval_registry,
)
from .human_remediation_lifecycle import (
    default_lifecycle_path,
    load_lifecycle,
    validate_lifecycle,
)
from .human_remediation_promotion import (
    default_promotion_ledger_path,
    load_promotion_ledger,
    validate_promotion_ledger,
)

CLOSURE_LEDGER_VERSION = "roberta_human_remediation_closure_ledger/v1"
CLOSURE_APPROVAL_VERSION = "roberta_human_remediation_closure_approval/v1"
CLOSURE_RESULT_VERSION = "roberta_human_remediation_closure_result/v1"


def default_closure_ledger_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "human_remediation_closure_ledger.json"


def empty_closure_ledger() -> dict[str, Any]:
    return {
        "ledger_version": CLOSURE_LEDGER_VERSION,
        "policy": {
            "explicit_approval_required": True,
            "close_issue_requires_explicit_flag": True,
            "closure_requires_resolved": True,
            "duplicate_close_prevention": True,
            "target_repository": HUMAN_REMEDIATION_REPOSITORY,
            "production_code_mutation": False,
            "execution_authorized": False,
        },
        "closures": [],
    }


def load_closure_ledger(path: Path | None = None) -> dict[str, Any]:
    source = path or default_closure_ledger_path()
    payload = json.loads(source.read_text(encoding="utf-8"))
    validate_closure_ledger(payload)
    return payload


def write_closure_ledger(path: Path, ledger: dict[str, Any]) -> None:
    validate_closure_ledger(ledger)
    path.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _stable_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _find_lifecycle_record(lifecycle: dict[str, Any], fingerprint: str) -> dict[str, Any]:
    record = next(
        (item for item in lifecycle["records"] if item["proposal_fingerprint"] == fingerprint),
        None,
    )
    if record is None:
        raise ValueError("Human remediation lifecycle record not found")
    return record


def _find_promotion(promotion_ledger: dict[str, Any], fingerprint: str) -> dict[str, Any]:
    promotion = next(
        (item for item in promotion_ledger["promotions"] if item["proposal_fingerprint"] == fingerprint),
        None,
    )
    if promotion is None:
        raise ValueError("Human remediation closure requires a promoted GitHub issue")
    return promotion


def _find_checkpoint(history: dict[str, Any], checkpoint_id: str) -> dict[str, Any]:
    checkpoint = next(
        (item for item in history["checkpoints"] if item["checkpoint_id"] == checkpoint_id),
        None,
    )
    if checkpoint is None:
        raise ValueError("resolved Human checkpoint is not present in accepted checkpoint history")
    return checkpoint


def _resolved_verification(record: dict[str, Any]) -> dict[str, Any]:
    if record.get("status") != "RESOLVED":
        raise ValueError("Human remediation closure requires lifecycle status RESOLVED")
    verifications = record.get("verifications") or []
    if not verifications:
        raise ValueError("RESOLVED remediation is missing replay verification evidence")
    verification = verifications[-1]
    if verification.get("outcome") != "RESOLVED":
        raise ValueError("latest Human remediation verification is not RESOLVED")
    if int(verification.get("targeted_failure_count", -1)) != 0:
        raise ValueError("RESOLVED remediation must have zero targeted failure occurrences")
    if float(verification.get("targeted_failure_rate", -1.0)) != 0.0:
        raise ValueError("RESOLVED remediation must have zero targeted failure rate")
    return verification


def _closure_evidence_key(
    *,
    fingerprint: str,
    issue_number: int,
    verification: dict[str, Any],
    failure_code: str,
) -> str:
    return _stable_sha256(
        {
            "proposal_fingerprint": fingerprint,
            "target_repository": HUMAN_REMEDIATION_REPOSITORY,
            "issue_number": issue_number,
            "resolved_checkpoint_id": verification["checkpoint_id"],
            "resolved_checkpoint_sequence": verification["checkpoint_sequence"],
            "failure_code": failure_code,
            "targeted_failure_count": verification["targeted_failure_count"],
            "targeted_failure_rate": verification["targeted_failure_rate"],
        }
    )


def build_closure_approval(
    lifecycle: dict[str, Any],
    checkpoint_history: dict[str, Any],
    approval_registry: dict[str, Any],
    promotion_ledger: dict[str, Any],
    *,
    fingerprint: str,
    reviewer: str,
    approved: bool,
) -> dict[str, Any]:
    validate_lifecycle(lifecycle)
    validate_human_checkpoint_history(checkpoint_history)
    validate_approval_registry(approval_registry)
    validate_promotion_ledger(promotion_ledger)
    reviewer = reviewer.strip()
    if not approved:
        raise ValueError("Human remediation closure requires explicit owner approval")
    if not reviewer:
        raise ValueError("closure reviewer identity is required")

    gate = closure_gate(
        lifecycle,
        checkpoint_history,
        approval_registry,
        promotion_ledger,
        fingerprint=fingerprint,
    )
    if gate.get("status") != "READY_TO_CLOSE" or gate.get("closure_ready") is not True:
        blockers = "; ".join(gate.get("blockers") or []) or "closure gate is not ready"
        raise ValueError(f"Human remediation closure is premature: {blockers}")
    if gate.get("closure_gate_version") != CLOSURE_GATE_VERSION:
        raise ValueError("unsupported Human remediation closure gate version")
    if gate.get("next_action") != "CLOSE_AS_RESOLVED":
        raise ValueError("Human remediation closure gate did not select CLOSE_AS_RESOLVED")

    record = _find_lifecycle_record(lifecycle, fingerprint)
    verification = _resolved_verification(record)
    checkpoint = _find_checkpoint(checkpoint_history, verification["checkpoint_id"])
    if int(checkpoint["sequence"]) != int(verification["checkpoint_sequence"]):
        raise ValueError("resolved checkpoint sequence does not match lifecycle verification")
    failure = checkpoint["snapshot"].get("failure_codes", {}).get(
        record["failure_code"], {"count": 0, "rate": 0.0}
    )
    if int(failure.get("count", 0)) != 0 or float(failure.get("rate", 0.0)) != 0.0:
        raise ValueError("accepted resolved checkpoint still contains the targeted failure")

    promotion = _find_promotion(promotion_ledger, fingerprint)
    issue_number = gate.get("issue_number")
    issue_url = gate.get("issue_url")
    if not isinstance(issue_number, int) or issue_number <= 0:
        raise ValueError("closure-ready remediation is missing a valid GitHub issue number")
    if promotion.get("issue_number") != issue_number or promotion.get("issue_url") != issue_url:
        raise ValueError("closure gate and promotion ledger issue identity mismatch")
    if record.get("issue_number") != issue_number or record.get("issue_url") != issue_url:
        raise ValueError("closure gate and lifecycle issue identity mismatch")

    evidence_key = _closure_evidence_key(
        fingerprint=fingerprint,
        issue_number=issue_number,
        verification=verification,
        failure_code=record["failure_code"],
    )
    approval = {
        "approval_version": CLOSURE_APPROVAL_VERSION,
        "approved": True,
        "approved_by": reviewer,
        "proposal_fingerprint": fingerprint,
        "proposal_sha256": record["proposal_sha256"],
        "closure_evidence_key": evidence_key,
        "target_repository": HUMAN_REMEDIATION_REPOSITORY,
        "issue_number": issue_number,
        "issue_url": issue_url,
        "failure_code": record["failure_code"],
        "resolved_checkpoint_id": verification["checkpoint_id"],
        "resolved_checkpoint_sequence": int(verification["checkpoint_sequence"]),
        "targeted_failure_count": 0,
        "targeted_failure_rate": 0.0,
        "resolved_verification_sha256": _stable_sha256(verification),
        "closure_gate_status": "READY_TO_CLOSE",
        "production_code_mutation": False,
        "execution_authorized": False,
    }
    validate_closure_approval(approval)
    return approval


def validate_closure_approval(approval: dict[str, Any]) -> None:
    if approval.get("approval_version") != CLOSURE_APPROVAL_VERSION:
        raise ValueError("unsupported Human remediation closure approval version")
    if approval.get("approved") is not True:
        raise ValueError("Human remediation closure approval must be explicit")
    if not isinstance(approval.get("approved_by"), str) or not approval["approved_by"].strip():
        raise ValueError("Human remediation closure reviewer is required")
    if approval.get("target_repository") != HUMAN_REMEDIATION_REPOSITORY:
        raise ValueError("Human remediation closure target repository mismatch")
    for key in ("proposal_fingerprint", "proposal_sha256", "closure_evidence_key", "resolved_verification_sha256"):
        value = approval.get(key)
        if not isinstance(value, str) or len(value) != 64:
            raise ValueError(f"Human remediation closure {key} is invalid")
    if not isinstance(approval.get("issue_number"), int) or approval["issue_number"] <= 0:
        raise ValueError("Human remediation closure issue number is invalid")
    if not isinstance(approval.get("issue_url"), str) or not approval["issue_url"].startswith("https://github.com/"):
        raise ValueError("Human remediation closure issue URL is invalid")
    if not isinstance(approval.get("resolved_checkpoint_id"), str) or not approval["resolved_checkpoint_id"]:
        raise ValueError("Human remediation closure resolved checkpoint is required")
    if not isinstance(approval.get("resolved_checkpoint_sequence"), int) or approval["resolved_checkpoint_sequence"] <= 0:
        raise ValueError("Human remediation closure resolved checkpoint sequence is invalid")
    if approval.get("targeted_failure_count") != 0 or float(approval.get("targeted_failure_rate", -1.0)) != 0.0:
        raise ValueError("Human remediation closure requires zero targeted failure evidence")
    if approval.get("closure_gate_status") != "READY_TO_CLOSE":
        raise ValueError("Human remediation closure approval requires READY_TO_CLOSE evidence")
    if approval.get("production_code_mutation") is not False:
        raise ValueError("Human remediation closure cannot authorize production code mutation")
    if approval.get("execution_authorized") is not False:
        raise ValueError("Human remediation closure cannot authorize execution")


def validate_closure_ledger(ledger: dict[str, Any]) -> None:
    if ledger.get("ledger_version") != CLOSURE_LEDGER_VERSION:
        raise ValueError("unsupported Human remediation closure ledger version")
    policy = ledger.get("policy")
    required = {
        "explicit_approval_required": True,
        "close_issue_requires_explicit_flag": True,
        "closure_requires_resolved": True,
        "duplicate_close_prevention": True,
        "target_repository": HUMAN_REMEDIATION_REPOSITORY,
        "production_code_mutation": False,
        "execution_authorized": False,
    }
    if not isinstance(policy, dict):
        raise ValueError("Human remediation closure ledger policy is required")
    for key, expected in required.items():
        if policy.get(key) != expected:
            raise ValueError(f"Human remediation closure ledger policy mismatch: {key}")
    closures = ledger.get("closures")
    if not isinstance(closures, list):
        raise ValueError("Human remediation closures must be a list")
    fingerprints: set[str] = set()
    evidence_keys: set[str] = set()
    issue_ids: set[tuple[str, int]] = set()
    for sequence, entry in enumerate(closures, start=1):
        if not isinstance(entry, dict) or entry.get("sequence") != sequence:
            raise ValueError("Human remediation closure sequence must be contiguous")
        fingerprint = entry.get("proposal_fingerprint")
        evidence_key = entry.get("closure_evidence_key")
        if not isinstance(fingerprint, str) or len(fingerprint) != 64:
            raise ValueError("Human remediation closure fingerprint is invalid")
        if not isinstance(evidence_key, str) or len(evidence_key) != 64:
            raise ValueError("Human remediation closure evidence key is invalid")
        if fingerprint in fingerprints or evidence_key in evidence_keys:
            raise ValueError("duplicate Human remediation closure identity")
        fingerprints.add(fingerprint)
        evidence_keys.add(evidence_key)
        if entry.get("target_repository") != HUMAN_REMEDIATION_REPOSITORY:
            raise ValueError("Human remediation closure repository mismatch")
        issue_number = entry.get("issue_number")
        if not isinstance(issue_number, int) or issue_number <= 0:
            raise ValueError("Human remediation closure ledger issue number is invalid")
        identity = (HUMAN_REMEDIATION_REPOSITORY, issue_number)
        if identity in issue_ids:
            raise ValueError("duplicate Human remediation closed issue identity")
        issue_ids.add(identity)
        if entry.get("issue_closed") is not True or entry.get("issue_state") != "closed":
            raise ValueError("closure ledger may only contain confirmed closed issues")
        approval = entry.get("approval")
        if not isinstance(approval, dict):
            raise ValueError("Human remediation closure approval receipt is required")
        validate_closure_approval(approval)
        if approval["proposal_fingerprint"] != fingerprint or approval["closure_evidence_key"] != evidence_key:
            raise ValueError("Human remediation closure ledger approval identity mismatch")
        if approval["issue_number"] != issue_number:
            raise ValueError("Human remediation closure ledger issue identity mismatch")
        if entry.get("production_code_mutation") is not False or entry.get("execution_authorized") is not False:
            raise ValueError("Human remediation closure ledger cannot authorize code mutation or execution")


def closure_ledger_summary(ledger: dict[str, Any]) -> dict[str, Any]:
    validate_closure_ledger(ledger)
    latest = ledger["closures"][-1] if ledger["closures"] else None
    return {
        "ledger_version": CLOSURE_LEDGER_VERSION,
        "closure_count": len(ledger["closures"]),
        "latest_proposal_fingerprint": latest["proposal_fingerprint"] if latest else None,
        "latest_issue_number": latest["issue_number"] if latest else None,
        "explicit_approval_required": True,
        "duplicate_close_prevention": True,
        "production_code_mutation": False,
        "execution_authorized": False,
    }


def _find_existing_closure(
    ledger: dict[str, Any], approval: dict[str, Any]
) -> dict[str, Any] | None:
    by_fingerprint = next(
        (item for item in ledger["closures"] if item["proposal_fingerprint"] == approval["proposal_fingerprint"]),
        None,
    )
    by_evidence = next(
        (item for item in ledger["closures"] if item["closure_evidence_key"] == approval["closure_evidence_key"]),
        None,
    )
    by_issue = next(
        (item for item in ledger["closures"] if item["issue_number"] == approval["issue_number"]),
        None,
    )
    found = [item for item in (by_fingerprint, by_evidence, by_issue) if item is not None]
    if found and any(item is not found[0] for item in found[1:]):
        raise ValueError("Human remediation closure ledger contains conflicting closure identity")
    return found[0] if found else None


class IssueClosureTransport(Protocol):
    def close_issue(self, *, repository: str, issue_number: int) -> dict[str, Any]:
        """Close one issue and return GitHub's issue payload."""


class GitHubRestIssueClosureTransport:
    def __init__(self, token: str, *, api_base: str = "https://api.github.com") -> None:
        if not token.strip():
            raise ValueError("GitHub token is required")
        self._token = token.strip()
        self._api_base = api_base.rstrip("/")

    def close_issue(self, *, repository: str, issue_number: int) -> dict[str, Any]:
        request = urllib.request.Request(
            f"{self._api_base}/repos/{repository}/issues/{issue_number}",
            data=json.dumps({"state": "closed", "state_reason": "completed"}).encode("utf-8"),
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
                "User-Agent": "roberta-eval-human-remediation-closure",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            method="PATCH",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"GitHub issue closure failed: HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"GitHub issue closure failed: {exc.reason}") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("GitHub issue closure returned invalid payload")
        return payload


def close_human_remediation(
    lifecycle: dict[str, Any],
    checkpoint_history: dict[str, Any],
    approval_registry: dict[str, Any],
    promotion_ledger: dict[str, Any],
    *,
    fingerprint: str,
    reviewer: str,
    approved: bool,
    close_issue: bool,
    closure_ledger_path: Path | None = None,
    transport: IssueClosureTransport | None = None,
) -> dict[str, Any]:
    approval = build_closure_approval(
        lifecycle,
        checkpoint_history,
        approval_registry,
        promotion_ledger,
        fingerprint=fingerprint,
        reviewer=reviewer,
        approved=approved,
    )
    target = closure_ledger_path or default_closure_ledger_path()
    ledger = load_closure_ledger(target)
    existing = _find_existing_closure(ledger, approval)
    if existing is not None:
        if existing["closure_evidence_key"] != approval["closure_evidence_key"]:
            raise ValueError("existing Human remediation closure conflicts with current resolved evidence")
        return {
            "closure_result_version": CLOSURE_RESULT_VERSION,
            "status": "ALREADY_CLOSED",
            "approval": approval,
            "issue_closed": True,
            "issue_number": existing["issue_number"],
            "issue_url": existing["issue_url"],
            "ledger": closure_ledger_summary(ledger),
            "github_issue_state_mutation": False,
            "external_calls": 0,
            "production_code_mutation": False,
            "execution_authorized": False,
        }

    if not close_issue:
        return {
            "closure_result_version": CLOSURE_RESULT_VERSION,
            "status": "APPROVED_DRY_RUN",
            "approval": approval,
            "issue_closed": False,
            "issue_number": approval["issue_number"],
            "issue_url": approval["issue_url"],
            "ledger": closure_ledger_summary(ledger),
            "github_issue_state_mutation": False,
            "external_calls": 0,
            "production_code_mutation": False,
            "execution_authorized": False,
        }

    if transport is None:
        raise ValueError("issue closure transport is required when close_issue=true")
    closed = transport.close_issue(
        repository=HUMAN_REMEDIATION_REPOSITORY,
        issue_number=approval["issue_number"],
    )
    if closed.get("number") != approval["issue_number"]:
        raise RuntimeError("GitHub issue closure returned the wrong issue identity")
    if closed.get("state") != "closed":
        raise RuntimeError("GitHub did not confirm the remediation issue is closed")
    issue_url = closed.get("html_url") or closed.get("url")
    if not isinstance(issue_url, str) or not issue_url.startswith("https://github.com/"):
        raise RuntimeError("GitHub issue closure returned an invalid issue URL")

    updated = deepcopy(ledger)
    entry = {
        "sequence": len(updated["closures"]) + 1,
        "proposal_fingerprint": approval["proposal_fingerprint"],
        "closure_evidence_key": approval["closure_evidence_key"],
        "approval": approval,
        "target_repository": HUMAN_REMEDIATION_REPOSITORY,
        "issue_number": approval["issue_number"],
        "issue_url": issue_url,
        "issue_closed": True,
        "issue_state": "closed",
        "state_reason": closed.get("state_reason") or "completed",
        "production_code_mutation": False,
        "execution_authorized": False,
    }
    updated["closures"].append(entry)
    validate_closure_ledger(updated)
    write_closure_ledger(target, updated)
    return {
        "closure_result_version": CLOSURE_RESULT_VERSION,
        "status": "CLOSED",
        "approval": approval,
        "issue_closed": True,
        "issue_number": approval["issue_number"],
        "issue_url": issue_url,
        "ledger": closure_ledger_summary(updated),
        "github_issue_state_mutation": True,
        "external_calls": 1,
        "production_code_mutation": False,
        "execution_authorized": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="roberta-eval-human-close")
    parser.add_argument("--fingerprint", required=True)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--approve", action="store_true", help="explicitly approve closure of the resolved remediation")
    parser.add_argument("--close-issue", action="store_true", help="after approval, close the tracked GitHub issue")
    parser.add_argument("--lifecycle", default=None)
    parser.add_argument("--checkpoint-history", default=None)
    parser.add_argument("--approval-registry", default=None)
    parser.add_argument("--promotion-ledger", default=None)
    parser.add_argument("--closure-ledger", default=None)
    parser.add_argument("--github-token-env", default="GITHUB_TOKEN")
    parser.add_argument("--output", default=None)
    args = parser.parse_args(argv)

    lifecycle = load_lifecycle(Path(args.lifecycle) if args.lifecycle else default_lifecycle_path())
    history = load_human_checkpoint_history(
        Path(args.checkpoint_history) if args.checkpoint_history else default_human_checkpoint_history_path()
    )
    approvals = load_approval_registry(
        Path(args.approval_registry) if args.approval_registry else default_approval_registry_path()
    )
    promotions = load_promotion_ledger(
        Path(args.promotion_ledger) if args.promotion_ledger else default_promotion_ledger_path()
    )
    transport: IssueClosureTransport | None = None
    if args.close_issue:
        token = os.environ.get(args.github_token_env, "")
        if not token:
            raise ValueError(f"{args.github_token_env} is required with --close-issue")
        transport = GitHubRestIssueClosureTransport(token)

    result = close_human_remediation(
        lifecycle,
        history,
        approvals,
        promotions,
        fingerprint=args.fingerprint,
        reviewer=args.reviewer,
        approved=args.approve,
        close_issue=args.close_issue,
        closure_ledger_path=Path(args.closure_ledger) if args.closure_ledger else None,
        transport=transport,
    )
    if args.output:
        Path(args.output).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
