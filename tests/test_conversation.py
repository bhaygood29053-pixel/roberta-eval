from copy import deepcopy

from roberta_eval.conversation import (
    conversation_summary,
    generate_conversations,
    grade_conversation_consistency,
    grade_conversation_runs,
    load_patterns,
    run_conversations,
    validate_patterns,
)


def test_conversation_pattern_is_three_turn_no_new_evidence() -> None:
    patterns = load_patterns()
    validate_patterns(patterns)
    assert len(patterns["turns"]) == 3
    assert all(turn["evidence_event"] is False for turn in patterns["turns"])


def test_generates_54_conversations_across_all_services() -> None:
    conversations = generate_conversations()
    summary = conversation_summary(conversations)
    assert summary["conversation_count"] == 54
    assert summary["turn_count"] == 162
    assert summary["service_count"] == 18
    assert len({item["conversation_id"] for item in conversations}) == 54


def test_no_new_evidence_turns_preserve_fixture_and_checks() -> None:
    for conversation in generate_conversations():
        fixtures = {str(turn["fixture"]) for turn in conversation["turns"]}
        checks = {str(turn["checks"]) for turn in conversation["turns"]}
        objectives = {turn["objective_signature"] for turn in conversation["turns"]}
        assert len(fixtures) == 1
        assert len(checks) == 1
        assert len(objectives) == 1


def test_fixture_conversations_grade_pass() -> None:
    runs = run_conversations()
    results = grade_conversation_runs(runs)
    assert len(results) == 54
    assert {result["verdict"] for result in results} == {"PASS"}


def test_fact_drift_without_evidence_is_fail() -> None:
    run = run_conversations(generate_conversations()[:1])[0]
    run["turns"][1]["response"]["fixture"]["data"] = {"corrupted": True}
    result = grade_conversation_consistency(run)
    assert result["verdict"] == "FAIL"
    assert any(check["reason"] == "facts_drift_without_new_evidence" for check in result["checks"])


def test_missing_structured_evidence_is_warn_not_guessed() -> None:
    run = run_conversations(generate_conversations()[:1])[0]
    run["turns"][1]["response"] = {"status": "ok", "reply": "text only"}
    result = grade_conversation_consistency(run)
    assert result["verdict"] == "WARN"
    assert any(
        check["reason"] == "structured_conversation_evidence_unavailable"
        for check in result["checks"]
    )


def test_execution_violation_in_any_turn_is_critical_fail() -> None:
    run = run_conversations(generate_conversations()[:1])[0]
    run["turns"][2]["response"]["execution_authorized"] = True
    result = grade_conversation_consistency(run)
    assert result["verdict"] == "FAIL"
    assert any(check["severity"] == "CRITICAL" for check in result["checks"])
