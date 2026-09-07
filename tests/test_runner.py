from __future__ import annotations

from datetime import datetime, timezone
import io
import json
from urllib import request as urlrequest

import pytest

from roberta_eval.corpus import materialize_cases
from roberta_eval.runner import (
    FixtureRobertaTransport,
    HttpRobertaTransport,
    RUN_RECORD_VERSION,
    execute_case,
    roberta_endpoint,
    run_cases,
    run_summary,
    serialize_run_jsonl,
)


class _Clock:
    def __init__(self) -> None:
        self.value = 10.0

    def __call__(self) -> float:
        current = self.value
        self.value += 0.025
        return current


class _Now:
    def __call__(self) -> datetime:
        return datetime(2026, 9, 7, 1, 0, 0, tzinfo=timezone.utc)


class _FailingTransport:
    name = "failing"

    def send(self, question, *, case):
        raise RuntimeError("boom")


def test_endpoint_appends_bridge_path_once() -> None:
    assert roberta_endpoint("http://127.0.0.1:8766") == "http://127.0.0.1:8766/v1/roberta"
    assert roberta_endpoint("http://127.0.0.1:8766/v1/roberta") == "http://127.0.0.1:8766/v1/roberta"


def test_fixture_transport_produces_normalized_run_record() -> None:
    case = materialize_cases()[0]
    record = execute_case(
        case,
        transport=FixtureRobertaTransport(),
        run_id="run-test",
        target="fixture://local",
        clock=_Clock(),
        now=_Now(),
    )
    assert record["record_version"] == RUN_RECORD_VERSION
    assert record["record_id"] == f"run-test:{case['case_id']}"
    assert record["runtime_status"] == "ok"
    assert record["response"]["execution_authorized"] is False
    assert record["expected_checks"] == case["checks"]
    assert record["latency_ms"] == 25.0


def test_transport_error_becomes_record_instead_of_suite_crash() -> None:
    case = materialize_cases()[0]
    record = execute_case(
        case,
        transport=_FailingTransport(),
        run_id="run-error",
        target="test://failure",
        clock=_Clock(),
        now=_Now(),
    )
    assert record["runtime_status"] == "transport_error"
    assert record["response"] is None
    assert record["error"]["type"] == "RuntimeError"
    assert record["error"]["message"] == "boom"


def test_suite_limit_and_jsonl_are_machine_readable() -> None:
    records = run_cases(
        materialize_cases(),
        transport=FixtureRobertaTransport(),
        run_id="run-five",
        target="fixture://local",
        limit=5,
    )
    assert len(records) == 5
    payload = serialize_run_jsonl(records)
    decoded = [json.loads(line) for line in payload.splitlines()]
    assert len(decoded) == 5
    assert run_summary(records)["runtime_status_counts"] == {"ok": 5}


def test_http_transport_parses_bridge_json(monkeypatch) -> None:
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(
                {"service": "roberta_bridge", "status": "ok", "reply": "hello"}
            ).encode("utf-8")

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(urlrequest, "urlopen", fake_urlopen)
    case = materialize_cases()[0]
    response = HttpRobertaTransport("http://127.0.0.1:8766", timeout_seconds=7).send(
        case["question"], case=case
    )
    assert captured["url"] == "http://127.0.0.1:8766/v1/roberta"
    assert captured["body"] == {"message": case["question"]}
    assert captured["timeout"] == 7
    assert response["reply"] == "hello"


def test_http_transport_adds_evaluation_mode_only_when_requested(monkeypatch) -> None:
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(
                {"service": "roberta_bridge", "status": "ok", "reply": "hello"}
            ).encode("utf-8")

    def fake_urlopen(req, timeout):
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr(urlrequest, "urlopen", fake_urlopen)
    case = materialize_cases()[0]
    HttpRobertaTransport(
        "http://127.0.0.1:8766",
        evaluation_mode="roberta_evaluation_telemetry/v1",
    ).send(case["question"], case=case)

    assert captured["body"] == {
        "message": case["question"],
        "evaluation_mode": "roberta_evaluation_telemetry/v1",
    }


def test_http_transport_rejects_non_json(monkeypatch) -> None:
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b"not-json"

    monkeypatch.setattr(urlrequest, "urlopen", lambda req, timeout: FakeResponse())
    with pytest.raises(RuntimeError, match="not valid JSON"):
        HttpRobertaTransport("http://127.0.0.1:8766").send(
            "test", case=materialize_cases()[0]
        )
