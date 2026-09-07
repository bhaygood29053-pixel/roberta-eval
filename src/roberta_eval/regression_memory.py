from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

MEMORY_VERSION = "roberta_regression_memory/v1"


def memory_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "regression_memory.json"


def load_memory(path: Path | None = None) -> dict[str, Any]:
    source = path or memory_path()
    return json.loads(source.read_text(encoding="utf-8"))


def validate_memory(memory: dict[str, Any]) -> None:
    if memory.get("memory_version") != MEMORY_VERSION:
        raise ValueError("unsupported regression memory version")
    if not memory.get("policy"):
        raise ValueError("regression memory policy is required")
    records = memory.get("records")
    if not isinstance(records, list):
        raise ValueError("regression records must be a list")
    ids = [item.get("regression_id") for item in records]
    if any(not value for value in ids) or len(ids) != len(set(ids)):
        raise ValueError("regression IDs must be unique and non-empty")
    for record in records:
        if record.get("status") != "active":
            raise ValueError(f"{record.get('regression_id')}: invalid status")
        if record.get("execution_authorized") is not False:
            raise ValueError(f"{record.get('regression_id')}: execution must remain unauthorized")
        replay = record.get("replay_case")
        if not isinstance(replay, dict):
            raise ValueError(f"{record.get('regression_id')}: replay case is required")
        if not replay.get("case_id") or not replay.get("objective_signature"):
            raise ValueError(f"{record.get('regression_id')}: replay case identity is incomplete")
        if not replay.get("checks"):
            raise ValueError(f"{record.get('regression_id')}: replay checks are required")


def _regression_id(cluster_id: str, case_id: str) -> str:
    payload = f"{cluster_id}|{case_id}"
    return "regression::" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def promote_cluster(
    memory: dict[str, Any],
    cluster: dict[str, Any],
    source_case: dict[str, Any],
    *,
    confirmed: bool,
) -> dict[str, Any]:
    validate_memory(memory)
    if not confirmed:
        raise ValueError("regression promotion requires confirmed=true")
    if not cluster.get("actionable_product_defect"):
        raise ValueError("cluster is not an actionable product defect")
    if cluster.get("evaluation_incomplete"):
        raise ValueError("evaluation-incomplete cluster cannot become regression memory")
    if cluster.get("category") in {"EVALUATION_INCOMPLETE", "EVALUATION_ERROR"}:
        raise ValueError("evaluation-system cluster cannot become regression memory")
    if source_case.get("service") != cluster.get("service"):
        raise ValueError("source case service does not match cluster service")
    if not source_case.get("checks"):
        raise ValueError("source case is not replayable")

    rid = _regression_id(str(cluster["cluster_id"]), str(source_case["case_id"]))
    existing = {item["regression_id"]: item for item in memory["records"]}
    if rid in existing:
        return memory

    record = {
        "regression_id": rid,
        "status": "active",
        "cluster_id": cluster["cluster_id"],
        "category": cluster["category"],
        "severity": cluster["severity"],
        "service": cluster["service"],
        "likely_layer": cluster.get("likely_layer", "unknown"),
        "reason": cluster["reason"],
        "source_case_id": source_case["case_id"],
        "execution_authorized": False,
        "replay_case": {
            key: deepcopy(source_case[key])
            for key in (
                "case_id",
                "service",
                "taxonomy_class",
                "evidence_condition",
                "objective_signature",
                "question",
                "fixture",
                "checks",
            )
            if key in source_case
        },
    }
    updated = deepcopy(memory)
    updated["records"].append(record)
    updated["records"].sort(key=lambda item: item["regression_id"])
    validate_memory(updated)
    return updated


def memory_summary(memory: dict[str, Any] | None = None) -> dict[str, Any]:
    memory = memory or load_memory()
    validate_memory(memory)
    records = memory["records"]
    return {
        "memory_version": MEMORY_VERSION,
        "active_regression_count": len(records),
        "services": sorted({item["service"] for item in records}),
        "critical_count": sum(1 for item in records if item["severity"] == "CRITICAL"),
    }


def write_memory(path: Path, memory: dict[str, Any]) -> None:
    validate_memory(memory)
    path.write_text(json.dumps(memory, indent=2, sort_keys=True) + "\n", encoding="utf-8")
