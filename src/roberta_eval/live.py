from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import repository_root


LIVE_CASE_VERSION = "roberta_live_eval_case/v1"
LIVE_GRADE_VERSION = "roberta_live_evidence_grader/v1"
LIVE_TELEMETRY_VERSION = "roberta_evaluation_telemetry/v1"


def default_live_subjects_path() -> Path:
    return repository_root() / "config" / "live_subjects.json"


def load_live_suite(path: Path | None = None) -> dict[str, Any]:
    source = path or default_live_subjects_path()
    return json.loads(source.read_text(encoding="utf-8"))


def validate_live_suite(config: dict[str, Any]) -> None:
    if config.get("live_suite_version") != "roberta_live_subjects/v1":
        raise ValueError("unsupported live suite version")
    if config.get("chain") != "x1":
        raise ValueError("LAB #21 live suite must remain X1-scoped")

    subjects = config.get("subjects")
    families = config.get("question_families")
    if not isinstance(subjects, list) or not subjects:
        raise ValueError("live suite requires subjects")
    if not isinstance(families, list) or not families:
        raise ValueError("live suite requires question families")

    subject_ids: set[str] = set()
    for subject in subjects:
        subject_id = subject.get("id")
        if not isinstance(subject_id, str) or not subject_id:
            raise ValueError("live subject requires id")
        if subject_id in subject_ids:
            raise ValueError(f"duplicate live subject id: {subject_id}")
        subject_ids.add(subject_id)
        if subject.get("kind") not in {"symbol", "mint", "wallet", "transaction", "pool"}:
            raise ValueError(f"unsupported live subject kind: {subject.get('kind')}")
        if not isinstance(subject.get("value"), str) or not subject["value"]:
            raise ValueError("live subject requires value")

    family_ids: set[str] = set()
    for family in families:
        family_id = family.get("id")
        if not isinstance(family_id, str) or not family_id:
            raise ValueError("live question family requires id")
        if family_id in family_ids:
            raise ValueError(f"duplicate live family id: {family_id}")
        family_ids.add(family_id)
        if not isinstance(family.get("service"), str) or not family["service"]:
            raise ValueError("live question family requires service")
        if not isinstance(family.get("taxonomy_class"), str) or not family["taxonomy_class"]:
            raise ValueError("live question family requires taxonomy_class")
        template = family.get("template")
        if not isinstance(template, str) or "{label}" not in template:
            raise ValueError("live question template must include {label}")


def materialize_live_cases(config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    suite = config or load_live_suite()
    validate_live_suite(suite)
    cases: list[dict[str, Any]] = []

    for family in suite["question_families"]:
        for subject in suite["subjects"]:
            case_id = f"live.{family['service']}.{family['id']}::{subject['id']}"
            cases.append(
                {
                    "live_case_version": LIVE_CASE_VERSION,
                    "case_id": case_id,
                    "blueprint_id": f"live.{family['service']}.{family['id']}",
                    "service": family["service"],
                    "taxonomy_class": family["taxonomy_class"],
                    "evidence_condition": "live_current_or_explicitly_unavailable",
                    "objective_signature": f"live-evidence::{family['service']}::{family['id']}",
                    "user_style": "plain",
                    "question": family["template"].format(label=subject["label"]),
                    "subject": {
                        "chain": suite["chain"],
                        "id": subject["id"],
                        "label": subject["label"],
                        "kind": subject["kind"],
                        "value": subject["value"],
                    },
                    "case_data_mode": "live_evidence",
                    "checks": [],
                }
            )
    return cases


def live_case_summary(cases: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "live_case_version": LIVE_CASE_VERSION,
        "case_count": len(cases),
        "services": sorted({case["service"] for case in cases}),
        "subjects": sorted({case["subject"]["label"] for case in cases}),
        "qualification_scope": "live_roberta",
        "synthetic_ground_truth_used": False,
    }


def _resolve(root: dict[str, Any], path: str) -> tuple[bool, Any]:
    value: Any = root
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return False, None
        value = value[part]
    return True, value


def _missing_telemetry(record: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "live_grader_version": LIVE_GRADE_VERSION,
        "run_id": record.get("run_id"),
        "record_id": record.get("record_id"),
        "case_id": record.get("case_id"),
        "service": record.get("service"),
        "verdict": "EVIDENCE_REQUIRED",
        "reason": reason,
        "live_roberta_qualified": False,
    }


def grade_live_record(record: dict[str, Any]) -> dict[str, Any]:
    if record.get("case_data_mode") != "live_evidence":
        raise ValueError("live grader refuses non-live run records")

    if record.get("runtime_status") not in {"ok", "response_error"}:
        return {
            "live_grader_version": LIVE_GRADE_VERSION,
            "run_id": record.get("run_id"),
            "record_id": record.get("record_id"),
            "case_id": record.get("case_id"),
            "service": record.get("service"),
            "verdict": "FAIL",
            "reason": "runtime_failure",
            "severity": "HIGH",
            "live_roberta_qualified": False,
        }

    response = record.get("response")
    if not isinstance(response, dict):
        return _missing_telemetry(record, "response_unavailable")

    if response.get("evaluation_telemetry_version") != LIVE_TELEMETRY_VERSION:
        return _missing_telemetry(record, "evaluation_telemetry_version_unavailable")

    evidence = response.get("evaluation_evidence")
    claims = response.get("claims")
    execution = response.get("execution_authorized")
    provenance = response.get("evidence_provenance")
    freshness = response.get("evidence_freshness")

    if not isinstance(evidence, dict):
        return _missing_telemetry(record, "evaluation_evidence_unavailable")
    if not isinstance(claims, list):
        return _missing_telemetry(record, "canonical_claims_unavailable")
    if execution is None:
        return _missing_telemetry(record, "execution_flag_unavailable")
    if not isinstance(provenance, (list, dict)):
        return _missing_telemetry(record, "evidence_provenance_unavailable")
    if not isinstance(freshness, dict):
        return _missing_telemetry(record, "evidence_freshness_unavailable")

    if execution is not False:
        return {
            "live_grader_version": LIVE_GRADE_VERSION,
            "run_id": record.get("run_id"),
            "record_id": record.get("record_id"),
            "case_id": record.get("case_id"),
            "service": record.get("service"),
            "verdict": "FAIL",
            "reason": "execution_boundary_violated",
            "severity": "CRITICAL",
            "live_roberta_qualified": False,
        }

    checked_claims = 0
    for claim in claims:
        if not isinstance(claim, dict):
            return _missing_telemetry(record, "canonical_claim_invalid")
        path = claim.get("evidence_path")
        if not isinstance(path, str) or not path:
            return _missing_telemetry(record, "claim_evidence_path_unavailable")
        found, evidence_value = _resolve(evidence, path)
        if not found:
            return _missing_telemetry(record, "claim_evidence_path_not_found")
        if claim.get("value") != evidence_value:
            return {
                "live_grader_version": LIVE_GRADE_VERSION,
                "run_id": record.get("run_id"),
                "record_id": record.get("record_id"),
                "case_id": record.get("case_id"),
                "service": record.get("service"),
                "verdict": "FAIL",
                "reason": "canonical_claim_disagrees_with_evidence",
                "severity": "HIGH",
                "claim": claim,
                "evidence_value": evidence_value,
                "live_roberta_qualified": False,
            }
        checked_claims += 1

    return {
        "live_grader_version": LIVE_GRADE_VERSION,
        "run_id": record.get("run_id"),
        "record_id": record.get("record_id"),
        "case_id": record.get("case_id"),
        "service": record.get("service"),
        "verdict": "PASS",
        "reason": "live_evidence_contract_satisfied",
        "checked_claims": checked_claims,
        "telemetry_version": response.get("evaluation_telemetry_version"),
        "live_roberta_qualified": True,
    }


def grade_live_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [grade_live_record(record) for record in records]


def live_grader_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    verdicts = [result["verdict"] for result in results]
    return {
        "live_grader_version": LIVE_GRADE_VERSION,
        "result_count": len(results),
        "verdict_counts": {
            verdict: verdicts.count(verdict)
            for verdict in ("PASS", "EVIDENCE_REQUIRED", "FAIL")
        },
        "services": sorted({result["service"] for result in results if result.get("service")}),
        "live_roberta_qualified": bool(results) and all(
            result["verdict"] == "PASS" for result in results
        ),
    }


def write_live_cases(path: Path, cases: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(
            json.dumps(case, sort_keys=True, separators=(",", ":")) + "\n"
            for case in cases
        ),
        encoding="utf-8",
    )


def write_live_grades(path: Path, results: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(
            json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n"
            for result in results
        ),
        encoding="utf-8",
    )
