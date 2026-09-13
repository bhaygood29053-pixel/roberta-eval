from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from .human_checkpoint_history import (
    default_human_checkpoint_history_path,
    load_human_checkpoint_history,
)
from .human_remediation_actions import (
    default_approval_registry_path,
    load_approval_registry,
)
from .human_remediation_closure import (
    GitHubRestIssueClosureTransport,
    IssueClosureTransport,
    close_human_remediation,
)
from .human_remediation_lifecycle import default_lifecycle_path, load_lifecycle
from .human_remediation_lineage import build_generational_lineage_report
from .human_remediation_promotion import (
    default_promotion_ledger_path,
    load_promotion_ledger,
)
from .human_remediation_reopen_cycle import (
    default_reopen_cycle_promotion_ledger_path,
    load_reopen_cycle_promotion_ledger,
)
from .human_remediation_root_cause import (
    default_root_cause_ledger_path,
    load_root_cause_ledger,
    root_cause_sufficiency_gate,
)


def guarded_close_human_remediation(
    lifecycle: dict[str, Any],
    checkpoint_history: dict[str, Any],
    approval_registry: dict[str, Any],
    promotion_ledger: dict[str, Any],
    reopen_cycle_ledger: dict[str, Any],
    root_cause_ledger: dict[str, Any],
    *,
    fingerprint: str,
    reviewer: str,
    approved: bool,
    close_issue: bool,
    closure_ledger_path: Path | None = None,
    transport: IssueClosureTransport | None = None,
) -> dict[str, Any]:
    lineage = build_generational_lineage_report(lifecycle, reopen_cycle_ledger)
    gate = root_cause_sufficiency_gate(
        lineage,
        root_cause_ledger,
        fingerprint=fingerprint,
    )
    if gate.get("closure_sufficient") is not True:
        blockers = "; ".join(gate.get("blockers") or []) or gate.get("status", "root-cause gate blocked")
        raise ValueError(
            "Human remediation closure blocked by root-cause investigation gate: " + blockers
        )
    result = close_human_remediation(
        lifecycle,
        checkpoint_history,
        approval_registry,
        promotion_ledger,
        fingerprint=fingerprint,
        reviewer=reviewer,
        approved=approved,
        close_issue=close_issue,
        closure_ledger_path=closure_ledger_path,
        transport=transport,
    )
    return {**result, "root_cause_sufficiency": gate}


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
    parser.add_argument("--reopen-cycle-ledger", default=None)
    parser.add_argument("--root-cause-ledger", default=None)
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
    reopen_cycles = load_reopen_cycle_promotion_ledger(
        Path(args.reopen_cycle_ledger)
        if args.reopen_cycle_ledger
        else default_reopen_cycle_promotion_ledger_path()
    )
    root_cause = load_root_cause_ledger(
        Path(args.root_cause_ledger) if args.root_cause_ledger else default_root_cause_ledger_path()
    )

    transport: IssueClosureTransport | None = None
    if args.close_issue:
        token = os.environ.get(args.github_token_env, "")
        if not token:
            raise ValueError(f"{args.github_token_env} is required with --close-issue")
        transport = GitHubRestIssueClosureTransport(token)

    result = guarded_close_human_remediation(
        lifecycle,
        history,
        approvals,
        promotions,
        reopen_cycles,
        root_cause,
        fingerprint=args.fingerprint,
        reviewer=args.reviewer,
        approved=args.approve,
        close_issue=args.close_issue,
        closure_ledger_path=Path(args.closure_ledger) if args.closure_ledger else None,
        transport=transport,
    )
    if args.output:
        Path(args.output).write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
