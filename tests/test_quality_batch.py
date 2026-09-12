from __future__ import annotations

import json
from pathlib import Path

import pytest

from roberta_eval.grader import RUN_RECORD_VERSION, load_run_jsonl
from roberta_eval.quality import grade_human_quality_records, human_quality_summary


def _run_record(record_id: str, service: str, reply: str, *, depth: str = "normal") -> dict:
    return {
        "record_version": RUN_RECORD_VERSION,
        "run_id": "saved-replay",
        "record_id": record_id,
        "case_id": record_id,
        "blueprint_id": "saved",
        "service": service,
        "taxonomy_class": "human_decision",
        "evidence_condition": "fixture_verified",
        "objective_signature": "saved-replay",
        "user_style": "normal",
        "question": "Should I act on this?",
        "target": "saved://offline",
        "transport": "saved",
        "case_data_mode": "saved_run",
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


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_quality_replays_saved_run_directory_recursively(tmp_path: Path) -> None:
    repeated_reply = "I'd wait. I can't confirm the numbers are current yet."
    _write_jsonl(
        tmp_path / "run-a.jsonl",
        [
            _run_record("a1", "pre_trade", repeated_reply),
            _run_record("a2", "smart_route", repeated_reply),
        ],
    )
    _write_jsonl(
        tmp_path / "nested" / "run-b.jsonl",
        [
            _run_record(
                "b1",
                "token_risk",
                "Risk: UNKNOWN\nThe deterministic risk engine returned no result.",
            )
        ],
    )
    # Grade output beside saved runs must not be re-ingested as a run record.
    _write_jsonl(
        tmp_path / "nested" / "old-quality.jsonl",
        [{"quality_grader_version": "old", "verdict": "PASS"}],
    )

    records = load_run_jsonl(tmp_path)
    results = grade_human_quality_records(records)
    summary = human_quality_summary(results)
    human = summary["human_v2"]

    assert len(records) == 3
    assert human["source_file_count"] == 2
    assert human["unique_response_count"] == 2
    assert human["duplicate_response_record_count"] == 1
    assert human["verdict_counts"] == {"PASS": 2, "LANGUAGE_DEFECT": 1}
    assert human["by_service"]["token_risk"]["LANGUAGE_DEFECT"] == 1
    assert human["failure_code_counts"]["technical_language_leak"] == 1
    assert human["failure_code_counts"]["report_style_status_dump"] == 1
    assert human["ai_judge_used"] is False
    assert human["judge_model_calls"] == 0
    assert human["external_calls"] == 0
    assert human["zero_judge_tokens"] is True
    assert all(item["human_v2"]["response_unchanged"] is True for item in results)


def test_single_file_quality_input_remains_supported(tmp_path: Path) -> None:
    path = tmp_path / "one.jsonl"
    _write_jsonl(path, [_run_record("one", "daily_brief", "I'd watch this for now.")])

    records = load_run_jsonl(path)
    summary = human_quality_summary(grade_human_quality_records(records))["human_v2"]

    assert len(records) == 1
    assert summary["source_file_count"] == 1
    assert summary["verdict_counts"]["PASS"] == 1


def test_directory_without_run_records_fails_closed(tmp_path: Path) -> None:
    _write_jsonl(tmp_path / "grades.jsonl", [{"verdict": "PASS"}])

    with pytest.raises(ValueError, match="no roberta_eval_run_record/v1 JSONL run files"):
        load_run_jsonl(tmp_path)
