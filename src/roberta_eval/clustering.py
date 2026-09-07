from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

CLUSTER_VERSION = "roberta_failure_cluster/v1"
SEVERITY_RANK = {"INFO": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}


def _cluster_identity(finding: dict[str, Any], localization: dict[str, Any] | None) -> dict[str, str]:
    return {
        "category": str(finding.get("category") or "EVALUATION_ERROR"),
        "service": str(finding.get("service") or "unknown_service"),
        "likely_layer": str((localization or {}).get("likely_layer") or "unknown"),
        "reason": str(finding.get("reason") or "unknown_reason"),
    }


def _cluster_id(identity: dict[str, str]) -> str:
    payload = json.dumps(identity, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"cluster::{digest}"


def cluster_findings(
    findings: list[dict[str, Any]],
    localizations: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    by_finding_id = {
        str(item.get("finding_id")): item for item in (localizations or [])
    }
    groups: dict[str, list[tuple[dict[str, Any], dict[str, Any] | None]]] = defaultdict(list)

    for finding in findings:
        localization = by_finding_id.get(str(finding.get("finding_id")))
        identity = _cluster_identity(finding, localization)
        groups[_cluster_id(identity)].append((finding, localization))

    clusters: list[dict[str, Any]] = []
    for cluster_id in sorted(groups):
        members = groups[cluster_id]
        finding0, localization0 = members[0]
        identity = _cluster_identity(finding0, localization0)
        severities = [str(f.get("severity") or "MEDIUM") for f, _ in members]
        max_severity = max(severities, key=lambda value: SEVERITY_RANK.get(value, -1))
        member_ids = sorted(str(f.get("finding_id")) for f, _ in members)
        runs = sorted({str(f.get("run_id")) for f, _ in members if f.get("run_id")})
        cases = sorted({str(f.get("case_id")) for f, _ in members if f.get("case_id")})
        clusters.append(
            {
                "cluster_version": CLUSTER_VERSION,
                "cluster_id": cluster_id,
                **identity,
                "severity": max_severity,
                "occurrence_count": len(members),
                "member_finding_ids": member_ids,
                "run_ids": runs,
                "case_ids": cases,
                "evaluation_incomplete": identity["category"] == "EVALUATION_INCOMPLETE",
                "actionable_product_defect": identity["category"] not in {
                    "EVALUATION_INCOMPLETE",
                    "EVALUATION_ERROR",
                },
            }
        )
    return clusters


def cluster_summary(clusters: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "cluster_version": CLUSTER_VERSION,
        "cluster_count": len(clusters),
        "occurrence_count": sum(item["occurrence_count"] for item in clusters),
        "actionable_product_cluster_count": sum(
            1 for item in clusters if item["actionable_product_defect"]
        ),
        "evaluation_cluster_count": sum(
            1 for item in clusters if not item["actionable_product_defect"]
        ),
        "unknown_layer_cluster_count": sum(
            1 for item in clusters if item["likely_layer"] == "unknown"
        ),
    }


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_clusters(path: Path, clusters: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(item, sort_keys=True, separators=(",", ":")) + "\n" for item in clusters),
        encoding="utf-8",
    )
