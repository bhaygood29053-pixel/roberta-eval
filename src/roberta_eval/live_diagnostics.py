from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .live import LIVE_GRADE_VERSION


DIAGNOSTICS_VERSION = "roberta_live_qualification_diagnostics/v1"

_PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}

_REASON_RULES: dict[str, dict[str, Any]] = {
    "runtime_failure": {
        "diagnostic_class": "runtime_transport_failure",
        "owner_repository": "bhaygood29053-pixel/roberta-langgraph",
        "component": "roberta_bridge_runtime",
        "priority": "P0",
        "qualification_blocking": True,
        "product_defect_candidate": True,
        "recommended_action": (
            "Verify the accepted ROBERTA bridge/runtime pair, restart the local "
            "bridge from synchronized public/protected sources, and rerun the "
            "same live case before investigating service-specific evidence."
        ),
    },
    "response_unavailable": {
        "diagnostic_class": "public_bridge_telemetry_contract_gap",
        "owner_repository": "bhaygood29053-pixel/roberta-langgraph",
        "component": "evaluation_telemetry_projection",
        "priority": "P1",
        "qualification_blocking": True,
        "product_defect_candidate": False,
        "recommended_action": "Restore a structured ROBERTA evaluation response before grading claims.",
    },
    "evaluation_telemetry_version_unavailable": {
        "diagnostic_class": "public_bridge_telemetry_contract_gap",
        "owner_repository": "bhaygood29053-pixel/roberta-langgraph",
        "component": "evaluation_telemetry_projection",
        "priority": "P1",
        "qualification_blocking": True,
        "product_defect_candidate": False,
        "recommended_action": "Expose the accepted roberta_evaluation_telemetry/v1 contract on the live bridge.",
    },
    "evaluation_evidence_unavailable": {
        "diagnostic_class": "public_bridge_telemetry_contract_gap",
        "owner_repository": "bhaygood29053-pixel/roberta-langgraph",
        "component": "evaluation_telemetry_projection",
        "priority": "P1",
        "qualification_blocking": True,
        "product_defect_candidate": False,
        "recommended_action": "Restore whitelisted accepted final-message evidence in the evaluation projection.",
    },
    "current_x1_evidence_unavailable": {
        "diagnostic_class": "current_x1_evidence_delegation_gap",
        "owner_repository": "bhaygood29053-pixel/roberta-core",
        "component": "roberta_oracle_evidence_delegation",
        "priority": "P1",
        "qualification_blocking": True,
        "product_defect_candidate": True,
        "recommended_action": (
            "Require a current-turn X1 Scout result before ROBERTA can finish an "
            "explicit current/verified X1 evidence request; retry once and fail "
            "closed if delegation is still missing."
        ),
    },
    "canonical_claims_unavailable": {
        "diagnostic_class": "canonical_claim_coverage_gap",
        "owner_repository": "bhaygood29053-pixel/roberta-langgraph",
        "component": "evaluation_canonical_claim_projection",
        "priority": "P1",
        "qualification_blocking": True,
        "product_defect_candidate": False,
        "recommended_action": "Expose canonical claims from accepted final structures without parsing prose.",
    },
    "canonical_claims_empty": {
        "diagnostic_class": "canonical_claim_coverage_gap",
        "owner_repository": "bhaygood29053-pixel/roberta-langgraph",
        "component": "evaluation_canonical_claim_projection",
        "priority": "P1",
        "qualification_blocking": True,
        "product_defect_candidate": False,
        "recommended_action": "Add claim projection coverage for the affected accepted service/workflow.",
    },
    "material_claim_coverage_missing": {
        "diagnostic_class": "canonical_claim_relevance_gap",
        "owner_repository": "bhaygood29053-pixel/roberta-langgraph",
        "component": "evaluation_canonical_claim_projection",
        "priority": "P1",
        "qualification_blocking": True,
        "product_defect_candidate": False,
        "recommended_action": (
            "Project canonical claims that cover the material facts for the "
            "requested service before using the live result for qualification."
        ),
    },
    "canonical_claim_invalid": {
        "diagnostic_class": "canonical_claim_coverage_gap",
        "owner_repository": "bhaygood29053-pixel/roberta-langgraph",
        "component": "evaluation_canonical_claim_projection",
        "priority": "P1",
        "qualification_blocking": True,
        "product_defect_candidate": True,
        "recommended_action": "Repair malformed canonical claim projection and add a service-specific regression.",
    },
    "claim_evidence_path_unavailable": {
        "diagnostic_class": "canonical_claim_coverage_gap",
        "owner_repository": "bhaygood29053-pixel/roberta-langgraph",
        "component": "evaluation_canonical_claim_projection",
        "priority": "P1",
        "qualification_blocking": True,
        "product_defect_candidate": True,
        "recommended_action": "Bind every projected canonical claim to one explicit evaluation_evidence path.",
    },
    "claim_evidence_path_not_found": {
        "diagnostic_class": "canonical_claim_coverage_gap",
        "owner_repository": "bhaygood29053-pixel/roberta-langgraph",
        "component": "evaluation_canonical_claim_projection",
        "priority": "P1",
        "qualification_blocking": True,
        "product_defect_candidate": True,
        "recommended_action": "Repair claim-to-evidence path projection and preserve the failing case as a regression.",
    },
    "evidence_provenance_unavailable": {
        "diagnostic_class": "evidence_metadata_gap",
        "owner_repository": "bhaygood29053-pixel/roberta-langgraph",
        "component": "evaluation_evidence_metadata",
        "priority": "P2",
        "qualification_blocking": True,
        "product_defect_candidate": False,
        "recommended_action": "Expose facts/judgment authority and accepted source-contract provenance.",
    },
    "evidence_freshness_unavailable": {
        "diagnostic_class": "evidence_metadata_gap",
        "owner_repository": "bhaygood29053-pixel/roberta-langgraph",
        "component": "evaluation_evidence_metadata",
        "priority": "P2",
        "qualification_blocking": True,
        "product_defect_candidate": False,
        "recommended_action": "Expose bounded freshness state from the accepted final decision evidence.",
    },
    "execution_flag_unavailable": {
        "diagnostic_class": "public_bridge_telemetry_contract_gap",
        "owner_repository": "bhaygood29053-pixel/roberta-langgraph",
        "component": "evaluation_execution_boundary_projection",
        "priority": "P0",
        "qualification_blocking": True,
        "product_defect_candidate": True,
        "recommended_action": "Restore the explicit execution_authorized=false evaluation boundary.",
    },
    "claim_integrity_unavailable": {
        "diagnostic_class": "protected_claim_integrity_gap",
        "owner_repository": "bhaygood29053-pixel/roberta-core",
        "component": "claim_integrity_runtime",
        "priority": "P1",
        "qualification_blocking": True,
        "product_defect_candidate": False,
        "recommended_action": "Extend protected Claim Integrity coverage to the affected accepted workflow.",
    },
    "claim_integrity_contract_unavailable": {
        "diagnostic_class": "protected_claim_integrity_gap",
        "owner_repository": "bhaygood29053-pixel/roberta-core",
        "component": "claim_integrity_runtime",
        "priority": "P1",
        "qualification_blocking": True,
        "product_defect_candidate": True,
        "recommended_action": "Restore the accepted roberta_claim_integrity/v1 contract on the final response.",
    },
    "claim_integrity_not_pass": {
        "diagnostic_class": "protected_claim_integrity_failure",
        "owner_repository": "bhaygood29053-pixel/roberta-core",
        "component": "claim_integrity_runtime",
        "priority": "P0",
        "qualification_blocking": True,
        "product_defect_candidate": True,
        "recommended_action": "Inspect the protected Claim Integrity rejection and fix the first unsupported claim path.",
    },
    "canonical_claim_disagrees_with_evidence": {
        "diagnostic_class": "claim_evidence_mismatch",
        "owner_repository": "bhaygood29053-pixel/roberta-langgraph",
        "component": "evaluation_canonical_claim_projection",
        "priority": "P0",
        "qualification_blocking": True,
        "product_defect_candidate": True,
        "recommended_action": "Fix the exact claim/evidence mismatch and preserve the case as a permanent regression.",
    },
    "execution_boundary_violated": {
        "diagnostic_class": "execution_boundary_violation",
        "owner_repository": "bhaygood29053-pixel/roberta-core",
        "component": "final_response_execution_boundary",
        "priority": "P0",
        "qualification_blocking": True,
        "product_defect_candidate": True,
        "recommended_action": "Block release, restore execution_authorized=false, and add a permanent critical regression.",
    },
}


def load_live_grades(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def validate_live_grades(results: list[dict[str, Any]]) -> None:
    if not isinstance(results, list) or not results:
        raise ValueError("live diagnostics require at least one live-grade result")
    seen: set[str] = set()
    for index, result in enumerate(results):
        if result.get("live_grader_version") != LIVE_GRADE_VERSION:
            raise ValueError(f"result[{index}] is not a LAB #21 live-grade record")
        verdict = result.get("verdict")
        if verdict not in {"PASS", "EVIDENCE_REQUIRED", "FAIL"}:
            raise ValueError(f"result[{index}] has unsupported live verdict")
        record_id = result.get("record_id")
        stable_id = str(record_id or result.get("case_id") or f"index:{index}")
        if stable_id in seen:
            raise ValueError(f"duplicate live-grade record identity: {stable_id}")
        seen.add(stable_id)


def _rule(reason: str) -> dict[str, Any]:
    if reason in _REASON_RULES:
        return dict(_REASON_RULES[reason])
    return {
        "diagnostic_class": "unclassified_live_grade_reason",
        "owner_repository": "bhaygood29053-pixel/roberta-eval",
        "component": "live_diagnostics",
        "priority": "P2",
        "qualification_blocking": True,
        "product_defect_candidate": False,
        "recommended_action": "Add an explicit deterministic LAB #22 rule before assigning product ownership.",
    }


def diagnose_live_grades(results: list[dict[str, Any]]) -> dict[str, Any]:
    validate_live_grades(results)

    verdict_counts = Counter(str(result["verdict"]) for result in results)
    by_service: dict[str, list[dict[str, Any]]] = defaultdict(list)
    grouped: dict[tuple[str, str, str, str, bool], dict[str, Any]] = {}

    for result in results:
        service = str(result.get("service") or "unknown")
        by_service[service].append(result)

        if result["verdict"] == "PASS":
            continue

        reason = str(result.get("reason") or "unknown_reason")
        rule = _rule(reason)
        key = (
            reason,
            rule["owner_repository"],
            rule["component"],
            rule["priority"],
            bool(rule["qualification_blocking"]),
        )
        group = grouped.setdefault(
            key,
            {
                "reason": reason,
                **rule,
                "occurrence_count": 0,
                "affected_services": set(),
                "case_ids": [],
                "verdict_counts": Counter(),
            },
        )
        group["occurrence_count"] += 1
        group["affected_services"].add(service)
        if result.get("case_id") is not None:
            group["case_ids"].append(str(result["case_id"]))
        group["verdict_counts"][str(result["verdict"])] += 1

    service_summaries = []
    for service in sorted(by_service):
        rows = by_service[service]
        counts = Counter(str(row["verdict"]) for row in rows)
        reasons = Counter(
            str(row.get("reason") or "unknown_reason")
            for row in rows
            if row["verdict"] != "PASS"
        )
        service_summaries.append(
            {
                "service": service,
                "result_count": len(rows),
                "verdict_counts": {
                    verdict: counts.get(verdict, 0)
                    for verdict in ("PASS", "EVIDENCE_REQUIRED", "FAIL")
                },
                "reason_counts": dict(sorted(reasons.items())),
                "fully_gradeable": all(row["verdict"] != "EVIDENCE_REQUIRED" for row in rows),
                "all_pass": bool(rows) and all(row["verdict"] == "PASS" for row in rows),
            }
        )

    remediation_groups: list[dict[str, Any]] = []
    for group in grouped.values():
        remediation_groups.append(
            {
                **{
                    key: value
                    for key, value in group.items()
                    if key not in {"affected_services", "case_ids", "verdict_counts"}
                },
                "affected_services": sorted(group["affected_services"]),
                "case_ids": sorted(set(group["case_ids"])),
                "verdict_counts": {
                    verdict: group["verdict_counts"].get(verdict, 0)
                    for verdict in ("EVIDENCE_REQUIRED", "FAIL")
                },
            }
        )

    remediation_groups.sort(
        key=lambda group: (
            _PRIORITY_ORDER.get(str(group["priority"]), 99),
            0 if group["product_defect_candidate"] else 1,
            str(group["reason"]),
            str(group["owner_repository"]),
        )
    )

    fail_count = verdict_counts.get("FAIL", 0)
    evidence_required_count = verdict_counts.get("EVIDENCE_REQUIRED", 0)
    pass_count = verdict_counts.get("PASS", 0)

    return {
        "diagnostics_version": DIAGNOSTICS_VERSION,
        "input_live_grader_version": LIVE_GRADE_VERSION,
        "result_count": len(results),
        "verdict_counts": {
            "PASS": pass_count,
            "EVIDENCE_REQUIRED": evidence_required_count,
            "FAIL": fail_count,
        },
        "service_summaries": service_summaries,
        "remediation_groups": remediation_groups,
        "qualification_blocking": bool(fail_count or evidence_required_count),
        "actual_live_failures_present": bool(fail_count),
        "evidence_gaps_present": bool(evidence_required_count),
        "product_defect_candidate_count": sum(
            group["occurrence_count"]
            for group in remediation_groups
            if group["product_defect_candidate"]
        ),
        "recommended_next_group": remediation_groups[0] if remediation_groups else None,
        "provider_truth_certified": False,
        "all_natural_language_claims_certified": False,
    }


def render_diagnostics_markdown(report: dict[str, Any]) -> str:
    counts = report["verdict_counts"]
    lines = [
        "# ROBERTA Live Qualification Diagnostics",
        "",
        f"Contract: `{report['diagnostics_version']}`",
        "",
        "## Verdicts",
        "",
        f"- PASS: {counts['PASS']}",
        f"- EVIDENCE_REQUIRED: {counts['EVIDENCE_REQUIRED']}",
        f"- FAIL: {counts['FAIL']}",
        "",
        "## Service coverage",
        "",
        "| Service | PASS | EVIDENCE_REQUIRED | FAIL | Fully gradeable |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for item in report["service_summaries"]:
        verdicts = item["verdict_counts"]
        lines.append(
            f"| {item['service']} | {verdicts['PASS']} | "
            f"{verdicts['EVIDENCE_REQUIRED']} | {verdicts['FAIL']} | "
            f"{str(item['fully_gradeable']).lower()} |"
        )

    lines.extend(["", "## Remediation priority", ""])
    if not report["remediation_groups"]:
        lines.append("No remediation groups. All supplied live grades passed.")
    else:
        for index, group in enumerate(report["remediation_groups"], start=1):
            lines.extend(
                [
                    f"### {index}. {group['priority']} — {group['reason']}",
                    "",
                    f"- Class: `{group['diagnostic_class']}`",
                    f"- Owner: `{group['owner_repository']}`",
                    f"- Component: `{group['component']}`",
                    f"- Occurrences: {group['occurrence_count']}",
                    f"- Services: {', '.join(group['affected_services'])}",
                    f"- Qualification blocking: {str(group['qualification_blocking']).lower()}",
                    f"- Product defect candidate: {str(group['product_defect_candidate']).lower()}",
                    f"- Next action: {group['recommended_action']}",
                    "",
                ]
            )

    lines.extend(
        [
            "## Qualification boundary",
            "",
            "This report diagnoses LAB #21 structured live-grade results only. "
            "EVIDENCE_REQUIRED is not a ROBERTA factual failure. A PASS does not "
            "certify upstream provider truth or every natural-language sentence.",
            "",
        ]
    )
    return "\n".join(lines)


def write_diagnostics_json(path: Path, report: dict[str, Any]) -> None:
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_diagnostics_markdown(path: Path, report: dict[str, Any]) -> None:
    path.write_text(render_diagnostics_markdown(report), encoding="utf-8")
