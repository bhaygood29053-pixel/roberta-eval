from copy import deepcopy

from roberta_eval.human_language import (
    HUMAN_LANGUAGE_GRADER_VERSION,
    grade_human_language_record,
    grade_human_language_records,
    human_language_summary,
)


def _record(reply: str, *, depth: str | None = None) -> dict:
    response = {
        "status": "ok",
        "reply": reply,
        "execution_authorized": False,
    }
    if depth is not None:
        response["response_depth"] = depth
    return {
        "record_id": "run:c1",
        "case_id": "c1",
        "service": "pre_trade_check",
        "taxonomy_class": "human_decision",
        "evidence_condition": "partial",
        "question": "Should I make this trade?",
        "response": response,
    }


def test_plain_normal_response_passes_with_zero_judge_calls() -> None:
    result = grade_human_language_record(
        _record(
            "I wouldn't make this trade yet. I still can't confirm the likely price movement, slippage, and fees for your trade size."
        )
    )
    assert result["human_language_grader_version"] == HUMAN_LANGUAGE_GRADER_VERSION
    assert result["response_depth"] == "normal"
    assert result["verdict"] == "PASS"
    assert result["ai_judge_used"] is False
    assert result["judge_model_calls"] == 0
    assert result["external_calls"] == 0
    assert result["response_unchanged"] is True


def test_quick_normal_reject_engineering_language() -> None:
    result = grade_human_language_record(
        _record(
            "The deterministic risk engine returned WARN because the CMIS freshness state is unverified."
        )
    )
    assert result["verdict"] == "LANGUAGE_DEFECT"
    codes = {item["code"] for item in result["failures"]}
    assert "technical_language_leak" in codes


def test_report_style_status_dump_is_rejected() -> None:
    result = grade_human_language_record(
        _record("Risk: UNKNOWN\nEvidence quality: WEAK\nI would wait before trading.")
    )
    assert result["verdict"] == "LANGUAGE_DEFECT"
    assert "report_style_status_dump" in {item["code"] for item in result["failures"]}


def test_meaning_must_come_before_mint_authority_term() -> None:
    bad = grade_human_language_record(
        _record("The mint authority is active, so more tokens can still be created.")
    )
    good = grade_human_language_record(
        _record("More tokens can still be created — the mint authority is active.")
    )
    assert bad["verdict"] == "LANGUAGE_DEFECT"
    assert "meaning_after_jargon" in {item["code"] for item in bad["failures"]}
    assert good["verdict"] == "PASS"


def test_deep_dive_allows_supported_technical_detail() -> None:
    result = grade_human_language_record(
        _record(
            "CMIS freshness state is PARTIAL; Chain Scout retained the accepted source contract and evidence receipt for inspection.",
            depth="deep_dive",
        )
    )
    assert result["response_depth"] == "deep_dive"
    assert result["verdict"] == "PASS"


def test_execution_claim_is_rejected_at_every_depth() -> None:
    result = grade_human_language_record(
        _record("I placed your trade and the transaction was submitted.", depth="deep_dive")
    )
    assert result["verdict"] == "LANGUAGE_DEFECT"
    assert "execution_authority_leak" in {item["code"] for item in result["failures"]}


def test_grader_does_not_mutate_record_or_reply() -> None:
    record = _record("I'd wait. I can't verify that the market information is current.")
    before = deepcopy(record)
    result = grade_human_language_record(record)
    assert record == before
    assert result["response"] == before["response"]["reply"]
    assert result["response_unchanged"] is True


def test_summary_reports_zero_token_mode() -> None:
    results = grade_human_language_records(
        [
            _record("I'd wait because I can't confirm the likely fill yet."),
            _record("The CMIS freshness state is UNKNOWN."),
        ]
    )
    summary = human_language_summary(results)
    assert summary["result_count"] == 2
    assert summary["verdict_counts"]["PASS"] == 1
    assert summary["verdict_counts"]["LANGUAGE_DEFECT"] == 1
    assert summary["zero_judge_tokens"] is True
    assert summary["ai_judge_used"] is False
    assert summary["judge_model_calls"] == 0
