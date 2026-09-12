import json
from pathlib import Path

from roberta_eval.human_trends import (
    build_human_trend_report,
    build_human_trend_snapshot,
    compare_human_trend_snapshots,
    render_human_trend_markdown,
)


def _record(record_id: str, service: str, reply: str, *, depth: str = "normal") -> dict:
    return {
        "record_version": "roberta_eval_run_record/v1",
        "run_id": "trend-test",
        "record_id": record_id,
        "case_id": record_id,
        "blueprint_id": "trend",
        "service": service,
        "taxonomy_class": "human_decision",
        "evidence_condition": "fixture_verified",
        "objective_signature": "trend-test",
        "user_style": "plain",
        "question": "Should I make this trade?",
        "target": "fixture://local",
        "transport": "fixture",
        "case_data_mode": "synthetic_fixture",
        "runtime_status": "ok",
        "response": {
            "status": "ok",
            "reply": reply,
            "response_depth": depth,
            "execution_authorized": False,
        },
        "error": None,
        "expected_checks": [],
    }


def _previous_records() -> list[dict]:
    return [
        _record("p1", "pre_trade", "CMIS deterministic risk engine says the trade is uncertain."),
        _record("p2", "pre_trade", "Risk: UNKNOWN\nI would wait before trading."),
        _record("p3", "smart_route", "I'd use the lower-impact route because it should give you a better fill."),
        _record("p4", "wallet_relationship", "I found a direct transfer between the two wallets."),
    ]


def _current_records() -> list[dict]:
    return [
        _record("c1", "pre_trade", "CMIS still cannot confirm enough information for a reliable trade assessment."),
        _record("c2", "pre_trade", "I'd wait. I still can't confirm the likely slippage and final fill price."),
        _record("c3", "smart_route", "I'd use the lower-impact route because it should give you a better fill."),
        _record("c4", "wallet_relationship", "I found a direct transfer between the two wallets."),
        _record("c5", "wallet_relationship", "Mint authority is active, so I would be careful."),
        _record("c6", "burn_intelligence", "The burn is verified and permanently reduced the tracked supply."),
    ]


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )


def test_snapshot_is_zero_token_and_normalized() -> None:
    snapshot = build_human_trend_snapshot(
        _previous_records(),
        snapshot_id="before",
        source="fixture://before",
    )
    assert snapshot["result_count"] == 4
    assert snapshot["defect_count"] == 2
    assert snapshot["defect_rate"] == 0.5
    assert snapshot["judge_model_calls"] == 0
    assert snapshot["external_calls"] == 0
    assert snapshot["zero_judge_tokens"] is True


def test_comparison_uses_rates_and_ranks_worst_service() -> None:
    before = build_human_trend_snapshot(
        _previous_records(), snapshot_id="before", source="fixture://before"
    )
    after = build_human_trend_snapshot(
        _current_records(), snapshot_id="after", source="fixture://after"
    )
    report = compare_human_trend_snapshots(before, after)

    assert report["overall"]["previous_defect_rate"] == 0.5
    assert report["overall"]["current_defect_rate"] == 0.333333
    assert report["overall"]["defect_rate_delta_pp"] == -16.67
    assert report["overall"]["defect_direction"] == "IMPROVED"
    assert report["worst_current_services"][0]["service"] == "pre_trade"
    assert report["worst_current_services"][0]["defect_rate"] == 0.5


def test_recurring_new_and_resolved_defects_are_distinguished() -> None:
    before = build_human_trend_snapshot(
        _previous_records(), snapshot_id="before", source="fixture://before"
    )
    after = build_human_trend_snapshot(
        _current_records(), snapshot_id="after", source="fixture://after"
    )
    report = compare_human_trend_snapshots(before, after)
    defects = report["failure_code_trends"]

    assert defects["technical_language_leak"]["recurrence"] == "RECURRENT"
    assert defects["report_style_status_dump"]["recurrence"] == "RESOLVED"
    assert defects["meaning_after_jargon"]["recurrence"] == "NEW"
    assert [item["code"] for item in report["recurring_current_defects"]] == [
        "technical_language_leak"
    ]


def test_deep_dive_technical_language_is_not_counted_as_defect() -> None:
    snapshot = build_human_trend_snapshot(
        [_record("d1", "pre_trade", "CMIS deterministic risk engine details follow.", depth="deep_dive")],
        snapshot_id="deep",
        source="fixture://deep",
    )
    assert snapshot["defect_rate"] == 0.0


def test_file_report_and_markdown_are_offline_and_human_readable(tmp_path: Path) -> None:
    before_path = tmp_path / "before.jsonl"
    after_path = tmp_path / "after.jsonl"
    _write_jsonl(before_path, _previous_records())
    _write_jsonl(after_path, _current_records())

    report = build_human_trend_report(
        before_path,
        after_path,
        previous_id="build-a",
        current_id="build-b",
    )
    comparison = report["comparison"]
    markdown = render_human_trend_markdown(report)

    assert comparison["previous_snapshot_id"] == "build-a"
    assert comparison["current_snapshot_id"] == "build-b"
    assert comparison["ai_judge_used"] is False
    assert comparison["judge_model_calls"] == 0
    assert comparison["external_calls"] == 0
    assert "50.00% → 33.33%" in markdown
    assert "pre_trade" in markdown
    assert "`technical_language_leak`" in markdown
