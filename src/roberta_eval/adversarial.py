from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .corpus import load_blueprints, serialize_jsonl, validate_blueprints


def attacks_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "adversarial_attacks.json"


def load_attacks(path: Path | None = None) -> dict[str, Any]:
    source = path or attacks_path()
    return json.loads(source.read_text(encoding="utf-8"))


def validate_attacks(document: dict[str, Any]) -> None:
    if document.get("adversarial_surface_version") != "roberta_adversarial_attacks/v1":
        raise ValueError("unsupported adversarial surface version")
    if not document.get("policy"):
        raise ValueError("adversarial policy is required")
    attacks = document.get("attacks")
    if not isinstance(attacks, list) or not attacks:
        raise ValueError("adversarial attacks are required")
    ids = [item.get("id") for item in attacks]
    if any(not value for value in ids) or len(ids) != len(set(ids)):
        raise ValueError("adversarial attack IDs must be unique")
    for item in attacks:
        for field in ("target_invariant", "prefix", "suffix", "extra_forbidden"):
            if field not in item:
                raise ValueError(f"{item['id']}: missing {field}")


def generate_adversarial_cases(
    blueprints_document: dict[str, Any] | None = None,
    attacks_document: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    blueprints_document = blueprints_document or load_blueprints()
    attacks_document = attacks_document or load_attacks()
    validate_blueprints(blueprints_document)
    validate_attacks(attacks_document)

    cases: list[dict[str, Any]] = []
    for blueprint in blueprints_document["blueprints"]:
        for attack in attacks_document["attacks"]:
            original_checks = json.loads(json.dumps(blueprint["checks"]))
            checks = json.loads(json.dumps(blueprint["checks"]))
            extra = {
                "kind": "forbidden_conclusion",
                "value": attack["extra_forbidden"],
            }
            if extra not in checks:
                checks.append(extra)
            cases.append(
                {
                    "case_id": f"adv::{blueprint['id']}::{attack['id']}",
                    "suite_version": "roberta_adversarial_suite/v1",
                    "blueprint_id": blueprint["id"],
                    "attack_id": attack["id"],
                    "target_invariant": attack["target_invariant"],
                    "service": blueprint["service"],
                    "taxonomy_class": "adversarial",
                    "source_taxonomy_class": blueprint["taxonomy_class"],
                    "evidence_condition": blueprint["evidence_condition"],
                    "objective_signature": blueprint["objective_signature"],
                    "question": (
                        f"{attack['prefix']}{blueprint['question']}{attack['suffix']}"
                    ),
                    "fixture": blueprint["fixture"],
                    "source_checks": original_checks,
                    "checks": checks,
                }
            )

    ids = [case["case_id"] for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("adversarial suite contains duplicate case IDs")
    return cases


def adversarial_digest(cases: list[dict[str, Any]] | None = None) -> str:
    cases = cases or generate_adversarial_cases()
    return hashlib.sha256(serialize_jsonl(cases).encode("utf-8")).hexdigest()


def adversarial_summary(cases: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    cases = cases or generate_adversarial_cases()
    return {
        "suite_version": "roberta_adversarial_suite/v1",
        "case_count": len(cases),
        "service_count": len({case["service"] for case in cases}),
        "blueprint_count": len({case["blueprint_id"] for case in cases}),
        "attack_count": len({case["attack_id"] for case in cases}),
        "target_invariant_count": len({case["target_invariant"] for case in cases}),
        "sha256": adversarial_digest(cases),
    }


def write_adversarial(path: Path, cases: list[dict[str, Any]] | None = None) -> None:
    cases = cases or generate_adversarial_cases()
    path.write_text(serialize_jsonl(cases), encoding="utf-8")
