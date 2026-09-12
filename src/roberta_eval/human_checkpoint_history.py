from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from .grader import load_run_jsonl
from .human_trends import (
    build_human_trend_snapshot,
    compare_human_trend_snapshots,
    validate_human_trend_snapshot,
)
from .quality import grade_human_quality_records, human_quality_summary

HUMAN_CHECKPOINT_HISTORY_VERSION = "roberta_human_language_checkpoint_history/v1"


def default_human_checkpoint_history_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "human_checkpoint_history.json"


def empty_human_checkpoint_history() -> dict[str, Any]:
    return {
        "history_version": HUMAN_CHECKPOINT_HISTORY_VERSION,
        "policy": {
            "acceptance": "explicit_only",
            "raw_responses_stored": False,
            "local_paths_stored": False,
            "checkpoint_id_reuse": "idempotent_same_corpus_only",
            "comparison": "latest_two_accepted",
            "advisory_only": True,
            "factual_authority": False,
            "execution_authorized": False,
        },
        "checkpoints": [],
    }


def load_human_checkpoint_history(path: Path | None = None) -> dict[str, Any]:
    source = path or default_human_checkpoint_history_path()
    history = json.loads(source.read_text(encoding="utf-8"))
    validate_human_checkpoint_history(history)
    return history


def write_human_checkpoint_history(path: Path, history: dict[str, Any]) -> None:
    validate_human_checkpoint_history(history)
    path.write_text(json.dumps(history, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _corpus_fingerprint(records: list[dict[str, Any]]) -> str:
    sanitized: list[dict[str, Any]] = []
    for record in records:
        row = {key: value for key, value in record.items() if key != "_source_path"}
        sanitized.append(row)
    sanitized.sort(
        key=lambda row: (
            str(row.get("record_id") or ""),
            str(row.get("case_id") or ""),
            str(row.get("service") or ""),
        )
    )
    payload = json.dumps(sanitized, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_human_checkpoint(
    records: list[dict[str, Any]],
    *,
    checkpoint_id: str,
) -> dict[str, Any]:
    checkpoint_id = checkpoint_id.strip()
    if not checkpoint_id:
        raise ValueError("checkpoint_id is required")

    quality_results = grade_human_quality_records(records)
    quality = human_quality_summary(quality_results)
    snapshot = build_human_trend_snapshot(
        records,
        snapshot_id=checkpoint_id,
        source=f"accepted_checkpoint:{checkpoint_id}",
    )
    return {
        "checkpoint_id": checkpoint_id,
        "corpus_sha256": _corpus_fingerprint(records),
        "snapshot": snapshot,
        "quality": {
            "result_count": int(quality["result_count"]),
            "average_overall_score": float(quality["average_overall_score"]),
            "internal_leakage_count": int(quality["internal_leakage_count"]),
            "advisory_only": True,
            "factual_authority": False,
            "ai_judge_used": False,
            "judge_model_calls": 0,
            "zero_judge_tokens": True,
        },
    }


def validate_human_checkpoint_history(history: dict[str, Any]) -> None:
    if history.get("history_version") != HUMAN_CHECKPOINT_HISTORY_VERSION:
        raise ValueError("unsupported Human checkpoint history version")
    policy = history.get("policy")
    if not isinstance(policy, dict):
        raise ValueError("Human checkpoint history policy is required")
    required_policy = {
        "acceptance": "explicit_only",
        "raw_responses_stored": False,
        "local_paths_stored": False,
        "checkpoint_id_reuse": "idempotent_same_corpus_only",
        "comparison": "latest_two_accepted",
        "advisory_only": True,
        "factual_authority": False,
        "execution_authorized": False,
    }
    for key, expected in required_policy.items():
        if policy.get(key) != expected:
            raise ValueError(f"Human checkpoint policy mismatch: {key}")

    checkpoints = history.get("checkpoints")
    if not isinstance(checkpoints, list):
        raise ValueError("Human checkpoint history checkpoints must be a list")

    ids: set[str] = set()
    for index, checkpoint in enumerate(checkpoints, start=1):
        if not isinstance(checkpoint, dict):
            raise ValueError("Human checkpoint must be an object")
        checkpoint_id = checkpoint.get("checkpoint_id")
        if not isinstance(checkpoint_id, str) or not checkpoint_id:
            raise ValueError("Human checkpoint_id is required")
        if checkpoint_id in ids:
            raise ValueError("Human checkpoint IDs must be unique")
        ids.add(checkpoint_id)
        if checkpoint.get("sequence") != index:
            raise ValueError("Human checkpoint sequence must be contiguous and ordered")
        fingerprint = checkpoint.get("corpus_sha256")
        if not isinstance(fingerprint, str) or len(fingerprint) != 64:
            raise ValueError("Human checkpoint corpus_sha256 is invalid")
        snapshot = checkpoint.get("snapshot")
        if not isinstance(snapshot, dict):
            raise ValueError("Human checkpoint snapshot is required")
        validate_human_trend_snapshot(snapshot)
        if snapshot.get("snapshot_id") != checkpoint_id:
            raise ValueError("Human checkpoint snapshot identity mismatch")
        if snapshot.get("source") != f"accepted_checkpoint:{checkpoint_id}":
            raise ValueError("Human checkpoint source must not contain a local path")
        quality = checkpoint.get("quality")
        if not isinstance(quality, dict):
            raise ValueError("Human checkpoint quality summary is required")
        if quality.get("ai_judge_used") is not False or quality.get("judge_model_calls") != 0:
            raise ValueError("Human checkpoint quality must remain zero-judge")


def append_human_checkpoint(
    history: dict[str, Any],
    checkpoint: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    validate_human_checkpoint_history(history)
    checkpoint_id = checkpoint.get("checkpoint_id")
    fingerprint = checkpoint.get("corpus_sha256")
    for existing in history["checkpoints"]:
        if existing["checkpoint_id"] != checkpoint_id:
            continue
        if existing["corpus_sha256"] == fingerprint:
            return history, "UNCHANGED"
        raise ValueError("checkpoint_id already exists with different corpus content")

    updated = deepcopy(history)
    accepted = deepcopy(checkpoint)
    accepted["sequence"] = len(updated["checkpoints"]) + 1
    updated["checkpoints"].append(accepted)
    validate_human_checkpoint_history(updated)
    return updated, "APPENDED"


def human_checkpoint_history_summary(history: dict[str, Any]) -> dict[str, Any]:
    validate_human_checkpoint_history(history)
    checkpoints = history["checkpoints"]
    latest = checkpoints[-1] if checkpoints else None
    previous = checkpoints[-2] if len(checkpoints) >= 2 else None
    return {
        "history_version": HUMAN_CHECKPOINT_HISTORY_VERSION,
        "checkpoint_count": len(checkpoints),
        "latest_checkpoint_id": latest["checkpoint_id"] if latest else None,
        "previous_checkpoint_id": previous["checkpoint_id"] if previous else None,
        "comparison_available": len(checkpoints) >= 2,
        "acceptance": "explicit_only",
        "raw_responses_stored": False,
        "local_paths_stored": False,
        "ai_judge_used": False,
        "judge_model_calls": 0,
        "external_calls": 0,
        "zero_judge_tokens": True,
    }


def latest_human_checkpoint_report(history: dict[str, Any]) -> dict[str, Any] | None:
    validate_human_checkpoint_history(history)
    checkpoints = history["checkpoints"]
    if len(checkpoints) < 2:
        return None
    previous = checkpoints[-2]
    current = checkpoints[-1]
    return {
        "human_trend_report_version": "roberta_human_language_trend_report/v1",
        "source_mode": "accepted_checkpoint_history",
        "previous": deepcopy(previous["snapshot"]),
        "current": deepcopy(current["snapshot"]),
        "comparison": compare_human_trend_snapshots(
            previous["snapshot"],
            current["snapshot"],
        ),
        "checkpoint_history": human_checkpoint_history_summary(history),
    }


def accept_human_checkpoint(
    input_path: Path,
    *,
    checkpoint_id: str,
    history_path: Path | None = None,
) -> dict[str, Any]:
    target = history_path or default_human_checkpoint_history_path()
    history = load_human_checkpoint_history(target)
    records = load_run_jsonl(input_path)
    checkpoint = build_human_checkpoint(records, checkpoint_id=checkpoint_id)
    updated, status = append_human_checkpoint(history, checkpoint)
    if status == "APPENDED":
        write_human_checkpoint_history(target, updated)
    return {
        "status": status,
        "checkpoint_id": checkpoint_id,
        "corpus_sha256": checkpoint["corpus_sha256"],
        "history_path": str(target),
        "history": human_checkpoint_history_summary(updated),
        "raw_responses_stored": False,
        "local_paths_stored": False,
        "ai_judge_used": False,
        "judge_model_calls": 0,
        "external_calls": 0,
        "zero_judge_tokens": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="roberta-eval-human-checkpoint")
    parser.add_argument("--input", required=True, help="saved ROBERTA run file/directory")
    parser.add_argument("--checkpoint-id", required=True, help="immutable accepted checkpoint ID")
    parser.add_argument("--history", default=None, help="optional checkpoint-history JSON path")
    parser.add_argument(
        "--accept",
        action="store_true",
        required=True,
        help="explicitly accept and persist this checkpoint",
    )
    args = parser.parse_args(argv)
    result = accept_human_checkpoint(
        Path(args.input),
        checkpoint_id=args.checkpoint_id,
        history_path=Path(args.history) if args.history else None,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
