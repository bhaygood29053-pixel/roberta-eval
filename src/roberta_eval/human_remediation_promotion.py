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

from .github_promotion import HUMAN_REMEDIATION_REPOSITORY, load_jsonl

PROMOTION_LEDGER_VERSION = "roberta_human_remediation_promotion_ledger/v1"
APPROVAL_VERSION = "roberta_human_remediation_approval/v1"
PROMOTION_RESULT_VERSION = "roberta_human_remediation_promotion_result/v1"


def default_promotion_ledger_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "human_remediation_promotion_ledger.json"


def empty_promotion_ledger() -> dict[str, Any]:
    return {
        "ledger_version": PROMOTION_LEDGER_VERSION,
        "policy": {
            "approval_required": True,
            "create_issue_requires_explicit_flag": True,
            "duplicate_issue_prevention": True,
            "target_repository": HUMAN_REMEDIATION_REPOSITORY,
            "production_code_mutation": False,
            "execution_authorized": False,
        },
        "promotions": [],
    }


def load_promotion_ledger(path: Path | None = None) -> dict[str, Any]:
    source = path or default_promotion_ledger_path()
    ledger = json.loads(source.read_text(encoding="utf-8"))
    validate_promotion_ledger(ledger)
    return ledger


def write_promotion_ledger(path: Path, ledger: dict[str, Any]) -> None:
    validate_promotion_ledger(ledger)
    path.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _stable_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _proposal_digest(proposal: dict[str, Any]) -> str:
    return _stable_sha256(proposal)


def _evidence_key(proposal: dict[str, Any]) -> str:
    priority = proposal.get("human_priority") or {}
    payload = {
        "proposal_kind": proposal.get("proposal_kind"),
        "target_repository": proposal.get("target_repository"),
        "previous_snapshot_id": proposal.get("previous_snapshot_id"),
        "current_snapshot_id": proposal.get("current_snapshot_id"),
        "failure_code": priority.get("failure_code"),
        "recurrence": priority.get("recurrence"),
        "service": priority.get("service"),
    }
    return _stable_sha256(payload)


def validate_human_remediation_proposal(proposal: dict[str, Any]) -> None:
    if not isinstance(proposal, dict):
        raise ValueError("Human remediation proposal must be an object")
    if proposal.get("proposal_kind") != "human_language_remediation":
        raise ValueError("proposal is not a Human language remediation proposal")
    if proposal.get("target_repository") != HUMAN_REMEDIATION_REPOSITORY:
        raise ValueError("Human remediation proposal target repository is not allowed")
    fingerprint = proposal.get("proposal_fingerprint")
    if not isinstance(fingerprint, str) or len(fingerprint) != 64:
        raise ValueError("Human remediation proposal fingerprint is invalid")
    if proposal.get("issue_created") is not False:
        raise ValueError("Human remediation proposal must be unpromoted")
    if proposal.get("production_mutation") is not False:
        raise ValueError("Human remediation proposal cannot carry production mutation authority")
    if proposal.get("execution_authorized") is not False:
        raise ValueError("Human remediation proposal cannot carry execution authority")
    if proposal.get("reviewable_proposal_only") is not True:
        raise ValueError("Human remediation proposal must remain review-only before approval")
    if proposal.get("ai_judge_used") is not False:
        raise ValueError("Human remediation proposal must be deterministic")
    if proposal.get("judge_model_calls") != 0 or proposal.get("external_calls") != 0:
        raise ValueError("Human remediation proposal must originate from zero-call grading")
    for key in ("previous_snapshot_id", "current_snapshot_id", "title", "body"):
        if not isinstance(proposal.get(key), str) or not proposal[key]:
            raise ValueError(f"Human remediation proposal {key} is required")
    priority = proposal.get("human_priority")
    if not isinstance(priority, dict):
        raise ValueError("Human remediation proposal priority is required")
    for key in ("failure_code", "recurrence"):
        if not isinstance(priority.get(key), str) or not priority[key]:
            raise ValueError(f"Human remediation priority {key} is required")
    current_count = priority.get("current_count")
    current_rate = priority.get("current_rate")
    if not isinstance(current_count, int) or current_count <= 0:
        raise ValueError("Human remediation current_count must be positive")
    if not isinstance(current_rate, (int, float)) or not (0 < float(current_rate) <= 1):
        raise ValueError("Human remediation current_rate must be in (0, 1]")


def build_approval_receipt(
    proposal: dict[str, Any],
    *,
    reviewer: str,
    approved: bool,
) -> dict[str, Any]:
    validate_human_remediation_proposal(proposal)
    reviewer = reviewer.strip()
    if not approved:
        raise ValueError("Human remediation promotion requires explicit approval")
    if not reviewer:
        raise ValueError("approval reviewer is required")
    priority = proposal["human_priority"]
    return {
        "approval_version": APPROVAL_VERSION,
        "approved": True,
        "approved_by": reviewer,
        "proposal_fingerprint": proposal["proposal_fingerprint"],
        "proposal_sha256": _proposal_digest(proposal),
        "evidence_key": _evidence_key(proposal),
        "target_repository": HUMAN_REMEDIATION_REPOSITORY,
        "previous_snapshot_id": proposal["previous_snapshot_id"],
        "current_snapshot_id": proposal["current_snapshot_id"],
        "failure_code": priority["failure_code"],
        "recurrence": priority["recurrence"],
        "service": priority.get("service"),
        "production_code_mutation": False,
        "execution_authorized": False,
    }


def validate_promotion_ledger(ledger: dict[str, Any]) -> None:
    if ledger.get("ledger_version") != PROMOTION_LEDGER_VERSION:
        raise ValueError("unsupported Human remediation promotion ledger version")
    policy = ledger.get("policy")
    if not isinstance(policy, dict):
        raise ValueError("Human remediation promotion ledger policy is required")
    required_policy = {
        "approval_required": True,
        "create_issue_requires_explicit_flag": True,
        "duplicate_issue_prevention": True,
        "target_repository": HUMAN_REMEDIATION_REPOSITORY,
        "production_code_mutation": False,
        "execution_authorized": False,
    }
    for key, expected in required_policy.items():
        if policy.get(key) != expected:
            raise ValueError(f"Human remediation promotion policy mismatch: {key}")

    promotions = ledger.get("promotions")
    if not isinstance(promotions, list):
        raise ValueError("Human remediation promotions must be a list")

    fingerprints: set[str] = set()
    evidence_keys: set[str] = set()
    issue_ids: set[tuple[str, int]] = set()
    for sequence, entry in enumerate(promotions, start=1):
        if not isinstance(entry, dict):
            raise ValueError("Human remediation promotion entry must be an object")
        if entry.get("sequence") != sequence:
            raise ValueError("Human remediation promotion sequence must be contiguous")
        fingerprint = entry.get("proposal_fingerprint")
        evidence_key = entry.get("evidence_key")
        if not isinstance(fingerprint, str) or len(fingerprint) != 64:
            raise ValueError("Human remediation promotion fingerprint is invalid")
        if not isinstance(evidence_key, str) or len(evidence_key) != 64:
            raise ValueError("Human remediation promotion evidence_key is invalid")
        if fingerprint in fingerprints:
            raise ValueError("duplicate Human remediation proposal fingerprint in ledger")
        if evidence_key in evidence_keys:
            raise ValueError("duplicate Human remediation evidence key in ledger")
        fingerprints.add(fingerprint)
        evidence_keys.add(evidence_key)

        if entry.get("target_repository") != HUMAN_REMEDIATION_REPOSITORY:
            raise ValueError("Human remediation promotion target repository mismatch")
        if entry.get("issue_created") is not True:
            raise ValueError("promotion ledger may only contain created issues")
        issue_number = entry.get("issue_number")
        issue_url = entry.get("issue_url")
        if not isinstance(issue_number, int) or issue_number <= 0:
            raise ValueError("Human remediation promotion issue_number is invalid")
        if not isinstance(issue_url, str) or not issue_url.startswith("https://github.com/"):
            raise ValueError("Human remediation promotion issue_url is invalid")
        issue_identity = (HUMAN_REMEDIATION_REPOSITORY, issue_number)
        if issue_identity in issue_ids:
            raise ValueError("duplicate GitHub issue identity in promotion ledger")
        issue_ids.add(issue_identity)

        approval = entry.get("approval")
        if not isinstance(approval, dict) or approval.get("approved") is not True:
            raise ValueError("Human remediation promotion approval receipt is required")
        if approval.get("proposal_fingerprint") != fingerprint:
            raise ValueError("approval/proposal fingerprint mismatch")
        if approval.get("evidence_key") != evidence_key:
            raise ValueError("approval/evidence key mismatch")
        if entry.get("production_code_mutation") is not False:
            raise ValueError("promotion ledger cannot authorize production mutation")
        if entry.get("execution_authorized") is not False:
            raise ValueError("promotion ledger cannot authorize execution")


def promotion_ledger_summary(ledger: dict[str, Any]) -> dict[str, Any]:
    validate_promotion_ledger(ledger)
    promotions = ledger["promotions"]
    latest = promotions[-1] if promotions else None
    return {
        "ledger_version": PROMOTION_LEDGER_VERSION,
        "promotion_count": len(promotions),
        "latest_proposal_fingerprint": latest["proposal_fingerprint"] if latest else None,
        "latest_issue_number": latest["issue_number"] if latest else None,
        "target_repository": HUMAN_REMEDIATION_REPOSITORY,
        "approval_required": True,
        "duplicate_issue_prevention": True,
        "production_code_mutation": False,
        "execution_authorized": False,
    }


def _find_existing(
    ledger: dict[str, Any],
    *,
    fingerprint: str,
    evidence_key: str,
) -> dict[str, Any] | None:
    by_fingerprint = next(
        (item for item in ledger["promotions"] if item["proposal_fingerprint"] == fingerprint),
        None,
    )
    by_evidence = next(
        (item for item in ledger["promotions"] if item["evidence_key"] == evidence_key),
        None,
    )
    if by_fingerprint and by_evidence and by_fingerprint is not by_evidence:
        raise ValueError("promotion ledger contains conflicting duplicate identity")
    return by_fingerprint or by_evidence


def select_human_proposal(
    proposals: list[dict[str, Any]],
    *,
    fingerprint: str | None = None,
) -> dict[str, Any]:
    human = [item for item in proposals if item.get("proposal_kind") == "human_language_remediation"]
    if fingerprint:
        human = [item for item in human if item.get("proposal_fingerprint") == fingerprint]
    if not human:
        raise ValueError("no matching Human remediation proposal found")
    if len(human) != 1:
        raise ValueError("proposal fingerprint is required when more than one Human proposal exists")
    validate_human_remediation_proposal(human[0])
    return human[0]


def build_issue_body(proposal: dict[str, Any], approval: dict[str, Any]) -> str:
    return "\n".join(
        [
            proposal["body"],
            "",
            "## Promotion trace",
            "",
            f"- Proposal fingerprint: `{approval['proposal_fingerprint']}`",
            f"- Evidence key: `{approval['evidence_key']}`",
            f"- Approved by: `{approval['approved_by']}`",
            f"- Previous checkpoint: `{approval['previous_snapshot_id']}`",
            f"- Current checkpoint: `{approval['current_snapshot_id']}`",
            "",
            "This issue was promoted through the explicit ROBERTA LAB Human-remediation approval gate. "
            "Promotion does not authorize production-code mutation or execution; normal repository review, "
            "tests, and merge gates still apply.",
        ]
    )


class IssueTransport(Protocol):
    def create_issue(self, *, repository: str, title: str, body: str) -> dict[str, Any]:
        """Create one issue and return at least number and html_url."""


class GitHubRestIssueTransport:
    def __init__(self, token: str, *, api_base: str = "https://api.github.com") -> None:
        if not token.strip():
            raise ValueError("GitHub token is required")
        self._token = token.strip()
        self._api_base = api_base.rstrip("/")

    def create_issue(self, *, repository: str, title: str, body: str) -> dict[str, Any]:
        request = urllib.request.Request(
            f"{self._api_base}/repos/{repository}/issues",
            data=json.dumps({"title": title, "body": body}).encode("utf-8"),
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
                "User-Agent": "roberta-eval-human-remediation-promotion",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"GitHub issue creation failed: HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"GitHub issue creation failed: {exc.reason}") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("GitHub issue creation returned invalid payload")
        return payload


def promote_human_proposal(
    proposal: dict[str, Any],
    *,
    reviewer: str,
    approved: bool,
    create_issue: bool,
    ledger_path: Path | None = None,
    transport: IssueTransport | None = None,
) -> dict[str, Any]:
    validate_human_remediation_proposal(proposal)
    approval = build_approval_receipt(proposal, reviewer=reviewer, approved=approved)
    target = ledger_path or default_promotion_ledger_path()
    ledger = load_promotion_ledger(target)

    existing = _find_existing(
        ledger,
        fingerprint=approval["proposal_fingerprint"],
        evidence_key=approval["evidence_key"],
    )
    if existing is not None:
        if existing.get("proposal_sha256") != approval["proposal_sha256"]:
            raise ValueError("existing promotion identity conflicts with current proposal content")
        return {
            "promotion_result_version": PROMOTION_RESULT_VERSION,
            "status": "ALREADY_PROMOTED",
            "approval": approval,
            "issue_created": True,
            "issue_number": existing["issue_number"],
            "issue_url": existing["issue_url"],
            "target_repository": HUMAN_REMEDIATION_REPOSITORY,
            "ledger": promotion_ledger_summary(ledger),
            "production_code_mutation": False,
            "execution_authorized": False,
        }

    if not create_issue:
        return {
            "promotion_result_version": PROMOTION_RESULT_VERSION,
            "status": "APPROVED_DRY_RUN",
            "approval": approval,
            "issue_created": False,
            "target_repository": HUMAN_REMEDIATION_REPOSITORY,
            "title": proposal["title"],
            "body": build_issue_body(proposal, approval),
            "ledger": promotion_ledger_summary(ledger),
            "production_code_mutation": False,
            "execution_authorized": False,
        }

    if transport is None:
        raise ValueError("issue transport is required when create_issue=true")

    created = transport.create_issue(
        repository=HUMAN_REMEDIATION_REPOSITORY,
        title=proposal["title"],
        body=build_issue_body(proposal, approval),
    )
    issue_number = created.get("number")
    issue_url = created.get("html_url") or created.get("url")
    if not isinstance(issue_number, int) or issue_number <= 0:
        raise RuntimeError("created GitHub issue number is invalid")
    if not isinstance(issue_url, str) or not issue_url.startswith("https://github.com/"):
        raise RuntimeError("created GitHub issue URL is invalid")

    updated = deepcopy(ledger)
    entry = {
        "sequence": len(updated["promotions"]) + 1,
        "proposal_fingerprint": approval["proposal_fingerprint"],
        "evidence_key": approval["evidence_key"],
        "proposal_sha256": approval["proposal_sha256"],
        "approval": approval,
        "target_repository": HUMAN_REMEDIATION_REPOSITORY,
        "issue_created": True,
        "issue_number": issue_number,
        "issue_url": issue_url,
        "production_code_mutation": False,
        "execution_authorized": False,
    }
    updated["promotions"].append(entry)
    validate_promotion_ledger(updated)
    write_promotion_ledger(target, updated)

    return {
        "promotion_result_version": PROMOTION_RESULT_VERSION,
        "status": "PROMOTED",
        "approval": approval,
        "issue_created": True,
        "issue_number": issue_number,
        "issue_url": issue_url,
        "target_repository": HUMAN_REMEDIATION_REPOSITORY,
        "ledger": promotion_ledger_summary(updated),
        "production_code_mutation": False,
        "execution_authorized": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="roberta-eval-human-promote")
    parser.add_argument("--proposals", required=True, help="Human remediation proposal JSONL")
    parser.add_argument("--fingerprint", default=None, help="proposal fingerprint when input contains multiple Human proposals")
    parser.add_argument("--reviewer", required=True, help="reviewer identity recorded in approval receipt")
    parser.add_argument("--approve", action="store_true", help="explicitly approve the selected proposal")
    parser.add_argument("--create-issue", action="store_true", help="after approval, create the tracked GitHub issue")
    parser.add_argument("--ledger", default=None, help="optional promotion-ledger JSON path")
    parser.add_argument("--github-token-env", default="GITHUB_TOKEN", help="environment variable containing GitHub token")
    parser.add_argument("--output", default=None, help="optional JSON promotion result")
    args = parser.parse_args(argv)

    proposals = load_jsonl(Path(args.proposals))
    proposal = select_human_proposal(proposals, fingerprint=args.fingerprint)
    transport: IssueTransport | None = None
    if args.create_issue:
        token = os.environ.get(args.github_token_env, "")
        if not token:
            raise ValueError(f"{args.github_token_env} is required with --create-issue")
        transport = GitHubRestIssueTransport(token)

    result = promote_human_proposal(
        proposal,
        reviewer=args.reviewer,
        approved=args.approve,
        create_issue=args.create_issue,
        ledger_path=Path(args.ledger) if args.ledger else None,
        transport=transport,
    )
    if args.output:
        Path(args.output).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
