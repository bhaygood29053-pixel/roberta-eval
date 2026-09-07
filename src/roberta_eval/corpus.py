from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from .registry import load_registry, validate_registry
from .taxonomy import load_taxonomy, validate_taxonomy


def blueprint_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "corpus_blueprints.json"


def load_blueprints(path: Path | None = None) -> dict[str, Any]:
    source = path or blueprint_path()
    return json.loads(source.read_text(encoding="utf-8"))


def _taxonomy_by_id(taxonomy: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["id"]: item for item in taxonomy["classes"]}


def validate_blueprints(
    document: dict[str, Any],
    *,
    registry: dict[str, Any] | None = None,
    taxonomy: dict[str, Any] | None = None,
) -> None:
    if document.get("corpus_blueprint_version") != "roberta_deterministic_blueprints/v1":
        raise ValueError("unsupported corpus blueprint version")

    registry = registry or load_registry()
    taxonomy = taxonomy or load_taxonomy()
    validate_registry(registry)
    validate_taxonomy(taxonomy, registry)

    if document.get("capability_registry_version") != registry["registry_version"]:
        raise ValueError("corpus registry version mismatch")
    if document.get("taxonomy_version") != taxonomy["taxonomy_version"]:
        raise ValueError("corpus taxonomy version mismatch")
    if not document.get("variation_policy"):
        raise ValueError("corpus variation policy is required")

    services = {item["id"] for item in registry["cmis_services"]}
    taxonomy_classes = _taxonomy_by_id(taxonomy)

    styles = document.get("variation_styles")
    if not isinstance(styles, list) or not styles:
        raise ValueError("variation styles are required")
    style_ids = [item.get("id") for item in styles]
    if any(not value for value in style_ids) or len(style_ids) != len(set(style_ids)):
        raise ValueError("variation style IDs must be unique and non-empty")
    allowed_user_styles = set(taxonomy["dimensions"]["user_styles"])
    for style in styles:
        if style.get("style") not in allowed_user_styles:
            raise ValueError(f"unknown user style: {style.get('style')}")
        if "prefix" not in style or "suffix" not in style:
            raise ValueError(f"{style['id']}: style wrapper is incomplete")

    blueprints = document.get("blueprints")
    if not isinstance(blueprints, list) or not blueprints:
        raise ValueError("corpus blueprints are required")
    ids = [item.get("id") for item in blueprints]
    if any(not value for value in ids) or len(ids) != len(set(ids)):
        raise ValueError("blueprint IDs must be unique and non-empty")

    covered_services: set[str] = set()
    for item in blueprints:
        blueprint_id = item["id"]
        service = item.get("service")
        if service not in services:
            raise ValueError(f"{blueprint_id}: unknown service {service}")
        covered_services.add(service)

        class_id = item.get("taxonomy_class")
        class_contract = taxonomy_classes.get(class_id)
        if class_contract is None:
            raise ValueError(f"{blueprint_id}: unknown taxonomy class {class_id}")
        applies_to = class_contract["applies_to"]
        if isinstance(applies_to, list) and service not in applies_to:
            raise ValueError(f"{blueprint_id}: taxonomy class does not apply to service")
        if applies_to == "none":
            raise ValueError(f"{blueprint_id}: unsupported class cannot target service")

        if item.get("evidence_condition") not in class_contract["evidence_conditions"]:
            raise ValueError(f"{blueprint_id}: evidence condition not allowed by taxonomy class")
        if not item.get("question"):
            raise ValueError(f"{blueprint_id}: question is required")
        if not item.get("objective_signature"):
            raise ValueError(f"{blueprint_id}: objective signature is required")

        fixture = item.get("fixture")
        if not isinstance(fixture, dict) or fixture.get("chain") != "x1":
            raise ValueError(f"{blueprint_id}: X1 fixture is required")

        checks = item.get("checks")
        if not isinstance(checks, list) or not checks:
            raise ValueError(f"{blueprint_id}: deterministic checks are required")
        if not any(
            check.get("kind") == "execution_authorized" and check.get("value") is False
            for check in checks
        ):
            raise ValueError(f"{blueprint_id}: execution boundary check is required")

    missing_services = services - covered_services
    if missing_services:
        raise ValueError(f"corpus missing services: {sorted(missing_services)}")


def materialize_cases(document: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    document = document or load_blueprints()
    validate_blueprints(document)

    cases: list[dict[str, Any]] = []
    for blueprint in document["blueprints"]:
        for style in document["variation_styles"]:
            case_id = f"{blueprint['id']}::{style['id']}"
            question = f"{style['prefix']}{blueprint['question']}{style['suffix']}"
            cases.append(
                {
                    "case_id": case_id,
                    "corpus_version": "roberta_deterministic_corpus/v1",
                    "blueprint_id": blueprint["id"],
                    "variation_id": style["id"],
                    "user_style": style["style"],
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
        raise ValueError("materialized corpus contains duplicate case IDs")
    return cases


def serialize_jsonl(cases: Iterable[dict[str, Any]]) -> str:
    return "".join(
        json.dumps(case, sort_keys=True, separators=(",", ":")) + "\n"
        for case in cases
    )


def corpus_digest(cases: list[dict[str, Any]] | None = None) -> str:
    cases = cases or materialize_cases()
    return hashlib.sha256(serialize_jsonl(cases).encode("utf-8")).hexdigest()


def corpus_summary(cases: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    cases = cases or materialize_cases()
    return {
        "corpus_version": "roberta_deterministic_corpus/v1",
        "case_count": len(cases),
        "service_count": len({case["service"] for case in cases}),
        "taxonomy_class_count": len({case["taxonomy_class"] for case in cases}),
        "user_style_count": len({case["variation_id"] for case in cases}),
        "sha256": corpus_digest(cases),
    }


def write_corpus(path: Path, cases: list[dict[str, Any]] | None = None) -> None:
    cases = cases or materialize_cases()
    path.write_text(serialize_jsonl(cases), encoding="utf-8")
