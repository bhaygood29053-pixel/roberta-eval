from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .corpus import load_blueprints, serialize_jsonl, validate_blueprints
from .taxonomy import load_taxonomy


def surfaces_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "generation_surfaces.json"


def load_surfaces(path: Path | None = None) -> dict[str, Any]:
    source = path or surfaces_path()
    return json.loads(source.read_text(encoding="utf-8"))


def validate_surfaces(document: dict[str, Any]) -> None:
    if document.get("surface_version") != "roberta_generation_surfaces/v1":
        raise ValueError("unsupported generation surface version")
    if not document.get("policy"):
        raise ValueError("generation surface policy is required")

    taxonomy = load_taxonomy()
    styles = set(taxonomy["dimensions"]["user_styles"])

    prefixes = document.get("prefixes")
    suffixes = document.get("suffixes")
    if not isinstance(prefixes, list) or not prefixes:
        raise ValueError("generation prefixes are required")
    if not isinstance(suffixes, list) or not suffixes:
        raise ValueError("generation suffixes are required")

    prefix_ids = [item.get("id") for item in prefixes]
    suffix_ids = [item.get("id") for item in suffixes]
    if any(not value for value in prefix_ids) or len(prefix_ids) != len(set(prefix_ids)):
        raise ValueError("generation prefix IDs must be unique")
    if any(not value for value in suffix_ids) or len(suffix_ids) != len(set(suffix_ids)):
        raise ValueError("generation suffix IDs must be unique")

    for item in prefixes:
        if item.get("style") not in styles:
            raise ValueError(f"unknown generated user style: {item.get('style')}")
        if "text" not in item:
            raise ValueError(f"{item['id']}: prefix text is required")
    for item in suffixes:
        if "text" not in item:
            raise ValueError(f"{item['id']}: suffix text is required")


def generate_cases(
    blueprints_document: dict[str, Any] | None = None,
    surfaces_document: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    blueprints_document = blueprints_document or load_blueprints()
    surfaces_document = surfaces_document or load_surfaces()
    validate_blueprints(blueprints_document)
    validate_surfaces(surfaces_document)

    generated: list[dict[str, Any]] = []
    for blueprint in blueprints_document["blueprints"]:
        seen_questions: set[str] = set()
        for prefix in surfaces_document["prefixes"]:
            for suffix in surfaces_document["suffixes"]:
                question = f"{prefix['text']}{blueprint['question']}{suffix['text']}"
                if question in seen_questions:
                    raise ValueError(
                        f"{blueprint['id']}: duplicate generated question text"
                    )
                seen_questions.add(question)
                generated.append(
                    {
                        "case_id": (
                            f"gen::{blueprint['id']}::{prefix['id']}::{suffix['id']}"
                        ),
                        "suite_version": "roberta_generated_suite/v1",
                        "blueprint_id": blueprint["id"],
                        "surface_signature": f"{prefix['id']}:{suffix['id']}",
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

    ids = [case["case_id"] for case in generated]
    if len(ids) != len(set(ids)):
        raise ValueError("generated suite contains duplicate case IDs")
    return generated


def generated_digest(cases: list[dict[str, Any]] | None = None) -> str:
    cases = cases or generate_cases()
    return hashlib.sha256(serialize_jsonl(cases).encode("utf-8")).hexdigest()


def generated_summary(cases: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    cases = cases or generate_cases()
    return {
        "suite_version": "roberta_generated_suite/v1",
        "case_count": len(cases),
        "blueprint_count": len({case["blueprint_id"] for case in cases}),
        "service_count": len({case["service"] for case in cases}),
        "surface_count": len({case["surface_signature"] for case in cases}),
        "sha256": generated_digest(cases),
    }


def write_generated(path: Path, cases: list[dict[str, Any]] | None = None) -> None:
    cases = cases or generate_cases()
    path.write_text(serialize_jsonl(cases), encoding="utf-8")
