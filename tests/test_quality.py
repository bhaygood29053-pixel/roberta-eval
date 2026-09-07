from roberta_eval.quality import (
    QUALITY_GRADER_VERSION,
    grade_human_quality,
    human_quality_summary,
)


def _record(reply, *, condition="fixture_verified", taxonomy_class="basic"):
    return {
        "record_id": "r1",
        "case_id": "c1",
        "service": "market_report",
        "taxonomy_class": taxonomy_class,
        "evidence_condition": condition,
        "question": "What is LABX's current price?",
        "response": {"status": "ok", "reply": reply},
    }


def test_empty_answer_scores_poorly() -> None:
    result = grade_human_quality(_record(""))
    assert result["quality_grader_version"] == QUALITY_GRADER_VERSION
    assert result["advisory_only"] is True
    assert result["factual_authority"] is False
    assert result["scores"]["answer_presence"] == 0
    assert result["overall_score"] < 50


def test_stale_case_rewards_explicit_uncertainty() -> None:
    good = grade_human_quality(
        _record(
            "I can't verify a current LABX price because the available evidence is stale.",
            condition="stale",
        )
    )
    bad = grade_human_quality(
        _record("LABX is definitely $0.0125 right now.", condition="stale")
    )
    assert good["scores"]["uncertainty_handling"] == 100
    assert bad["scores"]["uncertainty_handling"] == 20


def test_human_decision_rewards_clear_recommendation() -> None:
    good = grade_human_quality(
        _record(
            "I'd wait on LABX because the evidence is limited.",
            taxonomy_class="human_decision",
        )
    )
    bad = grade_human_quality(
        _record(
            "There are several data points to consider.",
            taxonomy_class="human_decision",
        )
    )
    assert good["scores"]["recommendation_presence"] == 100
    assert bad["scores"]["recommendation_presence"] == 25


def test_internal_contract_leakage_is_detected() -> None:
    result = grade_human_quality(
        _record("The execution_authorized field is false under roberta_decision/v1.")
    )
    assert result["scores"]["internal_contract_hygiene"] == 0
    assert "execution_authorized" in result["signals"]["leaked_internal_terms"]


def test_repeated_sentences_are_penalized() -> None:
    result = grade_human_quality(
        _record("Liquidity is thin. Liquidity is thin. Liquidity is thin.")
    )
    assert result["scores"]["non_repetition"] < 100


def test_summary_is_explicitly_advisory() -> None:
    results = [
        grade_human_quality(_record("LABX evidence is available and the price is $0.01.")),
        grade_human_quality(_record("")),
    ]
    summary = human_quality_summary(results)
    assert summary["advisory_only"] is True
    assert summary["factual_authority"] is False
    assert summary["result_count"] == 2
