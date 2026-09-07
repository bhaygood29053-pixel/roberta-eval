import json

from roberta_eval.adversarial import (
    adversarial_digest,
    adversarial_summary,
    generate_adversarial_cases,
    load_attacks,
    validate_attacks,
)
from roberta_eval.corpus import serialize_jsonl


def test_attack_catalog_is_valid() -> None:
    document = load_attacks()
    validate_attacks(document)
    ids = {item["id"] for item in document["attacks"]}
    assert {"ignore_evidence", "broaden_scope", "execution_pressure", "suppress_uncertainty"} <= ids


def test_adversarial_suite_has_432_cases_and_all_services() -> None:
    cases = generate_adversarial_cases()
    assert len(cases) == 432
    assert len({case["case_id"] for case in cases}) == 432
    assert len({case["service"] for case in cases}) == 18
    assert len({case["attack_id"] for case in cases}) == 8


def test_attacks_preserve_fixture_objective_and_original_checks() -> None:
    grouped = {}
    for case in generate_adversarial_cases():
        grouped.setdefault(case["blueprint_id"], []).append(case)

    for variants in grouped.values():
        assert len({item["objective_signature"] for item in variants}) == 1
        assert len({json.dumps(item["fixture"], sort_keys=True) for item in variants}) == 1
        assert len({json.dumps(item["source_checks"], sort_keys=True) for item in variants}) == 1


def test_each_attack_adds_explicit_target_and_forbidden_check() -> None:
    attacks = {item["id"]: item for item in load_attacks()["attacks"]}
    for case in generate_adversarial_cases():
        attack = attacks[case["attack_id"]]
        assert case["target_invariant"] == attack["target_invariant"]
        assert {
            "kind": "forbidden_conclusion",
            "value": attack["extra_forbidden"],
        } in case["checks"]


def test_adversarial_generation_is_reproducible() -> None:
    first = generate_adversarial_cases()
    second = generate_adversarial_cases()
    assert serialize_jsonl(first) == serialize_jsonl(second)
    assert adversarial_digest(first) == adversarial_digest(second)


def test_adversarial_summary_shape() -> None:
    summary = adversarial_summary()
    assert summary["case_count"] == 432
    assert summary["service_count"] == 18
    assert summary["blueprint_count"] == 54
    assert summary["attack_count"] == 8
    assert len(summary["sha256"]) == 64
