from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from typing import Any, Callable, Protocol
from urllib import error as urlerror
from urllib import request as urlrequest


RUN_RECORD_VERSION = "roberta_eval_run_record/v1"


class RobertaTransport(Protocol):
    name: str

    def send(self, question: str, *, case: dict[str, Any]) -> dict[str, Any]:
        ...


def roberta_endpoint(target: str) -> str:
    base = target.rstrip("/")
    if base.endswith("/v1/roberta"):
        return base
    return base + "/v1/roberta"


@dataclass
class HttpRobertaTransport:
    target: str
    timeout_seconds: float = 120.0
    evaluation_mode: str | None = None
    name: str = "http"

    def send(self, question: str, *, case: dict[str, Any]) -> dict[str, Any]:
        request_payload: dict[str, Any] = {"message": question}
        if self.evaluation_mode is not None:
            request_payload["evaluation_mode"] = self.evaluation_mode
        payload = json.dumps(request_payload).encode("utf-8")
        req = urlrequest.Request(
            roberta_endpoint(self.target),
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlrequest.urlopen(req, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except urlerror.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"ROBERTA HTTP {exc.code}: {body}") from exc
        except urlerror.URLError as exc:
            raise RuntimeError(f"ROBERTA connection failed: {exc.reason}") from exc

        try:
            decoded = json.loads(body)
        except json.JSONDecodeError as exc:
            raise RuntimeError("ROBERTA response was not valid JSON") from exc
        if not isinstance(decoded, dict):
            raise RuntimeError("ROBERTA response JSON must be an object")
        return decoded


@dataclass
class FixtureRobertaTransport:
    name: str = "fixture"

    def send(self, question: str, *, case: dict[str, Any]) -> dict[str, Any]:
        return {
            "service": "roberta_eval_fixture_transport",
            "status": "ok",
            "reply": "Deterministic fixture transport response.",
            "fixture": case["fixture"],
            "claims": [],
            "execution_authorized": False,
        }


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def execute_case(
    case: dict[str, Any],
    *,
    transport: RobertaTransport,
    run_id: str,
    target: str,
    clock: Callable[[], float] = time.perf_counter,
    now: Callable[[], datetime] = utc_now,
) -> dict[str, Any]:
    started_at = now()
    started_clock = clock()
    response: dict[str, Any] | None = None
    runtime_status = "ok"
    error_detail: dict[str, str] | None = None

    try:
        response = transport.send(case["question"], case=case)
        if response.get("status") == "error":
            runtime_status = "response_error"
    except Exception as exc:  # one bad case must not abort a large suite
        runtime_status = "transport_error"
        error_detail = {
            "type": type(exc).__name__,
            "message": str(exc),
        }

    elapsed_ms = max(0.0, (clock() - started_clock) * 1000.0)
    finished_at = now()

    return {
        "record_version": RUN_RECORD_VERSION,
        "run_id": run_id,
        "record_id": f"{run_id}:{case['case_id']}",
        "case_id": case["case_id"],
        "blueprint_id": case["blueprint_id"],
        "service": case["service"],
        "taxonomy_class": case["taxonomy_class"],
        "evidence_condition": case["evidence_condition"],
        "objective_signature": case["objective_signature"],
        "user_style": case["user_style"],
        "question": case["question"],
        "target": target,
        "transport": transport.name,
        "case_data_mode": case.get("case_data_mode", "synthetic_fixture"),
        "started_at": _iso(started_at),
        "finished_at": _iso(finished_at),
        "latency_ms": round(elapsed_ms, 3),
        "runtime_status": runtime_status,
        "response": response,
        "error": error_detail,
        "expected_checks": case["checks"],
    }


def select_cases(
    cases: list[dict[str, Any]],
    *,
    limit: int | None = None,
    strategy: str = "sequential",
) -> list[dict[str, Any]]:
    if limit is None:
        return list(cases)
    count = max(0, limit)
    if strategy == "sequential":
        return list(cases[:count])
    if strategy != "balanced":
        raise ValueError(f"unsupported case selection strategy: {strategy}")

    groups: dict[str, list[dict[str, Any]]] = {}
    group_order: list[str] = []
    for case in cases:
        key = str(case.get("service", ""))
        if key not in groups:
            groups[key] = []
            group_order.append(key)
        groups[key].append(case)

    selected: list[dict[str, Any]] = []
    offset = 0
    while len(selected) < count:
        added = False
        for key in group_order:
            bucket = groups[key]
            if offset < len(bucket):
                selected.append(bucket[offset])
                added = True
                if len(selected) >= count:
                    break
        if not added:
            break
        offset += 1
    return selected


def run_cases(
    cases: list[dict[str, Any]],
    *,
    transport: RobertaTransport,
    run_id: str,
    target: str,
    limit: int | None = None,
    selection: str = "sequential",
) -> list[dict[str, Any]]:
    selected = select_cases(cases, limit=limit, strategy=selection)
    return [
        execute_case(case, transport=transport, run_id=run_id, target=target)
        for case in selected
    ]


def serialize_run_jsonl(records: list[dict[str, Any]]) -> str:
    return "".join(
        json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
        for record in records
    )


def write_run(path: Path, records: list[dict[str, Any]]) -> None:
    path.write_text(serialize_run_jsonl(records), encoding="utf-8")


def run_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for record in records:
        counts[record["runtime_status"]] = counts.get(record["runtime_status"], 0) + 1
    return {
        "record_version": RUN_RECORD_VERSION,
        "record_count": len(records),
        "runtime_status_counts": counts,
        "services": sorted({record["service"] for record in records}),
        "transport": sorted({record["transport"] for record in records}),
    }
