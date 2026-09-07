from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .registry import load_registry, validate_registry

REQUIRED_CLASSES = {
    "basic",
    "complex",
    "numerical",
    "comparison",
    "ambiguous",
    "adversarial",
    "false_premise",
    "missing_data",
    "stale_data",
    "unsupported",
    "follow_up",
    "multi_turn",
}

VALID_SHAPES = {"single_turn", "follow_up", "multi_turn"}


def taxonomy_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "question_taxonomy.json"


def load_taxonomy(path: Path | None = None) -> dict[str, Any]:
    source = path or taxonomy_path()
    return json.loads(source.read_text(encoding="utf-8"))


def validate_taxonomy(taxonomy: dict[str, Any], registry: dict[str, Any] | None = None) -> None:
    if taxonomy.get("taxonomy_version") != "roberta_question_taxonomy/v1":
        raise ValueError("unsupported question taxonomy version")
    if taxonomy.get("capability_registry_version") != "roberta_capability_registry/v1":
        raise ValueError("taxonomy capability registry version mismatch")
    if not taxonomy.get("objective_preservation_rule"):
        raise ValueError("objective preservation rule is required")

    registry = registry or load_registry()
    validate_registry(registry)
    service_ids = {item["id"] for item in registry["cmis_services"]}

    dimensions = taxonomy.get("dimensions")
    if not isinstance(dimensions, dict):
        raise ValueError("taxonomy dimensions are required")
    evidence_conditions = set(dimensions.get("evidence_conditions", {}))
    user_styles = dimensions.get("user_styles")
    shapes = dimensions.get("conversation_shapes")
    if not evidence_conditions:
        raise ValueError("evidence conditions are required")
    if not isinstance(user_styles, list) or len(set(user_styles)) != len(user_styles):
        raise ValueError("user styles must be a unique list")
    if set(shapes or {}) != VALID_SHAPES:
        raise ValueError("conversation shape definitions are incomplete")

    classes = taxonomy.get("classes")
    if not isinstance(classes, list) or not classes:
        raise ValueError("taxonomy classes are required")

    ids = [item.get("id") for item in classes]
    if any(not value for value in ids):
        raise ValueError("taxonomy class contains an empty id")
    if len(ids) != len(set(ids)):
        raise ValueError("taxonomy contains duplicate class ids")

    class_ids = set(ids)
    missing = REQUIRED_CLASSES - class_ids
    if missing:
        raise ValueError(f"taxonomy missing required classes: {sorted(missing)}")

    for item in classes:
        class_id = item["id"]
        shape = item.get("conversation_shape")
        if shape not in VALID_SHAPES:
            raise ValueError(f"{class_id}: invalid conversation shape")

        shape_contract = shapes[shape]
        if item.get("min_turns") != shape_contract["min_turns"]:
            raise ValueError(f"{class_id}: min_turns violates conversation shape")
        if item.get("max_turns") != shape_contract["max_turns"]:
            raise ValueError(f"{class_id}: max_turns violates conversation shape")

        applies_to = item.get("applies_to")
        if applies_to not in {"all", "none"}:
            if not isinstance(applies_to, list) or not applies_to:
                raise ValueError(f"{class_id}: applies_to must be all, none, or services")
            unknown = set(applies_to) - service_ids
            if unknown:
                raise ValueError(f"{class_id}: unknown services {sorted(unknown)}")

        conditions = item.get("evidence_conditions")
        if not isinstance(conditions, list) or not conditions:
            raise ValueError(f"{class_id}: evidence conditions are required")
        unknown_conditions = set(conditions) - evidence_conditions
        if unknown_conditions:
            raise ValueError(
                f"{class_id}: unknown evidence conditions {sorted(unknown_conditions)}"
            )

        for field in ("grading_focus", "generator_rules", "invariants"):
            values = item.get(field)
            if not isinstance(values, list) or not values:
                raise ValueError(f"{class_id}: {field} is required")

    by_id = {item["id"]: item for item in classes}
    if by_id["follow_up"]["conversation_shape"] != "follow_up":
        raise ValueError("follow_up must use follow_up conversation shape")
    if by_id["multi_turn"]["conversation_shape"] != "multi_turn":
        raise ValueError("multi_turn must use multi_turn conversation shape")
    if by_id["unsupported"]["applies_to"] != "none":
        raise ValueError("unsupported tests must not map to a supported service")


def taxonomy_summary(taxonomy: dict[str, Any]) -> dict[str, Any]:
    validate_taxonomy(taxonomy)
    return {
        "taxonomy_version": taxonomy["taxonomy_version"],
        "class_count": len(taxonomy["classes"]),
        "classes": [item["id"] for item in taxonomy["classes"]],
        "user_style_count": len(taxonomy["dimensions"]["user_styles"]),
        "evidence_condition_count": len(taxonomy["dimensions"]["evidence_conditions"]),
    }
