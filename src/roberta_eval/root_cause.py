from __future__ import annotations

import json
from pathlib import Path
from typing import Any

LOCALIZER_VERSION = "roberta_root_cause_localizer/v1"
VALID_STATES = {"correct", "incorrect", "unknown", "unavailable"}
VALID_LAYERS = {
    "provider",
    "cmis",
    "x1_scout",
    "roberta",
    "laboratory",
    "runtime_transport",
    "unknown",
}


def validate_layer_snapshot(snapshot: dict[str, Any]) -> None:
    for layer in ("provider", "cmis", "x1_scout", "roberta"):
        state = snapshot.get(layer, "unknown")
        if state not in VALID_STATES:
            raise ValueError(f"{layer}: invalid layer snapshot state {state}")


def _result(
    finding: dict[str, Any],
    *,
    layer: str,
    confidence: float,
    basis: str,
    snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "localizer_version": LOCALIZER_VERSION,
        "finding_id": finding.get("finding_id"),
        "category": finding.get("category"),
        "severity": finding.get("severity"),
        "service": finding.get("service"),
        "likely_layer": layer,
        "confidence": confidence,
        "basis": basis,
        "layer_snapshot": snapshot,
    }


def localize_finding(
    finding: dict[str, Any],
    layer_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    category = finding.get("category")
    reason = finding.get("reason")

    if category in {"EVALUATION_INCOMPLETE", "EVALUATION_ERROR"}:
        return _result(
            finding,
            layer="laboratory",
            confidence=1.0,
            basis="evaluation-system finding; not evidence of a ROBERTA product defect",
            snapshot=layer_snapshot,
        )

    if category == "RUNTIME_ERROR":
        return _result(
            finding,
            layer="runtime_transport",
            confidence=0.9,
            basis="runtime/transport failure occurred before a trustworthy answer was graded",
            snapshot=layer_snapshot,
        )

    if (
        category == "EXECUTION_BOUNDARY_VIOLATION"
        and reason in {
            "execution_boundary_violated",
            "execution_boundary_violated_in_conversation",
        }
    ):
        return _result(
            finding,
            layer="roberta",
            confidence=0.95,
            basis="the observed ROBERTA-facing response violated the execution boundary",
            snapshot=layer_snapshot,
        )

    if layer_snapshot is None:
        return _result(
            finding,
            layer="unknown",
            confidence=0.0,
            basis="no layer snapshot available",
            snapshot=None,
        )

    validate_layer_snapshot(layer_snapshot)
    provider = layer_snapshot.get("provider", "unknown")
    cmis = layer_snapshot.get("cmis", "unknown")
    scout = layer_snapshot.get("x1_scout", "unknown")
    roberta = layer_snapshot.get("roberta", "unknown")

    if provider == "incorrect":
        return _result(
            finding,
            layer="provider",
            confidence=1.0,
            basis="provider snapshot is incorrect",
            snapshot=layer_snapshot,
        )

    if provider == "correct" and cmis == "incorrect":
        return _result(
            finding,
            layer="cmis",
            confidence=1.0,
            basis="provider is correct while CMIS snapshot is incorrect",
            snapshot=layer_snapshot,
        )

    if provider == "correct" and cmis == "correct" and scout == "incorrect":
        return _result(
            finding,
            layer="x1_scout",
            confidence=1.0,
            basis="provider and CMIS are correct while X1 Scout is incorrect",
            snapshot=layer_snapshot,
        )

    if (
        provider == "correct"
        and cmis == "correct"
        and scout == "correct"
        and roberta == "incorrect"
    ):
        return _result(
            finding,
            layer="roberta",
            confidence=1.0,
            basis="upstream evidence and Scout are correct while ROBERTA is incorrect",
            snapshot=layer_snapshot,
        )

    return _result(
        finding,
        layer="unknown",
        confidence=0.0,
        basis="layer snapshot is insufficient or inconclusive",
        snapshot=layer_snapshot,
    )


def localize_findings(
    findings: list[dict[str, Any]],
    snapshots: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    snapshots = snapshots or {}
    return [
        localize_finding(finding, snapshots.get(str(finding.get("finding_id"))))
        for finding in findings
    ]


def localization_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {layer: 0 for layer in sorted(VALID_LAYERS)}
    for result in results:
        counts[result["likely_layer"]] += 1
    return {
        "localizer_version": LOCALIZER_VERSION,
        "result_count": len(results),
        "layer_counts": counts,
        "unknown_count": counts["unknown"],
    }


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_localizations(path: Path, results: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(
            json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n"
            for result in results
        ),
        encoding="utf-8",
    )
