import json
from pathlib import Path

import pytest

import roberta_eval.dashboard as dashboard_module
from roberta_eval.dashboard import build_dashboard, render_markdown
from roberta_eval.human_checkpoint_history import (
    accept_human_checkpoint,
    append_human_checkpoint,
    build_human_checkpoint,
    empty_human_checkpoint_history,
    human_checkpoint_history_summary,
    latest_human_checkpoint_report,
    load_human_checkpoint_history,
    write_human_checkpoint_history,
)
from roberta_eval.human_trends import build_human_trend_report
from roberta_eval.stress import run_stress_qualification


def _record(record_id: str, service: str, reply: str, *, question: str = "Should I trade?") -> dict:
    return {
        "record_version": "roberta_eval_run_record/v1",
        "run_id": "checkpoint-test",
        "record_id": record_id,
        "case_id": record_id,
        "blueprint_id": "checkpoint",
        "service": service,
        "taxonomy_class": "human_decision",
        "evidence_condition": "fixture_verified",
        "objective_signature": "checkpoint-test",
        "user_style": "plain",
        "question": question,
        "target": "fixture://local",
        "transport": "fixture",
        "case_data_mode": "synthetic_fixture",
        "runtime_status": "ok",
        "response": {
            "status": "ok",
            "reply": reply,
            "response_depth": "normal",
            "execution_authorized": False,
        },
        "error": None,
        "expected_checks": [],
    }


def _before() -> list[dict]:
    return [
        _record("b1", "pre_trade", "CMIS deterministic risk engine says the trade is uncertain."),
        _record("b2", "smart_route", "I'd use the lower-impact route because it should give you a better fill."),
    ]


def _after() -> list[dict]:
    return [
        _record("a1", "pre_trade", "I'd wait. I still can't confirm the likely slippage and final fill price."),
        _record("a2", "smart_route", "I'd use the lower-impact route because it should give you a better fill."),
    ]


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )


def _history_with_two() -> dict:
    history = empty_human_checkpoint_history()
    history, _ = append_human_checkpoint(
        history, build_human_checkpoint(_before(), checkpoint_id="human-001")
    )
    history, _ = append_human_checkpoint(
        history, build_human_checkpoint(_after(), checkpoint_id="human-002")
    )
    return history


def test_checkpoint_history_stores_metrics_not_raw_reply_or_local_path() -> None:
    records = _before()
    records[0]["_source_path"] = "/home/private/secret/replay.jsonl"
    checkpoint = build_human_checkpoint(records, checkpoint_id="safe-001")
    history, status = append_human_checkpoint(empty_human_checkpoint_history(), checkpoint)
    encoded = json.dumps(history, sort_keys=True)

    assert status == "APPENDED"
    assert "deterministic risk engine says the trade is uncertain" not in encoded
    assert "/home/private/secret" not in encoded
    assert "accepted_checkpoint:safe-001" in encoded
    assert history["policy"]["raw_responses_stored"] is False
    assert history["policy"]["local_paths_stored"] is False


def test_duplicate_checkpoint_id_is_idempotent_only_for_same_corpus() -> None:
    history = empty_human_checkpoint_history()
    first = build_human_checkpoint(_before(), checkpoint_id="same-id")
    history, status = append_human_checkpoint(history, first)
    assert status == "APPENDED"

    same_again = build_human_checkpoint(_before(), checkpoint_id="same-id")
    unchanged, status = append_human_checkpoint(history, same_again)
    assert status == "UNCHANGED"
    assert unchanged == history

    changed_records = _before()
    changed_records[0]["question"] = "Did the question change?"
    conflict = build_human_checkpoint(changed_records, checkpoint_id="same-id")
    with pytest.raises(ValueError, match="different corpus content"):
        append_human_checkpoint(history, conflict)


def test_latest_pair_report_uses_last_two_accepted_checkpoints() -> None:
    history = _history_with_two()
    report = latest_human_checkpoint_report(history)
    assert report is not None
    assert report["source_mode"] == "accepted_checkpoint_history"
    assert report["comparison"]["previous_snapshot_id"] == "human-001"
    assert report["comparison"]["current_snapshot_id"] == "human-002"
    assert report["comparison"]["judge_model_calls"] == 0
    assert report["comparison"]["external_calls"] == 0


def test_accept_checkpoint_persists_only_snapshot_history(tmp_path: Path) -> None:
    replay = tmp_path / "private-replay.jsonl"
    history_path = tmp_path / "history.json"
    _write_jsonl(replay, _before())
    write_human_checkpoint_history(history_path, empty_human_checkpoint_history())

    result = accept_human_checkpoint(
        replay,
        checkpoint_id="accepted-001",
        history_path=history_path,
    )
    persisted = history_path.read_text(encoding="utf-8")
    loaded = load_human_checkpoint_history(history_path)

    assert result["status"] == "APPENDED"
    assert result["judge_model_calls"] == 0
    assert result["external_calls"] == 0
    assert human_checkpoint_history_summary(loaded)["checkpoint_count"] == 1
    assert str(replay) not in persisted
    assert "deterministic risk engine says the trade is uncertain" not in persisted


def test_dashboard_automatically_uses_latest_accepted_pair(monkeypatch: pytest.MonkeyPatch) -> None:
    history = _history_with_two()
    monkeypatch.setattr(
        dashboard_module,
        "load_human_checkpoint_history",
        lambda: history,
    )
    view = build_dashboard(qualification=run_stress_qualification(limit=50))

    assert view["human_v2"]["available"] is True
    assert view["human_v2"]["source_mode"] == "accepted_checkpoint_history"
    assert view["human_v2"]["comparison_checkpoint_ids"] == {
        "previous": "human-001",
        "current": "human-002",
    }
    assert view["human_v2"]["accepted_checkpoint_count"] == 2
    assert view["advisory"]["average_human_quality"] == history["checkpoints"][-1]["quality"]["average_overall_score"]
    assert "accepted_checkpoint_history" in render_markdown(view)


def test_dashboard_does_not_invent_trend_with_one_checkpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    history = empty_human_checkpoint_history()
    history, _ = append_human_checkpoint(
        history, build_human_checkpoint(_before(), checkpoint_id="only-one")
    )
    monkeypatch.setattr(
        dashboard_module,
        "load_human_checkpoint_history",
        lambda: history,
    )
    view = build_dashboard(qualification=run_stress_qualification(limit=50))
    assert view["human_v2"]["available"] is False
    assert view["human_v2"]["accepted_checkpoint_count"] == 1
    assert view["human_v2"]["latest_checkpoint_id"] == "only-one"
    assert "not enough accepted checkpoints yet" in render_markdown(view)


def test_explicit_replay_report_overrides_accepted_history(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    history = _history_with_two()
    monkeypatch.setattr(
        dashboard_module,
        "load_human_checkpoint_history",
        lambda: history,
    )
    before_path = tmp_path / "before.jsonl"
    after_path = tmp_path / "after.jsonl"
    _write_jsonl(before_path, _before())
    _write_jsonl(after_path, _after())
    explicit = build_human_trend_report(
        before_path,
        after_path,
        previous_id="manual-before",
        current_id="manual-after",
    )

    view = build_dashboard(
        qualification=run_stress_qualification(limit=50),
        human_trend_report=explicit,
    )
    assert view["human_v2"]["source_mode"] == "explicit_replay_pair"
    assert view["human_v2"]["comparison_checkpoint_ids"] == {
        "previous": "manual-before",
        "current": "manual-after",
    }
    assert view["human_v2"]["accepted_checkpoint_count"] == 2
