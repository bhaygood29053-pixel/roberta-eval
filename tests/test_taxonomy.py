import copy

import pytest

from roberta_eval.registry import load_registry
from roberta_eval.taxonomy import (
    REQUIRED_CLASSES,
    load_taxonomy,
    taxonomy_summary,
    validate_taxonomy,
)


def test_taxonomy_validates_against_capability_registry() -> None:
    taxonomy = load_taxonomy()
    validate_taxonomy(taxonomy, load_registry())
    assert REQUIRED_CLASSES <= {item["id"] for item in taxonomy["classes"]}


def test_taxonomy_separates_evidence_style_and_conversation_dimensions() -> None:
    taxonomy = load_taxonomy()
    dimensions = taxonomy["dimensions"]
    assert "stale" in dimensions["evidence_conditions"]
    assert "pressuring" in dimensions["user_styles"]
    assert "multi_turn" in dimensions["conversation_shapes"]


def test_objective_preservation_rule_is_explicit() -> None:
    rule = load_taxonomy()["objective_preservation_rule"]
    assert "must not silently change" in rule
    assert "expected invariant" in rule


def test_taxonomy_rejects_duplicate_class_ids() -> None:
    taxonomy = load_taxonomy()
    taxonomy["classes"].append(copy.deepcopy(taxonomy["classes"][0]))
    with pytest.raises(ValueError, match="duplicate class ids"):
        validate_taxonomy(taxonomy)


def test_taxonomy_rejects_unknown_service_reference() -> None:
    taxonomy = load_taxonomy()
    taxonomy["classes"][0]["applies_to"] = ["not_a_service"]
    with pytest.raises(ValueError, match="unknown services"):
        validate_taxonomy(taxonomy)


def test_follow_up_requires_exactly_two_turns() -> None:
    taxonomy = load_taxonomy()
    item = next(value for value in taxonomy["classes"] if value["id"] == "follow_up")
    item["max_turns"] = 3
    with pytest.raises(ValueError, match="max_turns"):
        validate_taxonomy(taxonomy)


def test_multi_turn_requires_three_or_more_turns() -> None:
    taxonomy = load_taxonomy()
    item = next(value for value in taxonomy["classes"] if value["id"] == "multi_turn")
    item["min_turns"] = 2
    with pytest.raises(ValueError, match="min_turns"):
        validate_taxonomy(taxonomy)


def test_unsupported_does_not_map_to_supported_service() -> None:
    taxonomy = load_taxonomy()
    item = next(value for value in taxonomy["classes"] if value["id"] == "unsupported")
    item["applies_to"] = ["market_report"]
    with pytest.raises(ValueError, match="unsupported tests"):
        validate_taxonomy(taxonomy)


def test_taxonomy_summary_reports_dimensions() -> None:
    summary = taxonomy_summary(load_taxonomy())
    assert summary["class_count"] >= 12
    assert summary["user_style_count"] >= 5
    assert summary["evidence_condition_count"] >= 5
