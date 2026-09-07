from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .corpus import serialize_jsonl
from .generator import generate_cases, generated_digest
from .grader import grade_records, grader_summary
from .runner import FixtureRobertaTransport, run_cases, run_summary

STRESS_REPORT_VERSION = "roberta_stress_report/v1"
DEFAULT_STRESS_LIMIT = 2500


def select_stress_cases(
    cases: list[dict[str, Any]] | None = None,
    *,
    limit: int = DEFAULT_STRESS_LIMIT,
) -> list[dict[str, Any]]:
    cases = cases or generate_cases()
    if limit < 1:
        raise ValueError("stress limit must be positive")
    if limit > len(cases):
        raise ValueError("stress limit exceeds generated suite")
    ordered = sorted(
        cases,
        key=lambda case: (
            case["surface_signature"],
            case["blueprint_id"],
            case["case_id"],
        ),
    )
    return ordered[:limit]


def _selected_digest(cases: list[dict[str, Any]]) -> str:
    return hashlib.sha256(serialize_jsonl(cases).encode("utf-8")).hexdigest()


def run_stress_qualification(
    *,
    limit: int = DEFAULT_STRESS_LIMIT,
    run_id: str = "stress-fixture-v1",
) -> dict[str, Any]:
    generated = generate_cases()
    selected = select_stress_cases(generated, limit=limit)
    records = run_cases(
        selected,
        transport=FixtureRobertaTransport(),
        run_id=run_id,
        target="fixture://local",
    )
    grades = grade_records(records)

    rsummary = run_summary(records)
    gsummary = grader_summary(grades)
    services = sorted({case["service"] for case in selected})
    taxonomy_classes = sorted({case["taxonomy_class"] for case in selected})
    verdict_counts = gsummary["verdict_counts"]

    acceptance = {
        "selected_case_count_is_limit": len(selected) == limit,
        "all_18_services_represented": len(services) == 18,
        "runner_record_count_matches": len(records) == limit,
        "grader_result_count_matches": len(grades) == limit,
        "fixture_baseline_all_pass": (
            verdict_counts["PASS"] == limit
            and verdict_counts["WARN"] == 0
            and verdict_counts["FAIL"] == 0
        ),
    }
    accepted = all(acceptance.values())

    return {
        "report_version": STRESS_REPORT_VERSION,
        "qualification_scope": "laboratory_pipeline_fixture_transport",
        "live_roberta_qualified": False,
        "boundary": (
            "This qualification proves the Laboratory generation/runner/grader "
            "pipeline at scale using synthetic fixture evidence. It does not prove "
            "that live ROBERTA answered these cases correctly."
        ),
        "run_id": run_id,
        "requested_limit": limit,
        "selected_case_count": len(selected),
        "generated_suite_sha256": generated_digest(generated),
        "selected_suite_sha256": _selected_digest(selected),
        "coverage": {
            "service_count": len(services),
            "services": services,
            "taxonomy_class_count": len(taxonomy_classes),
            "taxonomy_classes": taxonomy_classes,
            "blueprint_count": len({case["blueprint_id"] for case in selected}),
            "surface_count": len({case["surface_signature"] for case in selected}),
        },
        "runtime": rsummary,
        "grading": gsummary,
        "acceptance_checks": acceptance,
        "accepted": accepted,
    }


def render_stress_markdown(report: dict[str, Any]) -> str:
    verdicts = report["grading"]["verdict_counts"]
    checks = report["acceptance_checks"]
    check_lines = "\n".join(
        f"- {'PASS' if passed else 'FAIL'} — {name}"
        for name, passed in checks.items()
    )
    return f"""# ROBERTA Evaluation Laboratory Stress Qualification

**Report:** {report['report_version']}
**Scope:** {report['qualification_scope']}
**Accepted:** {'YES' if report['accepted'] else 'NO'}

## Results

- Selected cases: {report['selected_case_count']}
- Services represented: {report['coverage']['service_count']}
- PASS: {verdicts['PASS']}
- WARN: {verdicts['WARN']}
- FAIL: {verdicts['FAIL']}
- Live ROBERTA qualified: {str(report['live_roberta_qualified']).lower()}

## Acceptance checks

{check_lines}

## Boundary

{report['boundary']}

This is a Laboratory pipeline qualification. A separate live-eligible suite is
required before these results can be used as evidence of live ROBERTA answer quality.
"""


def write_stress_json(path: Path, report: dict[str, Any]) -> None:
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_stress_markdown(path: Path, report: dict[str, Any]) -> None:
    path.write_text(render_stress_markdown(report), encoding="utf-8")
