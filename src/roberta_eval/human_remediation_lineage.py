from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .human_remediation_lifecycle import (
    default_lifecycle_path,
    load_lifecycle,
    validate_lifecycle,
)
from .human_remediation_reopen_cycle import (
    REOPEN_CHILD_ORIGIN,
    default_reopen_cycle_promotion_ledger_path,
    load_reopen_cycle_promotion_ledger,
    validate_reopen_cycle_promotion_ledger,
)

GENERATIONAL_LINEAGE_VERSION = "roberta_human_remediation_generational_lineage_reconciliation/v1"
LINEAGE_HEALTH_VERSION = "roberta_human_remediation_lineage_health/v1"

STABLE_ROOT = "STABLE_ROOT"
RECURRENCE_OBSERVED = "RECURRENCE_OBSERVED"
ROOT_CAUSE_WARNING = "ROOT_CAUSE_WARNING"
CHRONIC_REGRESSION = "CHRONIC_REGRESSION"
HEALTH_STATES = (
    STABLE_ROOT,
    RECURRENCE_OBSERVED,
    ROOT_CAUSE_WARNING,
    CHRONIC_REGRESSION,
)


def _stable_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _health_for_depth(depth: int) -> str:
    if depth <= 0:
        return STABLE_ROOT
    if depth == 1:
        return RECURRENCE_OBSERVED
    if depth == 2:
        return ROOT_CAUSE_WARNING
    return CHRONIC_REGRESSION


def _record_index(lifecycle: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {record["proposal_fingerprint"]: record for record in lifecycle["records"]}


def _validate_child_against_promotion(
    *,
    child: dict[str, Any],
    parent: dict[str, Any],
    promotion: dict[str, Any],
) -> None:
    child_fp = child["proposal_fingerprint"]
    parent_fp = parent["proposal_fingerprint"]
    if child_fp == parent_fp:
        raise ValueError("Human remediation lineage cannot self-parent")
    if child.get("origin_kind") != REOPEN_CHILD_ORIGIN:
        raise ValueError("reopen promotion child lifecycle origin is invalid")
    lineage = child.get("lineage")
    if not isinstance(lineage, dict):
        raise ValueError("reopen promotion child lifecycle lineage is missing")

    expected = {
        "parent_proposal_fingerprint": parent_fp,
        "parent_lifecycle_id": parent["lifecycle_id"],
        "child_proposal_fingerprint": child_fp,
        "child_lifecycle_id": child["lifecycle_id"],
        "new_cycle_id": promotion["new_cycle_id"],
        "closure_evidence_key": promotion["closure_evidence_key"],
        "reopen_event_key": promotion["reopen_event_key"],
        "failure_code": promotion["failure_code"],
        "fresh_checkpoint_id": promotion["fresh_checkpoint_id"],
        "fresh_checkpoint_sequence": promotion["fresh_checkpoint_sequence"],
        "targeted_failure_count": promotion["targeted_failure_count"],
        "targeted_failure_rate": promotion["targeted_failure_rate"],
        "adjudicated_by": promotion["adjudicated_by"],
        "cycle_promoted_by": promotion["approved_by"],
    }
    for key, value in expected.items():
        if lineage.get(key) != value:
            raise ValueError(f"Human remediation lineage evidence mismatch: {key}")

    if promotion["parent_lifecycle_id"] != parent["lifecycle_id"]:
        raise ValueError("reopen promotion parent lifecycle identity mismatch")
    if promotion["child_lifecycle_id"] != child["lifecycle_id"]:
        raise ValueError("reopen promotion child lifecycle identity mismatch")
    if promotion["child_proposal_sha256"] != child["proposal_sha256"]:
        raise ValueError("reopen promotion child proposal digest mismatch")

    if parent["failure_code"] != child["failure_code"] or child["failure_code"] != promotion["failure_code"]:
        raise ValueError("Human remediation generational lineage failure-code drift")
    if parent.get("service") != child.get("service") or child.get("service") != promotion.get("service"):
        raise ValueError("Human remediation generational lineage service drift")
    if child.get("recurrence") != "RECURRENT":
        raise ValueError("reopen child remediation must remain RECURRENT")


def _build_parent_map(
    lifecycle: dict[str, Any],
    promotion_ledger: dict[str, Any],
) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    records = _record_index(lifecycle)
    parent_of: dict[str, str] = {}
    promotion_for_child: dict[str, dict[str, Any]] = {}

    for promotion in promotion_ledger["promotions"]:
        parent_fp = promotion["parent_proposal_fingerprint"]
        child_fp = promotion["child_proposal_fingerprint"]
        parent = records.get(parent_fp)
        child = records.get(child_fp)
        if parent is None:
            raise ValueError("Human remediation lineage references a missing parent lifecycle")
        if child is None:
            raise ValueError("Human remediation lineage references a missing child lifecycle")
        if child_fp in parent_of and parent_of[child_fp] != parent_fp:
            raise ValueError("Human remediation child has conflicting parentage")
        if child_fp in promotion_for_child:
            raise ValueError("Human remediation child has duplicate lineage promotion evidence")
        _validate_child_against_promotion(child=child, parent=parent, promotion=promotion)
        parent_of[child_fp] = parent_fp
        promotion_for_child[child_fp] = promotion

    for record in lifecycle["records"]:
        if record.get("origin_kind") == REOPEN_CHILD_ORIGIN:
            child_fp = record["proposal_fingerprint"]
            if child_fp not in parent_of:
                raise ValueError("reopen child lifecycle is missing LAB #77 parent promotion evidence")
            lineage = record.get("lineage") or {}
            if lineage.get("parent_proposal_fingerprint") != parent_of[child_fp]:
                raise ValueError("reopen child lifecycle carries conflicting parent identity")

    return parent_of, promotion_for_child


def _assert_acyclic(records: dict[str, dict[str, Any]], parent_of: dict[str, str]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visited:
            return
        if node in visiting:
            raise ValueError("Human remediation generational lineage contains a cycle")
        visiting.add(node)
        parent = parent_of.get(node)
        if parent is not None:
            if parent not in records:
                raise ValueError("Human remediation lineage parent is missing")
            visit(parent)
        visiting.remove(node)
        visited.add(node)

    for fingerprint in records:
        visit(fingerprint)


def _generation_map(
    records: dict[str, dict[str, Any]], parent_of: dict[str, str]
) -> dict[str, int]:
    generations: dict[str, int] = {}

    def generation(node: str) -> int:
        if node in generations:
            return generations[node]
        parent = parent_of.get(node)
        value = 0 if parent is None else generation(parent) + 1
        generations[node] = value
        return value

    for fingerprint in records:
        generation(fingerprint)
    return generations


def _root_for(node: str, parent_of: dict[str, str]) -> str:
    current = node
    seen: set[str] = set()
    while current in parent_of:
        if current in seen:
            raise ValueError("Human remediation generational lineage contains a cycle")
        seen.add(current)
        current = parent_of[current]
    return current


def _path_to_root(node: str, parent_of: dict[str, str]) -> list[str]:
    reverse_path = [node]
    current = node
    seen: set[str] = set()
    while current in parent_of:
        if current in seen:
            raise ValueError("Human remediation generational lineage contains a cycle")
        seen.add(current)
        current = parent_of[current]
        reverse_path.append(current)
    reverse_path.reverse()
    return reverse_path


def build_generational_lineage_report(
    lifecycle: dict[str, Any],
    promotion_ledger: dict[str, Any],
) -> dict[str, Any]:
    validate_lifecycle(lifecycle)
    validate_reopen_cycle_promotion_ledger(promotion_ledger)
    records = _record_index(lifecycle)
    parent_of, promotion_for_child = _build_parent_map(lifecycle, promotion_ledger)
    _assert_acyclic(records, parent_of)
    generations = _generation_map(records, parent_of)

    children_by_parent: dict[str, list[str]] = defaultdict(list)
    for child, parent in parent_of.items():
        children_by_parent[parent].append(child)
    for children in children_by_parent.values():
        children.sort()

    families_by_root: dict[str, list[str]] = defaultdict(list)
    for fingerprint in records:
        families_by_root[_root_for(fingerprint, parent_of)].append(fingerprint)

    families: list[dict[str, Any]] = []
    repeat_regression_family_count = 0
    chronic_family_count = 0
    root_cause_warning_family_count = 0
    deepest_generation = 0

    for root_fp in sorted(families_by_root):
        members = sorted(families_by_root[root_fp], key=lambda fp: (generations[fp], fp))
        root = records[root_fp]
        max_generation = max(generations[fp] for fp in members)
        deepest_generation = max(deepest_generation, max_generation)
        repeat_regression_count = len(members) - 1
        health = _health_for_depth(max_generation)
        if repeat_regression_count >= 2:
            repeat_regression_family_count += 1
        if health in {ROOT_CAUSE_WARNING, CHRONIC_REGRESSION}:
            root_cause_warning_family_count += 1
        if health == CHRONIC_REGRESSION:
            chronic_family_count += 1

        leaves = [fp for fp in members if not children_by_parent.get(fp)]
        paths = []
        for leaf in sorted(leaves):
            path = _path_to_root(leaf, parent_of)
            paths.append(
                {
                    "leaf_proposal_fingerprint": leaf,
                    "depth": generations[leaf],
                    "proposal_fingerprints": path,
                    "lifecycle_ids": [records[fp]["lifecycle_id"] for fp in path],
                    "statuses": [records[fp]["status"] for fp in path],
                }
            )

        nodes = []
        for fp in members:
            record = records[fp]
            promotion = promotion_for_child.get(fp)
            stored_generation = None
            lineage = record.get("lineage")
            if isinstance(lineage, dict) and "generation" in lineage:
                stored_generation = lineage.get("generation")
                if not isinstance(stored_generation, int) or stored_generation != generations[fp]:
                    raise ValueError("stored Human remediation lineage generation conflicts with derived generation")
            nodes.append(
                {
                    "proposal_fingerprint": fp,
                    "lifecycle_id": record["lifecycle_id"],
                    "generation": generations[fp],
                    "parent_proposal_fingerprint": parent_of.get(fp),
                    "status": record["status"],
                    "failure_code": record["failure_code"],
                    "service": record.get("service"),
                    "issue_number": record.get("issue_number"),
                    "reopen_event_key": promotion.get("reopen_event_key") if promotion else None,
                    "fresh_checkpoint_id": promotion.get("fresh_checkpoint_id") if promotion else None,
                }
            )

        families.append(
            {
                "root_proposal_fingerprint": root_fp,
                "root_lifecycle_id": root["lifecycle_id"],
                "failure_code": root["failure_code"],
                "service": root.get("service"),
                "node_count": len(members),
                "repeat_regression_count": repeat_regression_count,
                "deepest_generation": max_generation,
                "health": health,
                "root_cause_warning": health in {ROOT_CAUSE_WARNING, CHRONIC_REGRESSION},
                "root_cause_interpretation": (
                    "Repeated accepted recurrence indicates a remediation-loop risk; it does not by itself prove the underlying causal root cause."
                    if health in {ROOT_CAUSE_WARNING, CHRONIC_REGRESSION}
                    else None
                ),
                "nodes": nodes,
                "paths": paths,
            }
        )

    health_counts = Counter(family["health"] for family in families)
    report_core = {
        "lineage_version": GENERATIONAL_LINEAGE_VERSION,
        "health_version": LINEAGE_HEALTH_VERSION,
        "family_count": len(families),
        "lineage_node_count": len(records),
        "reopen_edge_count": len(parent_of),
        "deepest_generation": deepest_generation,
        "repeat_regression_family_count": repeat_regression_family_count,
        "root_cause_warning_family_count": root_cause_warning_family_count,
        "chronic_family_count": chronic_family_count,
        "health_counts": {state: int(health_counts.get(state, 0)) for state in HEALTH_STATES},
        "families": families,
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
    report_core["report_sha256"] = _stable_sha256(report_core)
    return report_core


def validate_generational_lineage_report(report: dict[str, Any]) -> None:
    if report.get("lineage_version") != GENERATIONAL_LINEAGE_VERSION:
        raise ValueError("unsupported Human remediation generational lineage version")
    if report.get("health_version") != LINEAGE_HEALTH_VERSION:
        raise ValueError("unsupported Human remediation lineage health version")
    for key in (
        "acyclic",
        "one_parent_per_child",
        "generation_integrity",
        "failure_service_integrity",
        "read_only",
        "advisory_pattern_interpretation",
    ):
        if report.get(key) is not True:
            raise ValueError(f"Human remediation lineage report invariant failed: {key}")
    if report.get("automatic_issue_creation") is not False:
        raise ValueError("Human remediation lineage reconciliation cannot create issues")
    if report.get("lifecycle_mutation") is not False:
        raise ValueError("Human remediation lineage reconciliation cannot mutate lifecycle")
    if report.get("production_code_mutation") is not False or report.get("execution_authorized") is not False:
        raise ValueError("Human remediation lineage reconciliation exceeds authority boundary")
    families = report.get("families")
    if not isinstance(families, list):
        raise ValueError("Human remediation lineage families must be a list")
    expected = {key: value for key, value in report.items() if key != "report_sha256"}
    digest = report.get("report_sha256")
    if not isinstance(digest, str) or len(digest) != 64 or digest != _stable_sha256(expected):
        raise ValueError("Human remediation lineage report digest mismatch")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="roberta-eval-human-lineage")
    parser.add_argument("--lifecycle", default=None)
    parser.add_argument("--reopen-cycle-ledger", default=None)
    parser.add_argument("command", choices=("report", "validate"), nargs="?", default="report")
    args = parser.parse_args(argv)

    lifecycle = load_lifecycle(Path(args.lifecycle) if args.lifecycle else default_lifecycle_path())
    ledger = load_reopen_cycle_promotion_ledger(
        Path(args.reopen_cycle_ledger)
        if args.reopen_cycle_ledger
        else default_reopen_cycle_promotion_ledger_path()
    )
    report = build_generational_lineage_report(lifecycle, ledger)
    if args.command == "validate":
        validate_generational_lineage_report(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
