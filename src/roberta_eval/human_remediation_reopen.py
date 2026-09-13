from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from .human_checkpoint_history import (
    default_human_checkpoint_history_path,
    load_human_checkpoint_history,
    validate_human_checkpoint_history,
)
from .human_remediation_terminal import TERMINAL_RECONCILIATION_VERSION

REOPEN_ADJUDICATION_VERSION = "roberta_human_remediation_reopen_adjudication/v1"
REOPEN_ADJUDICATION_LEDGER_VERSION = "roberta_human_remediation_reopen_adjudication_ledger/v1"
REOPEN_CYCLE_SEED_VERSION = "roberta_human_remediation_reopen_cycle_seed/v1"

ADMINISTRATIVE_NON_QUALITY = "ADMINISTRATIVE_NON_QUALITY"
GENUINE_HUMAN_QUALITY_REGRESSION = "GENUINE_HUMAN_QUALITY_REGRESSION"
CLASSIFICATIONS = (ADMINISTRATIVE_NON_QUALITY, GENUINE_HUMAN_QUALITY_REGRESSION)


def default_reopen_adjudication_ledger_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "human_remediation_reopen_adjudication_ledger.json"


def empty_reopen_adjudication_ledger() -> dict[str, Any]:
    return {
        "ledger_version": REOPEN_ADJUDICATION_LEDGER_VERSION,
        "policy": {
            "explicit_owner_adjudication_required": True,
            "fresh_checkpoint_required_for_regression": True,
            "administrative_reopen_preserves_terminal_closed": True,
            "automatic_new_cycle_creation": False,
            "production_code_mutation": False,
            "execution_authorized": False,
        },
        "adjudications": [],
    }


def load_reopen_adjudication_ledger(path: Path | None = None) -> dict[str, Any]:
    source = path or default_reopen_adjudication_ledger_path()
    payload = json.loads(source.read_text(encoding="utf-8"))
    validate_reopen_adjudication_ledger(payload)
    return payload


def write_reopen_adjudication_ledger(path: Path, ledger: dict[str, Any]) -> None:
    validate_reopen_adjudication_ledger(ledger)
    path.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _stable_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _validate_terminal_report(report: dict[str, Any]) -> None:
    if report.get("terminal_reconciliation_version") != TERMINAL_RECONCILIATION_VERSION:
        raise ValueError("unsupported terminal reconciliation report version")
    if report.get("read_only") is not True:
        raise ValueError("reopen adjudication requires read-only terminal reconciliation evidence")
    if report.get("evidence_rewritten") is not False:
        raise ValueError("reopen adjudication cannot consume rewritten terminal evidence")
    if report.get("production_code_mutation") is not False:
        raise ValueError("terminal reconciliation cannot authorize production mutation")
    if report.get("execution_authorized") is not False:
        raise ValueError("terminal reconciliation cannot authorize execution")


def _find_reopened(report: dict[str, Any], fingerprint: str) -> dict[str, Any]:
    _validate_terminal_report(report)
    matches = [
        item
        for item in report.get("inconsistencies", [])
        if item.get("proposal_fingerprint") == fingerprint
        and item.get("consistency") == "REOPENED_INCONSISTENCY"
    ]
    if len(matches) != 1:
        raise ValueError("explicit REOPENED_INCONSISTENCY evidence is required")
    item = matches[0]
    if item.get("terminal_state") != "CLOSED" or item.get("lifecycle_status") != "RESOLVED":
        raise ValueError("reopen adjudication requires preserved CLOSED/RESOLVED evidence")
    if item.get("observed_issue_state") != "open":
        raise ValueError("reopen adjudication requires observed GitHub issue state open")
    if item.get("evidence_preserved") is not True:
        raise ValueError("reopen adjudication requires preserved terminal evidence")
    return item


def _find_checkpoint(history: dict[str, Any], checkpoint_id: str) -> dict[str, Any]:
    checkpoint = next(
        (item for item in history["checkpoints"] if item["checkpoint_id"] == checkpoint_id),
        None,
    )
    if checkpoint is None:
        raise ValueError("fresh accepted Human checkpoint was not found")
    return checkpoint


def _reopen_event_key(item: dict[str, Any]) -> str:
    return _stable_sha256(
        {
            "proposal_fingerprint": item["proposal_fingerprint"],
            "closure_evidence_key": item["closure_evidence_key"],
            "issue_number": item["issue_number"],
            "issue_url": item["issue_url"],
            "failure_code": item["failure_code"],
            "resolved_checkpoint_id": item["resolved_checkpoint_id"],
            "resolved_checkpoint_sequence": item["resolved_checkpoint_sequence"],
            "observed_issue_state": "open",
        }
    )


def _new_cycle_id(
    item: dict[str, Any],
    checkpoint: dict[str, Any],
    owner: str,
    metrics: dict[str, Any],
) -> str:
    digest = _stable_sha256(
        {
            "reopen_event_key": _reopen_event_key(item),
            "prior_proposal_fingerprint": item["proposal_fingerprint"],
            "closure_evidence_key": item["closure_evidence_key"],
            "issue_number": item["issue_number"],
            "failure_code": item["failure_code"],
            "checkpoint_id": checkpoint["checkpoint_id"],
            "checkpoint_sequence": checkpoint["sequence"],
            "checkpoint_corpus_sha256": checkpoint["corpus_sha256"],
            "targeted_failure_count": int(metrics["count"]),
            "targeted_failure_rate": float(metrics["rate"]),
            "adjudicated_by": owner,
        }
    )
    return f"human-remediation-reopen::{digest}"


def build_reopen_adjudication(
    terminal_report: dict[str, Any],
    checkpoint_history: dict[str, Any],
    *,
    fingerprint: str,
    owner: str,
    classification: str,
    approved: bool,
    checkpoint_id: str | None = None,
) -> dict[str, Any]:
    validate_human_checkpoint_history(checkpoint_history)
    owner = owner.strip()
    if not approved:
        raise ValueError("Human remediation reopen adjudication requires explicit owner approval")
    if not owner:
        raise ValueError("reopen adjudicator identity is required")
    if classification not in CLASSIFICATIONS:
        raise ValueError("unsupported Human remediation reopen classification")

    item = _find_reopened(terminal_report, fingerprint)
    event_key = _reopen_event_key(item)
    prior_sequence = int(item["resolved_checkpoint_sequence"])

    fresh_evidence: dict[str, Any] | None = None
    new_cycle_eligible = False
    new_cycle_id: str | None = None

    if classification == ADMINISTRATIVE_NON_QUALITY:
        if checkpoint_id is not None:
            raise ValueError("administrative reopen adjudication must not attach regression checkpoint evidence")
    else:
        if not checkpoint_id:
            raise ValueError("genuine Human-quality regression requires a fresh accepted checkpoint")
        checkpoint = _find_checkpoint(checkpoint_history, checkpoint_id)
        sequence = int(checkpoint["sequence"])
        if sequence <= prior_sequence:
            raise ValueError("regression checkpoint must be newer than the prior resolved checkpoint")
        metrics = checkpoint["snapshot"].get("failure_codes", {}).get(
            item["failure_code"], {"count": 0, "rate": 0.0}
        )
        count = int(metrics.get("count", 0))
        rate = float(metrics.get("rate", 0.0))
        if count <= 0 or rate <= 0.0:
            raise ValueError("fresh accepted checkpoint does not prove recurrence of the targeted Human defect")
        fresh_evidence = {
            "checkpoint_id": checkpoint["checkpoint_id"],
            "checkpoint_sequence": sequence,
            "checkpoint_corpus_sha256": checkpoint["corpus_sha256"],
            "targeted_failure_count": count,
            "targeted_failure_rate": rate,
        }
        new_cycle_eligible = True
        new_cycle_id = _new_cycle_id(item, checkpoint, owner, metrics)

    adjudication = {
        "adjudication_version": REOPEN_ADJUDICATION_VERSION,
        "reopen_event_key": event_key,
        "proposal_fingerprint": item["proposal_fingerprint"],
        "closure_evidence_key": item["closure_evidence_key"],
        "target_repository": item["target_repository"],
        "issue_number": item["issue_number"],
        "issue_url": item["issue_url"],
        "failure_code": item["failure_code"],
        "service": item.get("service"),
        "prior_terminal_state": "CLOSED",
        "prior_resolved_checkpoint_id": item["resolved_checkpoint_id"],
        "prior_resolved_checkpoint_sequence": prior_sequence,
        "classification": classification,
        "approved": True,
        "adjudicated_by": owner,
        "terminal_evidence_preserved": True,
        "fresh_regression_evidence": fresh_evidence,
        "new_cycle_eligible": new_cycle_eligible,
        "new_cycle_id": new_cycle_id,
        "automatic_new_cycle_creation": False,
        "production_code_mutation": False,
        "execution_authorized": False,
    }
    adjudication["decision_sha256"] = _stable_sha256(adjudication)
    validate_reopen_adjudication(adjudication)
    return adjudication


def validate_reopen_adjudication(adjudication: dict[str, Any]) -> None:
    if adjudication.get("adjudication_version") != REOPEN_ADJUDICATION_VERSION:
        raise ValueError("unsupported Human remediation reopen adjudication version")
    for key in ("reopen_event_key", "proposal_fingerprint", "closure_evidence_key", "decision_sha256"):
        value = adjudication.get(key)
        if not isinstance(value, str) or len(value) != 64:
            raise ValueError(f"reopen adjudication {key} is invalid")
    if adjudication.get("classification") not in CLASSIFICATIONS:
        raise ValueError("reopen adjudication classification is invalid")
    if adjudication.get("approved") is not True:
        raise ValueError("reopen adjudication must be explicitly approved")
    if not isinstance(adjudication.get("adjudicated_by"), str) or not adjudication["adjudicated_by"].strip():
        raise ValueError("reopen adjudicator is required")
    if adjudication.get("prior_terminal_state") != "CLOSED":
        raise ValueError("reopen adjudication must preserve prior terminal CLOSED")
    if adjudication.get("terminal_evidence_preserved") is not True:
        raise ValueError("reopen adjudication must preserve terminal evidence")
    if adjudication.get("automatic_new_cycle_creation") is not False:
        raise ValueError("reopen adjudication cannot auto-create a remediation cycle")
    if adjudication.get("production_code_mutation") is not False:
        raise ValueError("reopen adjudication cannot authorize production mutation")
    if adjudication.get("execution_authorized") is not False:
        raise ValueError("reopen adjudication cannot authorize execution")

    classification = adjudication["classification"]
    evidence = adjudication.get("fresh_regression_evidence")
    eligible = adjudication.get("new_cycle_eligible")
    cycle_id = adjudication.get("new_cycle_id")
    if classification == ADMINISTRATIVE_NON_QUALITY:
        if evidence is not None or eligible is not False or cycle_id is not None:
            raise ValueError("administrative reopen cannot create a new remediation cycle")
    else:
        if not isinstance(evidence, dict):
            raise ValueError("genuine regression requires fresh accepted checkpoint evidence")
        if int(evidence.get("checkpoint_sequence", 0)) <= int(adjudication["prior_resolved_checkpoint_sequence"]):
            raise ValueError("genuine regression evidence must be newer than prior resolution")
        if int(evidence.get("targeted_failure_count", 0)) <= 0:
            raise ValueError("genuine regression requires positive targeted failure count")
        if float(evidence.get("targeted_failure_rate", 0.0)) <= 0.0:
            raise ValueError("genuine regression requires positive targeted failure rate")
        if eligible is not True:
            raise ValueError("confirmed genuine regression must be new-cycle eligible")
        if not isinstance(cycle_id, str) or not cycle_id.startswith("human-remediation-reopen::"):
            raise ValueError("confirmed genuine regression requires deterministic new-cycle identity")

    expected = {key: value for key, value in adjudication.items() if key != "decision_sha256"}
    if adjudication["decision_sha256"] != _stable_sha256(expected):
        raise ValueError("reopen adjudication decision digest mismatch")


def validate_reopen_adjudication_ledger(ledger: dict[str, Any]) -> None:
    if ledger.get("ledger_version") != REOPEN_ADJUDICATION_LEDGER_VERSION:
        raise ValueError("unsupported Human remediation reopen adjudication ledger version")
    policy = ledger.get("policy")
    required = {
        "explicit_owner_adjudication_required": True,
        "fresh_checkpoint_required_for_regression": True,
        "administrative_reopen_preserves_terminal_closed": True,
        "automatic_new_cycle_creation": False,
        "production_code_mutation": False,
        "execution_authorized": False,
    }
    if not isinstance(policy, dict):
        raise ValueError("reopen adjudication ledger policy is required")
    for key, expected in required.items():
        if policy.get(key) != expected:
            raise ValueError(f"reopen adjudication ledger policy mismatch: {key}")
    rows = ledger.get("adjudications")
    if not isinstance(rows, list):
        raise ValueError("reopen adjudication ledger entries must be a list")
    event_keys: set[str] = set()
    fingerprints: set[str] = set()
    for sequence, row in enumerate(rows, start=1):
        if not isinstance(row, dict) or row.get("sequence") != sequence:
            raise ValueError("reopen adjudication sequence must be contiguous")
        validate_reopen_adjudication(row)
        if row["reopen_event_key"] in event_keys:
            raise ValueError("duplicate reopen event adjudication")
        if row["proposal_fingerprint"] in fingerprints:
            raise ValueError("duplicate proposal reopen adjudication")
        event_keys.add(row["reopen_event_key"])
        fingerprints.add(row["proposal_fingerprint"])


def register_reopen_adjudication(
    ledger: dict[str, Any], adjudication: dict[str, Any]
) -> tuple[dict[str, Any], str]:
    validate_reopen_adjudication_ledger(ledger)
    validate_reopen_adjudication(adjudication)
    existing = next(
        (
            row
            for row in ledger["adjudications"]
            if row["reopen_event_key"] == adjudication["reopen_event_key"]
            or row["proposal_fingerprint"] == adjudication["proposal_fingerprint"]
        ),
        None,
    )
    if existing is not None:
        expected = {key: value for key, value in existing.items() if key != "sequence"}
        if expected == adjudication:
            return ledger, "UNCHANGED"
        raise ValueError("reopen event already has a conflicting adjudication")
    updated = deepcopy(ledger)
    updated["adjudications"].append(
        {"sequence": len(updated["adjudications"]) + 1, **deepcopy(adjudication)}
    )
    validate_reopen_adjudication_ledger(updated)
    return updated, "APPENDED"


def reopen_adjudication_summary(
    ledger: dict[str, Any], terminal_report: dict[str, Any] | None = None
) -> dict[str, Any]:
    validate_reopen_adjudication_ledger(ledger)
    rows = ledger["adjudications"]
    adjudicated_events = {row["reopen_event_key"] for row in rows}
    pending: list[dict[str, Any]] = []
    if terminal_report is not None:
        _validate_terminal_report(terminal_report)
        for item in terminal_report.get("inconsistencies", []):
            if item.get("consistency") != "REOPENED_INCONSISTENCY":
                continue
            event_key = _reopen_event_key(item)
            if event_key not in adjudicated_events:
                pending.append(
                    {
                        "reopen_event_key": event_key,
                        "proposal_fingerprint": item["proposal_fingerprint"],
                        "failure_code": item["failure_code"],
                        "service": item.get("service"),
                        "issue_number": item["issue_number"],
                        "issue_url": item["issue_url"],
                    }
                )
    administrative = [row for row in rows if row["classification"] == ADMINISTRATIVE_NON_QUALITY]
    regressions = [row for row in rows if row["classification"] == GENUINE_HUMAN_QUALITY_REGRESSION]
    return {
        "ledger_version": REOPEN_ADJUDICATION_LEDGER_VERSION,
        "adjudication_count": len(rows),
        "pending_adjudication_count": len(pending),
        "administrative_count": len(administrative),
        "confirmed_regression_count": len(regressions),
        "new_cycle_eligible_count": sum(1 for row in rows if row["new_cycle_eligible"]),
        "pending": pending,
        "adjudications": deepcopy(rows),
        "explicit_owner_adjudication_required": True,
        "fresh_checkpoint_required_for_regression": True,
        "automatic_new_cycle_creation": False,
        "production_code_mutation": False,
        "execution_authorized": False,
    }


def build_new_cycle_seed(ledger: dict[str, Any], *, fingerprint: str) -> dict[str, Any]:
    validate_reopen_adjudication_ledger(ledger)
    row = next(
        (item for item in ledger["adjudications"] if item["proposal_fingerprint"] == fingerprint),
        None,
    )
    if row is None:
        raise ValueError("reopen event has not been adjudicated")
    if row["classification"] != GENUINE_HUMAN_QUALITY_REGRESSION or row["new_cycle_eligible"] is not True:
        raise ValueError("reopen adjudication is not eligible to begin a new remediation cycle")
    evidence = row["fresh_regression_evidence"]
    return {
        "seed_version": REOPEN_CYCLE_SEED_VERSION,
        "new_cycle_id": row["new_cycle_id"],
        "prior_proposal_fingerprint": row["proposal_fingerprint"],
        "reopen_event_key": row["reopen_event_key"],
        "closure_evidence_key": row["closure_evidence_key"],
        "issue_number": row["issue_number"],
        "issue_url": row["issue_url"],
        "failure_code": row["failure_code"],
        "service": row.get("service"),
        "fresh_checkpoint_id": evidence["checkpoint_id"],
        "fresh_checkpoint_sequence": evidence["checkpoint_sequence"],
        "targeted_failure_count": evidence["targeted_failure_count"],
        "targeted_failure_rate": evidence["targeted_failure_rate"],
        "adjudicated_by": row["adjudicated_by"],
        "new_cycle_eligible": True,
        "automatic_new_cycle_creation": False,
        "production_code_mutation": False,
        "execution_authorized": False,
    }


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("expected JSON object")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="roberta-eval-human-reopen")
    parser.add_argument("--ledger", default=None)
    parser.add_argument("--checkpoint-history", default=None)
    sub = parser.add_subparsers(dest="command", required=True)

    summary = sub.add_parser("summary", help="summarize reopen adjudications")
    summary.add_argument("--terminal-report", default=None)

    adjudicate = sub.add_parser("adjudicate", help="explicitly classify a REOPENED_INCONSISTENCY")
    adjudicate.add_argument("--terminal-report", required=True)
    adjudicate.add_argument("--fingerprint", required=True)
    adjudicate.add_argument("--owner", required=True)
    adjudicate.add_argument("--classification", required=True, choices=CLASSIFICATIONS)
    adjudicate.add_argument("--checkpoint-id", default=None)
    adjudicate.add_argument("--approve", action="store_true", required=True)

    seed = sub.add_parser("cycle-seed", help="emit an eligible new-cycle seed without mutating lifecycle")
    seed.add_argument("--fingerprint", required=True)

    args = parser.parse_args(argv)
    ledger_path = Path(args.ledger) if args.ledger else default_reopen_adjudication_ledger_path()
    ledger = load_reopen_adjudication_ledger(ledger_path)

    if args.command == "summary":
        report = _load_json(Path(args.terminal_report)) if args.terminal_report else None
        payload = reopen_adjudication_summary(ledger, report)
    elif args.command == "cycle-seed":
        payload = build_new_cycle_seed(ledger, fingerprint=args.fingerprint)
    else:
        history = load_human_checkpoint_history(
            Path(args.checkpoint_history) if args.checkpoint_history else default_human_checkpoint_history_path()
        )
        adjudication = build_reopen_adjudication(
            _load_json(Path(args.terminal_report)),
            history,
            fingerprint=args.fingerprint,
            owner=args.owner,
            classification=args.classification,
            approved=args.approve,
            checkpoint_id=args.checkpoint_id,
        )
        updated, status = register_reopen_adjudication(ledger, adjudication)
        if updated != ledger:
            write_reopen_adjudication_ledger(ledger_path, updated)
        payload = {
            "status": status,
            "adjudication": adjudication,
            "summary": reopen_adjudication_summary(updated),
        }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
