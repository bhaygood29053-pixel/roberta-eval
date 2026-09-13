from __future__ import annotations

import argparse
import json
import os
import urllib.request
from pathlib import Path
from typing import Any, Protocol

from .github_promotion import HUMAN_REMEDIATION_REPOSITORY
from .human_checkpoint_history import load_human_checkpoint_history
from .human_remediation_actions import (
    build_action_queue,
    load_approval_registry,
)
from .human_remediation_closure import (
    load_closure_ledger,
    validate_closure_ledger,
)
from .human_remediation_lifecycle import load_lifecycle, validate_lifecycle
from .human_remediation_promotion import load_promotion_ledger

TERMINAL_RECONCILIATION_VERSION = "roberta_human_remediation_terminal_reconciliation/v1"
TERMINAL_STATE = "CLOSED"


class IssueStateTransport(Protocol):
    def get_issue(self, repository: str, issue_number: int) -> dict[str, Any]: ...


class GitHubRestIssueStateTransport:
    def __init__(self, token: str) -> None:
        self._token = token

    def get_issue(self, repository: str, issue_number: int) -> dict[str, Any]:
        request = urllib.request.Request(
            f"https://api.github.com/repos/{repository}/issues/{issue_number}",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self._token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "roberta-eval-human-terminal",
            },
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return {
            "repository": repository,
            "issue_number": int(payload["number"]),
            "issue_url": payload["html_url"],
            "state": payload["state"],
        }


def _records_by_fingerprint(lifecycle: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {record["proposal_fingerprint"]: record for record in lifecycle["records"]}


def _terminal_record(
    lifecycle_record: dict[str, Any],
    closure: dict[str, Any],
    *,
    observed_state: str | None = None,
) -> dict[str, Any]:
    if lifecycle_record.get("status") != "RESOLVED":
        raise ValueError("terminal CLOSED requires lifecycle RESOLVED")
    if lifecycle_record.get("proposal_sha256") != closure["approval"]["proposal_sha256"]:
        raise ValueError("terminal reconciliation proposal digest mismatch")
    if lifecycle_record.get("issue_number") != closure.get("issue_number"):
        raise ValueError("terminal reconciliation issue number mismatch")
    if lifecycle_record.get("issue_url") != closure.get("issue_url"):
        raise ValueError("terminal reconciliation issue URL mismatch")
    if lifecycle_record.get("failure_code") != closure["approval"]["failure_code"]:
        raise ValueError("terminal reconciliation failure code mismatch")

    verifications = lifecycle_record.get("verifications") or []
    if not verifications or verifications[-1].get("outcome") != "RESOLVED":
        raise ValueError("terminal reconciliation requires resolved replay evidence")
    verification = verifications[-1]
    approval = closure["approval"]
    if verification.get("checkpoint_id") != approval.get("resolved_checkpoint_id"):
        raise ValueError("terminal reconciliation resolved checkpoint mismatch")
    if int(verification.get("checkpoint_sequence", -1)) != int(
        approval.get("resolved_checkpoint_sequence", -2)
    ):
        raise ValueError("terminal reconciliation checkpoint sequence mismatch")
    if int(verification.get("targeted_failure_count", -1)) != 0:
        raise ValueError("terminal reconciliation requires zero targeted failure count")
    if float(verification.get("targeted_failure_rate", -1.0)) != 0.0:
        raise ValueError("terminal reconciliation requires zero targeted failure rate")

    if observed_state is None:
        consistency = "NOT_CHECKED"
    elif observed_state == "closed":
        consistency = "CONSISTENT_CLOSED"
    elif observed_state == "open":
        consistency = "REOPENED_INCONSISTENCY"
    else:
        raise ValueError(f"unsupported GitHub issue state: {observed_state}")

    return {
        "proposal_fingerprint": lifecycle_record["proposal_fingerprint"],
        "terminal_state": TERMINAL_STATE,
        "lifecycle_status": "RESOLVED",
        "failure_code": lifecycle_record["failure_code"],
        "service": lifecycle_record.get("service"),
        "target_repository": HUMAN_REMEDIATION_REPOSITORY,
        "issue_number": closure["issue_number"],
        "issue_url": closure["issue_url"],
        "closure_evidence_key": closure["closure_evidence_key"],
        "closed_by": approval["approved_by"],
        "resolved_checkpoint_id": approval["resolved_checkpoint_id"],
        "resolved_checkpoint_sequence": approval["resolved_checkpoint_sequence"],
        "targeted_failure_count": approval["targeted_failure_count"],
        "targeted_failure_rate": approval["targeted_failure_rate"],
        "resolved_verification_sha256": approval["resolved_verification_sha256"],
        "observed_issue_state": observed_state,
        "consistency": consistency,
        "evidence_preserved": True,
        "production_code_mutation": False,
        "execution_authorized": False,
    }


def build_terminal_reconciliation(
    lifecycle: dict[str, Any],
    closure_ledger: dict[str, Any],
    *,
    observed_issue_states: dict[int, str] | None = None,
) -> dict[str, Any]:
    validate_lifecycle(lifecycle)
    validate_closure_ledger(closure_ledger)
    records = _records_by_fingerprint(lifecycle)
    terminal: list[dict[str, Any]] = []
    for closure in closure_ledger["closures"]:
        fingerprint = closure["proposal_fingerprint"]
        record = records.get(fingerprint)
        if record is None:
            raise ValueError("closure ledger references an unknown Human remediation")
        terminal.append(
            _terminal_record(
                record,
                closure,
                observed_state=(observed_issue_states or {}).get(closure["issue_number"]),
            )
        )

    inconsistencies = [
        item for item in terminal if item["consistency"] == "REOPENED_INCONSISTENCY"
    ]
    return {
        "terminal_reconciliation_version": TERMINAL_RECONCILIATION_VERSION,
        "terminal_state": TERMINAL_STATE,
        "closed_count": len(terminal),
        "reopened_inconsistency_count": len(inconsistencies),
        "terminal": terminal,
        "inconsistencies": inconsistencies,
        "read_only": True,
        "evidence_rewritten": False,
        "external_calls": 0 if observed_issue_states is None else len(terminal),
        "production_code_mutation": False,
        "execution_authorized": False,
    }


def reconcile_github_issue_states(
    lifecycle: dict[str, Any],
    closure_ledger: dict[str, Any],
    transport: IssueStateTransport,
) -> dict[str, Any]:
    validate_lifecycle(lifecycle)
    validate_closure_ledger(closure_ledger)
    observed: dict[int, str] = {}
    for closure in closure_ledger["closures"]:
        issue = transport.get_issue(HUMAN_REMEDIATION_REPOSITORY, closure["issue_number"])
        if issue.get("repository") != HUMAN_REMEDIATION_REPOSITORY:
            raise ValueError("terminal reconciliation repository mismatch")
        if int(issue.get("issue_number", -1)) != closure["issue_number"]:
            raise ValueError("terminal reconciliation observed issue identity mismatch")
        if issue.get("issue_url") != closure["issue_url"]:
            raise ValueError("terminal reconciliation observed issue URL mismatch")
        observed[closure["issue_number"]] = str(issue.get("state"))
    report = build_terminal_reconciliation(
        lifecycle,
        closure_ledger,
        observed_issue_states=observed,
    )
    report["external_calls"] = len(closure_ledger["closures"])
    return report


def build_terminal_action_queue(
    lifecycle: dict[str, Any],
    checkpoint_history: dict[str, Any],
    approval_registry: dict[str, Any],
    promotion_ledger: dict[str, Any],
    closure_ledger: dict[str, Any],
    *,
    terminal_reconciliation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base = build_action_queue(
        lifecycle,
        checkpoint_history,
        approval_registry,
        promotion_ledger,
    )
    terminal_report = terminal_reconciliation or build_terminal_reconciliation(
        lifecycle,
        closure_ledger,
    )
    if terminal_report.get("terminal_reconciliation_version") != TERMINAL_RECONCILIATION_VERSION:
        raise ValueError("unsupported terminal reconciliation report version")
    closed_fingerprints = {
        item["proposal_fingerprint"] for item in terminal_report["terminal"]
    }
    active_items = [
        item for item in base["items"] if item["proposal_fingerprint"] not in closed_fingerprints
    ]
    action_counts = {key: 0 for key in base["action_counts"]}
    for item in active_items:
        action_counts[item["next_action"]] += 1
    return {
        **base,
        "record_count": len(active_items) + len(terminal_report["terminal"]),
        "active_count": len(active_items),
        "closure_ready_count": sum(1 for item in active_items if item["closure_ready"]),
        "action_counts": action_counts,
        "items": active_items,
        "terminal_closed_count": terminal_report["closed_count"],
        "reopened_inconsistency_count": terminal_report["reopened_inconsistency_count"],
        "terminal": terminal_report["terminal"],
        "inconsistencies": terminal_report["inconsistencies"],
        "terminal_state": TERMINAL_STATE,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="roberta-eval-human-terminal")
    parser.add_argument("--lifecycle", default=None)
    parser.add_argument("--closure-ledger", default=None)
    parser.add_argument("--github-token-env", default="GITHUB_TOKEN")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("summary", help="show terminal CLOSED remediations from accepted closure evidence")
    reconcile = sub.add_parser("reconcile", help="read GitHub issue state and detect reopen inconsistencies")
    reconcile.add_argument("--check-github", action="store_true", required=True)
    sub.add_parser("queue", help="show active action queue with terminal CLOSED records removed")
    args = parser.parse_args(argv)

    lifecycle = load_lifecycle(Path(args.lifecycle) if args.lifecycle else None)
    closure_ledger = load_closure_ledger(
        Path(args.closure_ledger) if args.closure_ledger else None
    )

    if args.command == "summary":
        payload = build_terminal_reconciliation(lifecycle, closure_ledger)
    elif args.command == "reconcile":
        token = os.environ.get(args.github_token_env)
        if not token:
            raise ValueError(f"{args.github_token_env} is required with --check-github")
        payload = reconcile_github_issue_states(
            lifecycle,
            closure_ledger,
            GitHubRestIssueStateTransport(token),
        )
    else:
        payload = build_terminal_action_queue(
            lifecycle,
            load_human_checkpoint_history(),
            load_approval_registry(),
            load_promotion_ledger(),
            closure_ledger,
        )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
