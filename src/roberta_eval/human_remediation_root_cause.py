from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from .human_remediation_lineage import (
    CHRONIC_REGRESSION,
    ROOT_CAUSE_WARNING,
    build_generational_lineage_report,
    validate_generational_lineage_report,
)
from .human_remediation_lifecycle import default_lifecycle_path, load_lifecycle
from .human_remediation_reopen_cycle import (
    default_reopen_cycle_promotion_ledger_path,
    load_reopen_cycle_promotion_ledger,
)

ROOT_CAUSE_INVESTIGATION_VERSION = "roberta_human_remediation_root_cause_investigation/v1"
ROOT_CAUSE_EVIDENCE_VERSION = "roberta_human_remediation_root_cause_evidence/v1"
ROOT_CAUSE_FINDING_VERSION = "roberta_human_remediation_root_cause_finding/v1"
ROOT_CAUSE_LEDGER_VERSION = "roberta_human_remediation_root_cause_ledger/v1"
ROOT_CAUSE_DISPOSITION_VERSION = "roberta_human_remediation_root_cause_disposition/v1"
ROOT_CAUSE_SUFFICIENCY_GATE_VERSION = "roberta_human_remediation_root_cause_sufficiency_gate/v1"

DOMAINS = (
    "renderer",
    "policy",
    "prompt",
    "service_adapter",
    "vocabulary_replacement",
    "shared_human_layer",
)
DIRECTIONS = {"SUPPORTS", "CONTRADICTS", "NEUTRAL"}
STRENGTHS = {"DIRECT", "INDIRECT"}
FINDING_STATES = {
    "CONFIRMED_ROOT_CAUSE",
    "SUSPECTED",
    "INCONCLUSIVE",
    "RULED_OUT",
}
INVESTIGATION_REQUIRED_HEALTH = {ROOT_CAUSE_WARNING, CHRONIC_REGRESSION}
DISPOSITION_MODES = {
    "CONFIRMED_ROOT_CAUSE_ADDRESSED",
    "LEADING_FINDINGS_ADDRESSED",
}


def _stable_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def default_root_cause_ledger_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "human_remediation_root_cause_ledger.json"


def empty_root_cause_ledger() -> dict[str, Any]:
    return {
        "ledger_version": ROOT_CAUSE_LEDGER_VERSION,
        "policy": {
            "generation_2_plus_investigation_required": True,
            "root_cause_claims_require_evidence": True,
            "explicit_owner_disposition_required": True,
            "symptom_fix_alone_sufficient": False,
            "replay_success_alone_sufficient": False,
            "automatic_issue_creation": False,
            "production_code_mutation": False,
            "execution_authorized": False,
        },
        "investigations": [],
        "dispositions": [],
    }


def load_root_cause_ledger(path: Path | None = None) -> dict[str, Any]:
    source = path or default_root_cause_ledger_path()
    payload = json.loads(source.read_text(encoding="utf-8"))
    validate_root_cause_ledger(payload)
    return payload


def write_root_cause_ledger(path: Path, ledger: dict[str, Any]) -> None:
    validate_root_cause_ledger(ledger)
    path.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _family(lineage_report: dict[str, Any], root_fingerprint: str) -> dict[str, Any]:
    validate_generational_lineage_report(lineage_report)
    family = next(
        (
            item
            for item in lineage_report["families"]
            if item["root_proposal_fingerprint"] == root_fingerprint
        ),
        None,
    )
    if family is None:
        raise ValueError("Human remediation root-cause family was not found")
    return family


def _family_for_fingerprint(lineage_report: dict[str, Any], fingerprint: str) -> dict[str, Any]:
    validate_generational_lineage_report(lineage_report)
    matches = [
        family
        for family in lineage_report["families"]
        if any(node["proposal_fingerprint"] == fingerprint for node in family["nodes"])
    ]
    if len(matches) != 1:
        raise ValueError("Human remediation fingerprint must belong to exactly one lineage family")
    return matches[0]


def _family_sha(family: dict[str, Any]) -> str:
    return _stable_sha256(family)


def normalize_evidence_item(
    item: dict[str, Any],
    *,
    family: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise ValueError("root-cause evidence item must be an object")
    domain = item.get("domain")
    direction = item.get("direction")
    strength = item.get("strength")
    generation = item.get("generation")
    source_ref = item.get("source_ref")
    statement = item.get("statement")
    if domain not in DOMAINS:
        raise ValueError("root-cause evidence domain is invalid")
    if direction not in DIRECTIONS:
        raise ValueError("root-cause evidence direction is invalid")
    if strength not in STRENGTHS:
        raise ValueError("root-cause evidence strength is invalid")
    valid_generations = {int(node["generation"]) for node in family["nodes"]}
    if not isinstance(generation, int) or generation not in valid_generations:
        raise ValueError("root-cause evidence generation is not present in the accepted lineage")
    if not isinstance(source_ref, str) or not source_ref.strip():
        raise ValueError("root-cause evidence source_ref is required")
    if not isinstance(statement, str) or not statement.strip():
        raise ValueError("root-cause evidence statement is required")
    artifact_sha = item.get("artifact_sha256")
    if artifact_sha is not None and (
        not isinstance(artifact_sha, str) or len(artifact_sha) != 64
    ):
        raise ValueError("root-cause evidence artifact_sha256 is invalid")
    core = {
        "evidence_version": ROOT_CAUSE_EVIDENCE_VERSION,
        "family_root_fingerprint": family["root_proposal_fingerprint"],
        "failure_code": family["failure_code"],
        "service": family.get("service"),
        "domain": domain,
        "generation": generation,
        "direction": direction,
        "strength": strength,
        "source_ref": source_ref.strip(),
        "artifact_sha256": artifact_sha,
        "statement": statement.strip(),
    }
    core["evidence_id"] = _stable_sha256(core)
    return core


def normalize_evidence(
    evidence: list[dict[str, Any]],
    *,
    family: dict[str, Any],
) -> list[dict[str, Any]]:
    normalized = [normalize_evidence_item(item, family=family) for item in evidence]
    normalized.sort(key=lambda item: item["evidence_id"])
    ids = [item["evidence_id"] for item in normalized]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate root-cause evidence identity")
    return normalized


def _finding(domain: str, evidence: list[dict[str, Any]]) -> dict[str, Any]:
    items = [item for item in evidence if item["domain"] == domain]
    support = [item for item in items if item["direction"] == "SUPPORTS"]
    contradict = [item for item in items if item["direction"] == "CONTRADICTS"]
    direct_support = [item for item in support if item["strength"] == "DIRECT"]
    indirect_support = [item for item in support if item["strength"] == "INDIRECT"]
    direct_contradict = [item for item in contradict if item["strength"] == "DIRECT"]
    indirect_contradict = [item for item in contradict if item["strength"] == "INDIRECT"]
    support_generations = sorted({int(item["generation"]) for item in support})
    contradict_generations = sorted({int(item["generation"]) for item in contradict})
    score = (
        len(direct_support) * 5
        + len(indirect_support) * 2
        + len(support_generations) * 2
        - len(direct_contradict) * 6
        - len(indirect_contradict) * 3
    )

    if (
        len(direct_support) >= 2
        and len(support_generations) >= 2
        and not contradict
    ):
        state = "CONFIRMED_ROOT_CAUSE"
    elif (
        len(direct_contradict) >= 2
        and len(contradict_generations) >= 2
        and not support
    ):
        state = "RULED_OUT"
    elif support and score > 0:
        state = "SUSPECTED"
    else:
        state = "INCONCLUSIVE"

    return {
        "finding_version": ROOT_CAUSE_FINDING_VERSION,
        "domain": domain,
        "state": state,
        "score": score,
        "support_count": len(support),
        "direct_support_count": len(direct_support),
        "indirect_support_count": len(indirect_support),
        "support_generations": support_generations,
        "contradiction_count": len(contradict),
        "direct_contradiction_count": len(direct_contradict),
        "indirect_contradiction_count": len(indirect_contradict),
        "contradiction_generations": contradict_generations,
        "evidence_ids": [item["evidence_id"] for item in items],
        "confirmation_threshold": {
            "minimum_direct_support": 2,
            "minimum_support_generations": 2,
            "maximum_contradictions": 0,
        },
    }


def build_investigation_package(
    lineage_report: dict[str, Any],
    *,
    root_fingerprint: str,
    evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    family = _family(lineage_report, root_fingerprint)
    normalized = normalize_evidence(evidence or [], family=family)
    required = family["health"] in INVESTIGATION_REQUIRED_HEALTH
    findings = [_finding(domain, normalized) for domain in DOMAINS]
    order = {domain: index for index, domain in enumerate(DOMAINS)}
    findings.sort(
        key=lambda item: (
            -int(item["score"]),
            -len(item["support_generations"]),
            -int(item["direct_support_count"]),
            order[item["domain"]],
        )
    )
    confirmed = [
        item["domain"]
        for item in findings
        if item["state"] == "CONFIRMED_ROOT_CAUSE"
    ]
    suspected = [item["domain"] for item in findings if item["state"] == "SUSPECTED"]
    required_findings = confirmed[:] if confirmed else suspected[:2]
    evidence_gap_domains = [
        item["domain"] for item in findings if not item["evidence_ids"]
    ]
    family_sha = _family_sha(family)
    core = {
        "investigation_version": ROOT_CAUSE_INVESTIGATION_VERSION,
        "lineage_version": lineage_report["lineage_version"],
        "lineage_report_sha256": lineage_report["report_sha256"],
        "family_sha256": family_sha,
        "family_root_fingerprint": family["root_proposal_fingerprint"],
        "failure_code": family["failure_code"],
        "service": family.get("service"),
        "health": family["health"],
        "deepest_generation": int(family["deepest_generation"]),
        "repeat_regression_count": int(family["repeat_regression_count"]),
        "investigation_required": required,
        "lineage_paths": deepcopy(family["paths"]),
        "lineage_nodes": deepcopy(family["nodes"]),
        "domains": list(DOMAINS),
        "evidence": normalized,
        "findings": findings,
        "confirmed_root_causes": confirmed,
        "root_cause_named": bool(confirmed),
        "suspected_domains": suspected,
        "required_findings": required_findings,
        "evidence_gap_domains": evidence_gap_domains,
        "causal_claim_boundary": (
            "A domain is named as a root cause only after direct supporting evidence in at least two accepted generations with zero contradictory evidence."
        ),
        "ordinary_symptom_fix_sufficient": not required,
        "replay_success_alone_sufficient": not required,
        "automatic_issue_creation": False,
        "production_code_mutation": False,
        "execution_authorized": False,
    }
    core["package_id"] = _stable_sha256(core)
    core["package_sha256"] = _stable_sha256(core)
    validate_investigation_package(core)
    return core


def validate_investigation_package(package: dict[str, Any]) -> None:
    if package.get("investigation_version") != ROOT_CAUSE_INVESTIGATION_VERSION:
        raise ValueError("unsupported Human root-cause investigation version")
    for key in (
        "family_root_fingerprint",
        "family_sha256",
        "lineage_report_sha256",
        "package_id",
        "package_sha256",
    ):
        value = package.get(key)
        if not isinstance(value, str) or len(value) != 64:
            raise ValueError(f"Human root-cause investigation {key} is invalid")
    if package.get("domains") != list(DOMAINS):
        raise ValueError("Human root-cause investigation domain set mismatch")
    if package.get("health") in INVESTIGATION_REQUIRED_HEALTH:
        if package.get("investigation_required") is not True:
            raise ValueError("warning/chronic lineage must require root-cause investigation")
        if package.get("ordinary_symptom_fix_sufficient") is not False:
            raise ValueError("ordinary symptom fix cannot satisfy generation-2+ investigation")
        if package.get("replay_success_alone_sufficient") is not False:
            raise ValueError("replay success alone cannot satisfy generation-2+ investigation")
    findings = package.get("findings")
    if not isinstance(findings, list) or {item.get("domain") for item in findings} != set(DOMAINS):
        raise ValueError("Human root-cause findings must cover all investigation domains")
    for item in findings:
        if item.get("finding_version") != ROOT_CAUSE_FINDING_VERSION:
            raise ValueError("Human root-cause finding version mismatch")
        if item.get("state") not in FINDING_STATES:
            raise ValueError("Human root-cause finding state is invalid")
        if item.get("state") == "CONFIRMED_ROOT_CAUSE":
            if int(item.get("direct_support_count", 0)) < 2:
                raise ValueError("confirmed root cause lacks direct supporting evidence")
            if len(item.get("support_generations") or []) < 2:
                raise ValueError("confirmed root cause lacks cross-generation evidence")
            if int(item.get("contradiction_count", 0)) != 0:
                raise ValueError("confirmed root cause cannot carry contradictory evidence")
    confirmed = [item["domain"] for item in findings if item["state"] == "CONFIRMED_ROOT_CAUSE"]
    if package.get("confirmed_root_causes") != confirmed:
        raise ValueError("Human root-cause confirmed-domain summary mismatch")
    if package.get("root_cause_named") is not bool(confirmed):
        raise ValueError("Human root-cause naming boundary mismatch")
    if package.get("automatic_issue_creation") is not False:
        raise ValueError("Human root-cause investigation cannot create issues")
    if package.get("production_code_mutation") is not False or package.get("execution_authorized") is not False:
        raise ValueError("Human root-cause investigation exceeds authority boundary")
    expected = {key: value for key, value in package.items() if key not in {"package_id", "package_sha256"}}
    expected_id = _stable_sha256(expected)
    with_id = {**expected, "package_id": expected_id}
    if package["package_id"] != expected_id or package["package_sha256"] != _stable_sha256(with_id):
        raise ValueError("Human root-cause investigation package digest mismatch")


def validate_root_cause_ledger(ledger: dict[str, Any]) -> None:
    if ledger.get("ledger_version") != ROOT_CAUSE_LEDGER_VERSION:
        raise ValueError("unsupported Human root-cause ledger version")
    policy = ledger.get("policy")
    required_policy = {
        "generation_2_plus_investigation_required": True,
        "root_cause_claims_require_evidence": True,
        "explicit_owner_disposition_required": True,
        "symptom_fix_alone_sufficient": False,
        "replay_success_alone_sufficient": False,
        "automatic_issue_creation": False,
        "production_code_mutation": False,
        "execution_authorized": False,
    }
    if not isinstance(policy, dict):
        raise ValueError("Human root-cause ledger policy is required")
    for key, expected in required_policy.items():
        if policy.get(key) != expected:
            raise ValueError(f"Human root-cause ledger policy mismatch: {key}")
    investigations = ledger.get("investigations")
    dispositions = ledger.get("dispositions")
    if not isinstance(investigations, list) or not isinstance(dispositions, list):
        raise ValueError("Human root-cause ledger collections are required")
    package_ids: set[str] = set()
    roots: dict[str, str] = {}
    for sequence, row in enumerate(investigations, start=1):
        if not isinstance(row, dict) or row.get("sequence") != sequence:
            raise ValueError("Human root-cause investigation sequence must be contiguous")
        package = row.get("package")
        if not isinstance(package, dict):
            raise ValueError("Human root-cause investigation package is required")
        validate_investigation_package(package)
        package_id = row.get("package_id")
        if package_id != package["package_id"] or row.get("package_sha256") != package["package_sha256"]:
            raise ValueError("Human root-cause ledger package identity mismatch")
        if package_id in package_ids:
            raise ValueError("duplicate Human root-cause investigation package")
        package_ids.add(package_id)
        root = package["family_root_fingerprint"]
        if roots.get(root) == package_id:
            raise ValueError("duplicate Human root-cause family package")
        roots[root] = package_id
    disposition_ids: set[str] = set()
    disposed_packages: set[str] = set()
    for sequence, row in enumerate(dispositions, start=1):
        if not isinstance(row, dict) or row.get("sequence") != sequence:
            raise ValueError("Human root-cause disposition sequence must be contiguous")
        if row.get("disposition_version") != ROOT_CAUSE_DISPOSITION_VERSION:
            raise ValueError("Human root-cause disposition version mismatch")
        disposition_id = row.get("disposition_id")
        package_id = row.get("package_id")
        if not isinstance(disposition_id, str) or len(disposition_id) != 64:
            raise ValueError("Human root-cause disposition identity is invalid")
        if package_id not in package_ids:
            raise ValueError("Human root-cause disposition references unknown package")
        if disposition_id in disposition_ids or package_id in disposed_packages:
            raise ValueError("duplicate Human root-cause disposition")
        disposition_ids.add(disposition_id)
        disposed_packages.add(package_id)
        if row.get("approved") is not True or not isinstance(row.get("approved_by"), str) or not row["approved_by"].strip():
            raise ValueError("Human root-cause disposition requires explicit owner approval")
        if row.get("mode") not in DISPOSITION_MODES:
            raise ValueError("Human root-cause disposition mode is invalid")
        if not isinstance(row.get("addressed_domains"), list) or not row["addressed_domains"]:
            raise ValueError("Human root-cause disposition addressed domains are required")
        if not isinstance(row.get("evidence_refs"), list) or not row["evidence_refs"]:
            raise ValueError("Human root-cause disposition evidence refs are required")
        if not isinstance(row.get("rationale"), str) or not row["rationale"].strip():
            raise ValueError("Human root-cause disposition rationale is required")
        core = {key: value for key, value in row.items() if key not in {"sequence", "disposition_id", "disposition_sha256"}}
        expected_id = _stable_sha256(core)
        with_id = {**core, "disposition_id": expected_id}
        if row["disposition_id"] != expected_id or row.get("disposition_sha256") != _stable_sha256(with_id):
            raise ValueError("Human root-cause disposition digest mismatch")


def register_investigation(
    ledger: dict[str, Any], package: dict[str, Any]
) -> tuple[dict[str, Any], str]:
    validate_root_cause_ledger(ledger)
    validate_investigation_package(package)
    existing = next(
        (row for row in ledger["investigations"] if row["package_id"] == package["package_id"]),
        None,
    )
    if existing is not None:
        if existing["package"] == package:
            return ledger, "UNCHANGED"
        raise ValueError("Human root-cause investigation package identity conflict")
    same_family = [
        row
        for row in ledger["investigations"]
        if row["package"]["family_root_fingerprint"] == package["family_root_fingerprint"]
        and row["package"]["family_sha256"] == package["family_sha256"]
    ]
    if same_family:
        raise ValueError("current Human remediation family already has a conflicting investigation package")
    updated = deepcopy(ledger)
    updated["investigations"].append(
        {
            "sequence": len(updated["investigations"]) + 1,
            "package_id": package["package_id"],
            "package_sha256": package["package_sha256"],
            "package": deepcopy(package),
        }
    )
    validate_root_cause_ledger(updated)
    return updated, "APPENDED"


def address_investigation(
    ledger: dict[str, Any],
    *,
    package_id: str,
    owner: str,
    mode: str,
    addressed_domains: list[str],
    evidence_refs: list[str],
    rationale: str,
    approved: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    validate_root_cause_ledger(ledger)
    owner = owner.strip()
    if not approved:
        raise ValueError("Human root-cause disposition requires explicit owner approval")
    if not owner:
        raise ValueError("Human root-cause disposition owner is required")
    if mode not in DISPOSITION_MODES:
        raise ValueError("Human root-cause disposition mode is invalid")
    package_row = next(
        (row for row in ledger["investigations"] if row["package_id"] == package_id),
        None,
    )
    if package_row is None:
        raise ValueError("Human root-cause investigation package was not registered")
    package = package_row["package"]
    domains = sorted(set(addressed_domains))
    refs = sorted(set(ref.strip() for ref in evidence_refs if isinstance(ref, str) and ref.strip()))
    if any(domain not in DOMAINS for domain in domains):
        raise ValueError("Human root-cause disposition contains an invalid domain")
    if not refs:
        raise ValueError("Human root-cause disposition requires evidence references")
    required = set(package["required_findings"])
    if mode == "CONFIRMED_ROOT_CAUSE_ADDRESSED":
        confirmed = set(package["confirmed_root_causes"])
        if not confirmed:
            raise ValueError("cannot claim confirmed root-cause remediation without confirmed root-cause evidence")
        if not confirmed.issubset(domains):
            raise ValueError("all confirmed root-cause domains must be addressed")
    else:
        if package["confirmed_root_causes"]:
            raise ValueError("confirmed root cause requires CONFIRMED_ROOT_CAUSE_ADDRESSED disposition")
        if not required:
            raise ValueError("inconclusive investigation with no evidence-backed leading finding cannot be marked addressed")
        if not required.issubset(domains):
            raise ValueError("all evidence-backed leading findings must be addressed")
    core = {
        "disposition_version": ROOT_CAUSE_DISPOSITION_VERSION,
        "package_id": package_id,
        "family_root_fingerprint": package["family_root_fingerprint"],
        "approved": True,
        "approved_by": owner,
        "mode": mode,
        "addressed_domains": domains,
        "evidence_refs": refs,
        "rationale": rationale.strip(),
        "root_cause_named": bool(package["root_cause_named"]),
        "confirmed_root_causes": list(package["confirmed_root_causes"]),
        "production_code_mutation": False,
        "execution_authorized": False,
    }
    if not core["rationale"]:
        raise ValueError("Human root-cause disposition rationale is required")
    disposition_id = _stable_sha256(core)
    row = {
        **core,
        "disposition_id": disposition_id,
        "disposition_sha256": _stable_sha256({**core, "disposition_id": disposition_id}),
    }
    existing = next(
        (item for item in ledger["dispositions"] if item["package_id"] == package_id),
        None,
    )
    if existing is not None:
        expected = {key: value for key, value in existing.items() if key != "sequence"}
        if expected == row:
            return ledger, deepcopy(existing)
        raise ValueError("Human root-cause investigation already has a conflicting disposition")
    updated = deepcopy(ledger)
    stored = {"sequence": len(updated["dispositions"]) + 1, **row}
    updated["dispositions"].append(stored)
    validate_root_cause_ledger(updated)
    return updated, stored


def root_cause_sufficiency_gate(
    lineage_report: dict[str, Any],
    ledger: dict[str, Any],
    *,
    fingerprint: str,
) -> dict[str, Any]:
    validate_generational_lineage_report(lineage_report)
    validate_root_cause_ledger(ledger)
    family = _family_for_fingerprint(lineage_report, fingerprint)
    required = family["health"] in INVESTIGATION_REQUIRED_HEALTH
    base = {
        "gate_version": ROOT_CAUSE_SUFFICIENCY_GATE_VERSION,
        "proposal_fingerprint": fingerprint,
        "family_root_fingerprint": family["root_proposal_fingerprint"],
        "health": family["health"],
        "deepest_generation": int(family["deepest_generation"]),
        "investigation_required": required,
        "ordinary_symptom_fix_sufficient": not required,
        "replay_success_alone_sufficient": not required,
        "production_code_mutation": False,
        "execution_authorized": False,
    }
    if not required:
        return {
            **base,
            "status": "NOT_REQUIRED",
            "remediation_sufficient": True,
            "closure_sufficient": True,
            "package_id": None,
            "disposition_id": None,
            "blockers": [],
        }
    family_sha = _family_sha(family)
    current = [
        row
        for row in ledger["investigations"]
        if row["package"]["family_root_fingerprint"] == family["root_proposal_fingerprint"]
        and row["package"]["family_sha256"] == family_sha
    ]
    if not current:
        return {
            **base,
            "status": "BLOCKED_INVESTIGATION_REQUIRED",
            "remediation_sufficient": False,
            "closure_sufficient": False,
            "package_id": None,
            "disposition_id": None,
            "blockers": ["current generation-2+ lineage has no registered root-cause investigation package"],
        }
    if len(current) != 1:
        raise ValueError("Human root-cause ledger has conflicting current-family investigations")
    package_row = current[0]
    disposition = next(
        (row for row in ledger["dispositions"] if row["package_id"] == package_row["package_id"]),
        None,
    )
    if disposition is None:
        return {
            **base,
            "status": "BLOCKED_FINDINGS_UNADDRESSED",
            "remediation_sufficient": False,
            "closure_sufficient": False,
            "package_id": package_row["package_id"],
            "disposition_id": None,
            "blockers": ["root-cause investigation findings have not received an explicit evidence-backed owner disposition"],
        }
    return {
        **base,
        "status": "ROOT_CAUSE_FINDINGS_ADDRESSED",
        "remediation_sufficient": True,
        "closure_sufficient": True,
        "package_id": package_row["package_id"],
        "disposition_id": disposition["disposition_id"],
        "disposition_mode": disposition["mode"],
        "blockers": [],
    }


def root_cause_summary(ledger: dict[str, Any]) -> dict[str, Any]:
    validate_root_cause_ledger(ledger)
    disposed = {row["package_id"] for row in ledger["dispositions"]}
    return {
        "ledger_version": ROOT_CAUSE_LEDGER_VERSION,
        "investigation_count": len(ledger["investigations"]),
        "addressed_count": len(disposed),
        "unaddressed_count": len(ledger["investigations"]) - len(disposed),
        "confirmed_root_cause_package_count": sum(
            1 for row in ledger["investigations"] if row["package"]["root_cause_named"]
        ),
        "generation_2_plus_investigation_required": True,
        "root_cause_claims_require_evidence": True,
        "symptom_fix_alone_sufficient": False,
        "replay_success_alone_sufficient": False,
        "production_code_mutation": False,
        "execution_authorized": False,
    }


def _load_evidence(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if text.startswith("["):
        payload = json.loads(text)
        if not isinstance(payload, list):
            raise ValueError("root-cause evidence JSON must be a list")
        return payload
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _lineage_report(lifecycle_path: Path | None, reopen_cycle_path: Path | None) -> dict[str, Any]:
    lifecycle = load_lifecycle(lifecycle_path or default_lifecycle_path())
    reopen = load_reopen_cycle_promotion_ledger(
        reopen_cycle_path or default_reopen_cycle_promotion_ledger_path()
    )
    return build_generational_lineage_report(lifecycle, reopen)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="roberta-eval-human-root-cause")
    parser.add_argument("--lifecycle", default=None)
    parser.add_argument("--reopen-cycle-ledger", default=None)
    parser.add_argument("--ledger", default=None)
    sub = parser.add_subparsers(dest="command", required=True)

    package_cmd = sub.add_parser("package")
    package_cmd.add_argument("--root-fingerprint", required=True)
    package_cmd.add_argument("--evidence", default=None)

    register_cmd = sub.add_parser("register")
    register_cmd.add_argument("--root-fingerprint", required=True)
    register_cmd.add_argument("--evidence", default=None)

    address_cmd = sub.add_parser("address")
    address_cmd.add_argument("--package-id", required=True)
    address_cmd.add_argument("--owner", required=True)
    address_cmd.add_argument("--mode", choices=sorted(DISPOSITION_MODES), required=True)
    address_cmd.add_argument("--domain", action="append", dest="domains", default=[])
    address_cmd.add_argument("--evidence-ref", action="append", dest="evidence_refs", default=[])
    address_cmd.add_argument("--rationale", required=True)
    address_cmd.add_argument("--approve", action="store_true", required=True)

    sufficiency_cmd = sub.add_parser("sufficiency")
    sufficiency_cmd.add_argument("--fingerprint", required=True)
    sub.add_parser("summary")

    args = parser.parse_args(argv)
    ledger_path = Path(args.ledger) if args.ledger else default_root_cause_ledger_path()
    ledger = load_root_cause_ledger(ledger_path)

    if args.command == "summary":
        payload = root_cause_summary(ledger)
    elif args.command == "address":
        updated, payload = address_investigation(
            ledger,
            package_id=args.package_id,
            owner=args.owner,
            mode=args.mode,
            addressed_domains=args.domains,
            evidence_refs=args.evidence_refs,
            rationale=args.rationale,
            approved=args.approve,
        )
        if updated != ledger:
            write_root_cause_ledger(ledger_path, updated)
    else:
        lineage = _lineage_report(
            Path(args.lifecycle) if args.lifecycle else None,
            Path(args.reopen_cycle_ledger) if args.reopen_cycle_ledger else None,
        )
        if args.command == "sufficiency":
            payload = root_cause_sufficiency_gate(
                lineage, ledger, fingerprint=args.fingerprint
            )
        else:
            package = build_investigation_package(
                lineage,
                root_fingerprint=args.root_fingerprint,
                evidence=_load_evidence(Path(args.evidence) if args.evidence else None),
            )
            if args.command == "package":
                payload = package
            else:
                updated, status = register_investigation(ledger, package)
                if updated != ledger:
                    write_root_cause_ledger(ledger_path, updated)
                payload = {"status": status, "package": package, "summary": root_cause_summary(updated)}

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
