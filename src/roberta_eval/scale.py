from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .corpus import load_blueprints, serialize_jsonl, validate_blueprints
from .grader import grade_records, grader_summary
from .runner import FixtureRobertaTransport, run_cases, run_summary
from .taxonomy import load_taxonomy

SCALE_SUITE_VERSION = "roberta_scale_suite/v1"
SCALE_REPORT_VERSION = "roberta_scale_qualification/v1"


def scale_surfaces_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "scale_surfaces.json"


def load_scale_surfaces(path: Path | None = None) -> dict[str, Any]:
    source = path or scale_surfaces_path()
    return json.loads(source.read_text(encoding="utf-8"))


def validate_scale_surfaces(document: dict[str, Any]) -> None:
    if document.get("scale_surface_version") != "roberta_scale_surfaces/v1":
        raise ValueError("unsupported scale surface version")
    if not document.get("policy"):
        raise ValueError("scale surface policy is required")
    allowed_styles = set(load_taxonomy()["dimensions"]["user_styles"])
    for field in ("prefixes", "suffixes", "closers"):
        values = document.get(field)
        if not isinstance(values, list) or not values:
            raise ValueError(f"{field}: scale surfaces required")
        ids = [item.get("id") for item in values]
        if any(not value for value in ids) or len(ids) != len(set(ids)):
            raise ValueError(f"{field}: IDs must be unique")
        if any("text" not in item for item in values):
            raise ValueError(f"{field}: text required")
    for prefix in document["prefixes"]:
        if prefix.get("style") not in allowed_styles:
            raise ValueError(f"unknown user style: {prefix.get('style')}")


def generate_scale_cases(
    blueprints_document: dict[str, Any] | None = None,
    surfaces_document: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    blueprints_document = blueprints_document or load_blueprints()
    surfaces_document = surfaces_document or load_scale_surfaces()
    validate_blueprints(blueprints_document)
    validate_scale_surfaces(surfaces_document)

    cases: list[dict[str, Any]] = []
    for blueprint in blueprints_document["blueprints"]:
        seen_questions: set[str] = set()
        for prefix in surfaces_document["prefixes"]:
            for suffix in surfaces_document["suffixes"]:
                for closer in surfaces_document["closers"]:
                    question = (
                        f"{prefix['text']}{blueprint['question']}"
                        f"{suffix['text']}{closer['text']}"
                    )
                    if question in seen_questions:
                        raise ValueError(f"{blueprint['id']}: duplicate scale question")
                    seen_questions.add(question)
                    signature = f"{prefix['id']}:{suffix['id']}:{closer['id']}"
                    cases.append(
                        {
                            "case_id": f"scale::{blueprint['id']}::{signature}",
                            "suite_version": SCALE_SUITE_VERSION,
                            "blueprint_id": blueprint["id"],
                            "surface_signature": signature,
                            "user_style": prefix["style"],
                            "service": blueprint["service"],
                            "taxonomy_class": blueprint["taxonomy_class"],
                            "evidence_condition": blueprint["evidence_condition"],
                            "objective_signature": blueprint["objective_signature"],
                            "question": question,
                            "fixture": blueprint["fixture"],
                            "checks": blueprint["checks"],
                        }
                    )
    ids = [case["case_id"] for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("scale suite contains duplicate case IDs")
    return cases


def select_scale_cases(cases: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    if limit < 1 or limit > len(cases):
        raise ValueError("scale limit outside generated suite")
    ordered = sorted(
        cases,
        key=lambda case: (
            case["surface_signature"],
            case["blueprint_id"],
            case["case_id"],
        ),
    )
    return ordered[:limit]


def _digest(cases: list[dict[str, Any]]) -> str:
    return hashlib.sha256(serialize_jsonl(cases).encode("utf-8")).hexdigest()


def scale_summary(cases: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    cases = cases or generate_scale_cases()
    return {
        "suite_version": SCALE_SUITE_VERSION,
        "case_count": len(cases),
        "service_count": len({case["service"] for case in cases}),
        "blueprint_count": len({case["blueprint_id"] for case in cases}),
        "surface_count": len({case["surface_signature"] for case in cases}),
        "sha256": _digest(cases),
    }


def run_scale_qualification(*, limit: int, run_id: str | None = None) -> dict[str, Any]:
    generated = generate_scale_cases()
    selected = select_scale_cases(generated, limit=limit)
    records = run_cases(
        selected,
        transport=FixtureRobertaTransport(),
        run_id=run_id or f"scale-{limit}-fixture-v1",
        target="fixture://scale",
    )
    grades = grade_records(records)
    rsummary = run_summary(records)
    gsummary = grader_summary(grades)
    verdicts = gsummary["verdict_counts"]
    services = sorted({case["service"] for case in selected})
    accepted = (
        len(selected) == limit
        and len(services) == 18
        and len(records) == limit
        and len(grades) == limit
        and verdicts == {"PASS": limit, "WARN": 0, "FAIL": 0}
    )
    return {
        "report_version": SCALE_REPORT_VERSION,
        "qualification_scope": "laboratory_scale_fixture_transport",
        "requested_case_count": limit,
        "selected_case_count": len(selected),
        "generated_case_count": len(generated),
        "service_count": len(services),
        "services": services,
        "selected_sha256": _digest(selected),
        "runtime": rsummary,
        "grading": gsummary,
        "accepted": accepted,
        "live_roberta_qualified": False,
        "boundary": (
            "This scale qualification proves Laboratory generation/runner/grader "
            "behavior using synthetic fixtures. It is not a live ROBERTA quality claim."
        ),
    }


def write_scale_report(path: Path, report: dict[str, Any]) -> None:
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
