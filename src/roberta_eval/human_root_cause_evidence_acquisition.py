from __future__ import annotations

import argparse
import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from copy import deepcopy
from pathlib import Path
from typing import Any, Protocol

from .human_remediation_lineage import (
    CHRONIC_REGRESSION,
    ROOT_CAUSE_WARNING,
    build_generational_lineage_report,
    validate_generational_lineage_report,
)
from .human_remediation_lifecycle import (
    default_lifecycle_path,
    load_lifecycle,
    validate_lifecycle,
)
from .human_remediation_reopen_cycle import (
    default_reopen_cycle_promotion_ledger_path,
    load_reopen_cycle_promotion_ledger,
)
from .human_remediation_root_cause import (
    DOMAINS,
    build_investigation_package,
    validate_investigation_package,
)

EVIDENCE_ACQUISITION_VERSION = "roberta_human_root_cause_evidence_acquisition/v1"
SOURCE_SNAPSHOT_VERSION = "roberta_human_root_cause_source_snapshot/v1"
SOURCE_RECORD_VERSION = "roberta_human_root_cause_source_record/v1"
CORRELATION_VERSION = "roberta_human_root_cause_correlation/v1"
EVIDENCE_BUNDLE_VERSION = "roberta_human_root_cause_evidence_bundle/v1"

INVESTIGATION_REQUIRED_HEALTH = {ROOT_CAUSE_WARNING, CHRONIC_REGRESSION}

ARTIFACT_KINDS = {
    "IMPLEMENTATION_ARTIFACT",
    "TEST_ARTIFACT",
    "CI_CONFIGURATION",
    "DOCUMENTATION",
    "OTHER_ARTIFACT",
}

# Ordered only for stable output. One artifact may map to more than one domain.
DOMAIN_PATH_RULES: dict[str, tuple[str, ...]] = {
    "renderer": (
        "human_response_renderer",
        "human_renderer",
        "tokenized_equity_human_renderer",
        "/renderer",
        "_renderer.py",
    ),
    "policy": (
        "recommendation_policy",
        "opinion_contract",
        "human_response_contract",
        "/policy",
        "_policy.py",
    ),
    "prompt": (
        "/prompt",
        "_prompt",
        "prompt_",
        "system_message",
        "system_prompt",
        "instructions/",
    ),
    "service_adapter": (
        "service_adapter",
        "/adapters/",
        "_adapter.py",
        "bridge_http",
        "service_router",
        "/services/",
    ),
    "vocabulary_replacement": (
        "robertahuman/",
        "technicalvocabulary",
        "engineeringLeak".lower(),
        "plain_language",
        "vocabulary",
        ".vale.ini",
        "/vale",
    ),
    "shared_human_layer": (
        "human_response",
        "human_language",
        "human_remediation",
        "human_quality",
        "continuity",
        "decision_object",
        "shared_human",
    ),
}


def _stable_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _is_sha40(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 40 and all(ch in "0123456789abcdefABCDEF" for ch in value)


def classify_artifact(path: str) -> list[str]:
    normalized = str(path).replace("\\", "/").lower()
    matches: list[str] = []
    for domain in DOMAINS:
        patterns = DOMAIN_PATH_RULES[domain]
        if any(pattern.lower() in normalized for pattern in patterns):
            matches.append(domain)
    return matches


def artifact_kind(path: str) -> str:
    normalized = str(path).replace("\\", "/").lower()
    if normalized.startswith("tests/") or "/tests/" in normalized or normalized.split("/")[-1].startswith("test_"):
        return "TEST_ARTIFACT"
    if normalized.startswith(".github/workflows/") or normalized.endswith(".yml") and ".github/" in normalized:
        return "CI_CONFIGURATION"
    if normalized.startswith("docs/") or normalized.endswith(".md"):
        return "DOCUMENTATION"
    if normalized.endswith((".py", ".toml", ".ini", ".yaml", ".yml", ".json", ".txt")):
        return "IMPLEMENTATION_ARTIFACT"
    return "OTHER_ARTIFACT"


class EvidenceSourceTransport(Protocol):
    def get_pull_request(self, *, repository: str, pr_number: int) -> dict[str, Any]: ...

    def list_pull_request_files(self, *, repository: str, pr_number: int) -> list[dict[str, Any]]: ...

    def list_commit_checks(self, *, repository: str, commit_sha: str) -> list[dict[str, Any]]: ...


class GitHubRestEvidenceSourceTransport:
    """Explicit read-only GitHub source transport used only when acquisition is requested."""

    def __init__(self, token: str = "", *, api_base: str = "https://api.github.com") -> None:
        self._token = token.strip()
        self._api_base = api_base.rstrip("/")

    def _get(self, path: str) -> Any:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "roberta-eval-human-root-cause-evidence",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        request = urllib.request.Request(f"{self._api_base}{path}", headers=headers, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"GitHub evidence read failed: HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"GitHub evidence read failed: {exc.reason}") from exc

    def _paged(self, path: str, *, key: str | None = None) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        page = 1
        while True:
            separator = "&" if "?" in path else "?"
            payload = self._get(f"{path}{separator}per_page=100&page={page}")
            batch = payload.get(key, []) if key else payload
            if not isinstance(batch, list):
                raise RuntimeError("GitHub evidence source returned an invalid paginated payload")
            rows.extend(item for item in batch if isinstance(item, dict))
            if len(batch) < 100:
                break
            page += 1
        return rows

    def get_pull_request(self, *, repository: str, pr_number: int) -> dict[str, Any]:
        owner_repo = urllib.parse.quote(repository, safe="/")
        payload = self._get(f"/repos/{owner_repo}/pulls/{pr_number}")
        if not isinstance(payload, dict):
            raise RuntimeError("GitHub pull request evidence payload is invalid")
        return payload

    def list_pull_request_files(self, *, repository: str, pr_number: int) -> list[dict[str, Any]]:
        owner_repo = urllib.parse.quote(repository, safe="/")
        return self._paged(f"/repos/{owner_repo}/pulls/{pr_number}/files")

    def list_commit_checks(self, *, repository: str, commit_sha: str) -> list[dict[str, Any]]:
        owner_repo = urllib.parse.quote(repository, safe="/")
        return self._paged(
            f"/repos/{owner_repo}/commits/{commit_sha}/check-runs",
            key="check_runs",
        )


def _record_index(lifecycle: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {record["proposal_fingerprint"]: record for record in lifecycle["records"]}


def _normalize_file(row: dict[str, Any], *, generation: int, fingerprint: str) -> dict[str, Any]:
    path = row.get("filename") or row.get("path")
    if not isinstance(path, str) or not path.strip():
        raise ValueError("acquired changed-file evidence requires a path")
    status = str(row.get("status") or "modified")
    sha = row.get("sha")
    additions = int(row.get("additions") or 0)
    deletions = int(row.get("deletions") or 0)
    changes = int(row.get("changes") or additions + deletions)
    domains = classify_artifact(path)
    kind = artifact_kind(path)
    core = {
        "path": path,
        "status": status,
        "blob_sha": sha if isinstance(sha, str) else None,
        "additions": additions,
        "deletions": deletions,
        "changes": changes,
        "artifact_kind": kind,
        "domains": domains,
        "generation": generation,
        "proposal_fingerprint": fingerprint,
    }
    core["artifact_sha256"] = _stable_sha256(core)
    return core


def _normalize_check(row: dict[str, Any], *, generation: int, fingerprint: str, merge_sha: str) -> dict[str, Any]:
    name = row.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("acquired check evidence requires a name")
    core = {
        "name": name.strip(),
        "status": str(row.get("status") or "unknown"),
        "conclusion": row.get("conclusion"),
        "details_url": row.get("details_url") if isinstance(row.get("details_url"), str) else None,
        "generation": generation,
        "proposal_fingerprint": fingerprint,
        "merge_sha": merge_sha,
    }
    core["check_sha256"] = _stable_sha256(core)
    return core


def _normalize_fix_source(
    record: dict[str, Any],
    *,
    generation: int,
    transport: EvidenceSourceTransport | None,
) -> dict[str, Any] | None:
    fix = record.get("fix")
    if fix is None:
        return None
    repository = fix["repository"]
    pr_number = int(fix["pr_number"])
    merge_sha = str(fix["merge_sha"]).lower()
    if not _is_sha40(merge_sha):
        raise ValueError("lifecycle fix merge SHA is invalid for evidence acquisition")

    files: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []
    pr_title: str | None = None
    pr_url: str | None = None
    source_mode = "LIFECYCLE_FIX_ONLY"
    external_calls = 0

    if transport is not None:
        pull = transport.get_pull_request(repository=repository, pr_number=pr_number)
        external_calls += 1
        if int(pull.get("number", -1)) != pr_number:
            raise ValueError("GitHub PR evidence identity does not match lifecycle fix")
        observed_merge = pull.get("merge_commit_sha")
        if not isinstance(observed_merge, str) or observed_merge.lower() != merge_sha:
            raise ValueError("GitHub PR merge SHA conflicts with accepted lifecycle fix evidence")
        if pull.get("merged") is not True and pull.get("merged_at") is None:
            raise ValueError("accepted lifecycle fix PR is not confirmed merged by source transport")
        pr_title = pull.get("title") if isinstance(pull.get("title"), str) else None
        pr_url = pull.get("html_url") if isinstance(pull.get("html_url"), str) else None
        source_files = transport.list_pull_request_files(repository=repository, pr_number=pr_number)
        external_calls += 1
        files = [
            _normalize_file(row, generation=generation, fingerprint=record["proposal_fingerprint"])
            for row in source_files
        ]
        source_checks = transport.list_commit_checks(repository=repository, commit_sha=merge_sha)
        external_calls += 1
        checks = [
            _normalize_check(
                row,
                generation=generation,
                fingerprint=record["proposal_fingerprint"],
                merge_sha=merge_sha,
            )
            for row in source_checks
        ]
        source_mode = "READ_ONLY_GITHUB_PR_AND_CHECKS"

    replay_evidence = []
    for verification in record.get("verifications") or []:
        item = {
            "checkpoint_id": verification["checkpoint_id"],
            "checkpoint_sequence": int(verification["checkpoint_sequence"]),
            "outcome": verification["outcome"],
            "targeted_failure_count": int(verification["targeted_failure_count"]),
            "targeted_failure_rate": float(verification["targeted_failure_rate"]),
            "generation": generation,
        }
        item["verification_sha256"] = _stable_sha256(item)
        replay_evidence.append(item)

    core = {
        "source_record_version": SOURCE_RECORD_VERSION,
        "source_mode": source_mode,
        "generation": generation,
        "proposal_fingerprint": record["proposal_fingerprint"],
        "lifecycle_id": record["lifecycle_id"],
        "failure_code": record["failure_code"],
        "service": record.get("service"),
        "repository": repository,
        "pr_number": pr_number,
        "pr_title": pr_title,
        "pr_url": pr_url,
        "merge_sha": merge_sha,
        "verified_by": fix["verified_by"],
        "files": files,
        "checks": checks,
        "accepted_replays": replay_evidence,
        "external_calls": external_calls,
        "read_only": True,
    }
    core["source_record_id"] = _stable_sha256(core)
    return core


def _dedupe_source_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_identity: dict[tuple[str, int, int], dict[str, Any]] = {}
    for record in records:
        identity = (record["repository"], int(record["pr_number"]), int(record["generation"]))
        existing = by_identity.get(identity)
        if existing is not None:
            if existing["source_record_id"] != record["source_record_id"]:
                raise ValueError("conflicting acquired root-cause source identity")
            continue
        by_identity[identity] = record
    return sorted(by_identity.values(), key=lambda item: (item["generation"], item["repository"], item["pr_number"]))


def build_source_snapshot(
    lineage_report: dict[str, Any],
    lifecycle: dict[str, Any],
    *,
    transport: EvidenceSourceTransport | None = None,
) -> dict[str, Any]:
    validate_generational_lineage_report(lineage_report)
    validate_lifecycle(lifecycle)
    records = _record_index(lifecycle)
    sources: list[dict[str, Any]] = []
    for family in lineage_report["families"]:
        for node in family["nodes"]:
            fp = node["proposal_fingerprint"]
            record = records.get(fp)
            if record is None:
                raise ValueError("lineage node is missing from lifecycle during evidence acquisition")
            source = _normalize_fix_source(
                record,
                generation=int(node["generation"]),
                transport=transport,
            )
            if source is not None:
                sources.append(source)
    sources = _dedupe_source_records(sources)
    core = {
        "source_snapshot_version": SOURCE_SNAPSHOT_VERSION,
        "acquisition_version": EVIDENCE_ACQUISITION_VERSION,
        "lineage_report_sha256": lineage_report["report_sha256"],
        "source_count": len(sources),
        "sources": sources,
        "source_transport_used": transport is not None,
        "external_calls": sum(int(item["external_calls"]) for item in sources),
        "read_only": True,
        "github_issue_mutation": False,
        "production_code_mutation": False,
        "execution_authorized": False,
    }
    core["snapshot_sha256"] = _stable_sha256(core)
    validate_source_snapshot(core)
    return core


def validate_source_snapshot(snapshot: dict[str, Any]) -> None:
    if snapshot.get("source_snapshot_version") != SOURCE_SNAPSHOT_VERSION:
        raise ValueError("unsupported Human root-cause source snapshot version")
    if snapshot.get("acquisition_version") != EVIDENCE_ACQUISITION_VERSION:
        raise ValueError("unsupported Human root-cause evidence acquisition version")
    sources = snapshot.get("sources")
    if not isinstance(sources, list) or int(snapshot.get("source_count", -1)) != len(sources):
        raise ValueError("Human root-cause source snapshot count mismatch")
    identities: set[tuple[str, int, int]] = set()
    for source in sources:
        if source.get("source_record_version") != SOURCE_RECORD_VERSION:
            raise ValueError("Human root-cause source record version mismatch")
        identity = (source.get("repository"), source.get("pr_number"), source.get("generation"))
        if identity in identities:
            raise ValueError("duplicate Human root-cause source identity")
        identities.add(identity)
        if not _is_sha40(source.get("merge_sha")):
            raise ValueError("Human root-cause source merge SHA is invalid")
        if source.get("read_only") is not True:
            raise ValueError("Human root-cause source acquisition must remain read-only")
        for artifact in source.get("files") or []:
            if artifact.get("artifact_kind") not in ARTIFACT_KINDS:
                raise ValueError("Human root-cause acquired artifact kind is invalid")
            if any(domain not in DOMAINS for domain in artifact.get("domains") or []):
                raise ValueError("Human root-cause acquired artifact domain is invalid")
            digest = artifact.get("artifact_sha256")
            if not isinstance(digest, str) or len(digest) != 64:
                raise ValueError("Human root-cause artifact digest is invalid")
    if snapshot.get("read_only") is not True:
        raise ValueError("Human root-cause evidence snapshot must be read-only")
    if snapshot.get("github_issue_mutation") is not False:
        raise ValueError("Human root-cause evidence acquisition cannot mutate GitHub issues")
    if snapshot.get("production_code_mutation") is not False or snapshot.get("execution_authorized") is not False:
        raise ValueError("Human root-cause evidence acquisition exceeds authority boundary")
    expected = {key: value for key, value in snapshot.items() if key != "snapshot_sha256"}
    if snapshot.get("snapshot_sha256") != _stable_sha256(expected):
        raise ValueError("Human root-cause source snapshot digest mismatch")


def _family(lineage_report: dict[str, Any], root_fingerprint: str) -> dict[str, Any]:
    family = next(
        (item for item in lineage_report["families"] if item["root_proposal_fingerprint"] == root_fingerprint),
        None,
    )
    if family is None:
        raise ValueError("Human root-cause acquisition family was not found")
    return family


def _source_for_generation(snapshot: dict[str, Any], family_fingerprints: set[str]) -> list[dict[str, Any]]:
    return [
        source
        for source in snapshot["sources"]
        if source["proposal_fingerprint"] in family_fingerprints
    ]


def _auto_evidence_item(
    *,
    family: dict[str, Any],
    source: dict[str, Any],
    artifact: dict[str, Any],
    domain: str,
) -> dict[str, Any]:
    kind = artifact["artifact_kind"]
    direction = "SUPPORTS" if kind == "IMPLEMENTATION_ARTIFACT" else "NEUTRAL"
    source_ref = (
        f"github:{source['repository']}#pr-{source['pr_number']}:{artifact['path']}@{source['merge_sha']}"
    )
    statement = (
        f"Correlation-only acquisition: {artifact['path']} changed in the accepted generation "
        f"{source['generation']} remediation fix and maps to the {domain} domain. "
        "This is indirect association evidence and does not prove causation."
        if direction == "SUPPORTS"
        else (
            f"Context-only acquisition: {artifact['path']} is a {kind.lower()} associated with the accepted "
            f"generation {source['generation']} remediation. It does not establish a causal domain."
        )
    )
    return {
        "domain": domain,
        "generation": int(source["generation"]),
        "direction": direction,
        "strength": "INDIRECT",
        "source_ref": source_ref,
        "artifact_sha256": artifact["artifact_sha256"],
        "statement": statement,
    }


def _context_record(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    core = {
        "kind": kind,
        **deepcopy(payload),
        "causal_authority": False,
    }
    core["context_id"] = _stable_sha256(core)
    return core


def _dedupe_lab81_evidence(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_identity: dict[tuple[str, int, str], dict[str, Any]] = {}
    for item in items:
        identity = (item["source_ref"], int(item["generation"]), item["domain"])
        existing = by_identity.get(identity)
        if existing is not None:
            if existing != item:
                raise ValueError("conflicting automatic LAB #81 evidence identity")
            continue
        by_identity[identity] = item
    return sorted(
        by_identity.values(),
        key=lambda item: (item["generation"], item["domain"], item["source_ref"]),
    )


def _correlation_findings(
    *,
    sources: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for domain in DOMAINS:
        implementation: list[tuple[int, str]] = []
        tests: list[tuple[int, str]] = []
        accepted_checks = 0
        accepted_replays = 0
        for source in sources:
            domain_present = False
            for artifact in source["files"]:
                if domain not in artifact["domains"]:
                    continue
                domain_present = True
                if artifact["artifact_kind"] == "IMPLEMENTATION_ARTIFACT":
                    implementation.append((int(source["generation"]), artifact["path"]))
                elif artifact["artifact_kind"] == "TEST_ARTIFACT":
                    tests.append((int(source["generation"]), artifact["path"]))
            if domain_present:
                accepted_checks += sum(
                    1
                    for check in source["checks"]
                    if check.get("status") == "completed" and check.get("conclusion") == "success"
                )
                accepted_replays += sum(
                    1
                    for replay in source["accepted_replays"]
                    if replay.get("outcome") in {"IMPROVED", "RESOLVED"}
                )
        generations = sorted({generation for generation, _ in implementation})
        score = (
            len(generations) * 4
            + len(implementation) * 2
            + len(tests)
            + min(accepted_checks, 5)
            + min(accepted_replays, 3)
        )
        if len(generations) >= 2:
            signal = "REPEATED_CROSS_GENERATION_ASSOCIATION"
        elif len(generations) == 1:
            signal = "SINGLE_GENERATION_ASSOCIATION"
        elif tests:
            signal = "TEST_ONLY_ASSOCIATION"
        else:
            signal = "NO_OBSERVED_ASSOCIATION"
        findings.append(
            {
                "domain": domain,
                "signal": signal,
                "score": score,
                "implementation_change_count": len(implementation),
                "implementation_generations": generations,
                "implementation_paths": sorted({path for _, path in implementation}),
                "test_change_count": len(tests),
                "test_generations": sorted({generation for generation, _ in tests}),
                "test_paths": sorted({path for _, path in tests}),
                "accepted_success_check_count": accepted_checks,
                "accepted_improved_or_resolved_replay_count": accepted_replays,
                "causal_authority": False,
            }
        )
    order = {domain: index for index, domain in enumerate(DOMAINS)}
    findings.sort(key=lambda item: (-item["score"], order[item["domain"]]))
    return findings


def build_evidence_bundle(
    lineage_report: dict[str, Any],
    source_snapshot: dict[str, Any],
    *,
    root_fingerprint: str,
) -> dict[str, Any]:
    validate_generational_lineage_report(lineage_report)
    validate_source_snapshot(source_snapshot)
    if source_snapshot["lineage_report_sha256"] != lineage_report["report_sha256"]:
        raise ValueError("source snapshot does not match the supplied lineage report")
    family = _family(lineage_report, root_fingerprint)
    family_fingerprints = {node["proposal_fingerprint"] for node in family["nodes"]}
    sources = _source_for_generation(source_snapshot, family_fingerprints)

    evidence: list[dict[str, Any]] = []
    context: list[dict[str, Any]] = []
    for source in sources:
        context.append(
            _context_record(
                "FIX_HISTORY",
                {
                    "generation": source["generation"],
                    "proposal_fingerprint": source["proposal_fingerprint"],
                    "repository": source["repository"],
                    "pr_number": source["pr_number"],
                    "merge_sha": source["merge_sha"],
                    "source_record_id": source["source_record_id"],
                },
            )
        )
        for artifact in source["files"]:
            if not artifact["domains"]:
                continue
            for domain in artifact["domains"]:
                evidence.append(
                    _auto_evidence_item(
                        family=family,
                        source=source,
                        artifact=artifact,
                        domain=domain,
                    )
                )
        for check in source["checks"]:
            context.append(
                _context_record(
                    "ACCEPTED_CHECK",
                    {
                        "generation": source["generation"],
                        "proposal_fingerprint": source["proposal_fingerprint"],
                        "repository": source["repository"],
                        "merge_sha": source["merge_sha"],
                        "name": check["name"],
                        "status": check["status"],
                        "conclusion": check["conclusion"],
                        "check_sha256": check["check_sha256"],
                    },
                )
            )
        for replay in source["accepted_replays"]:
            context.append(
                _context_record(
                    "ACCEPTED_REPLAY",
                    {
                        "generation": source["generation"],
                        "proposal_fingerprint": source["proposal_fingerprint"],
                        **replay,
                    },
                )
            )

    evidence = _dedupe_lab81_evidence(evidence)
    context.sort(key=lambda item: item["context_id"])
    context_ids = [item["context_id"] for item in context]
    if len(context_ids) != len(set(context_ids)):
        raise ValueError("duplicate root-cause acquisition context identity")

    correlation_findings = _correlation_findings(sources=sources)
    correlation_core = {
        "correlation_version": CORRELATION_VERSION,
        "family_root_fingerprint": family["root_proposal_fingerprint"],
        "family_health": family["health"],
        "deepest_generation": int(family["deepest_generation"]),
        "findings": correlation_findings,
        "causal_authority": False,
        "correlation_is_not_causation": True,
        "root_cause_confirmation_authority": "LAB_81_ONLY",
    }
    correlation_core["correlation_sha256"] = _stable_sha256(correlation_core)

    core = {
        "evidence_bundle_version": EVIDENCE_BUNDLE_VERSION,
        "acquisition_version": EVIDENCE_ACQUISITION_VERSION,
        "source_snapshot_sha256": source_snapshot["snapshot_sha256"],
        "lineage_report_sha256": lineage_report["report_sha256"],
        "family_root_fingerprint": family["root_proposal_fingerprint"],
        "failure_code": family["failure_code"],
        "service": family.get("service"),
        "health": family["health"],
        "deepest_generation": int(family["deepest_generation"]),
        "investigation_required": family["health"] in INVESTIGATION_REQUIRED_HEALTH,
        "source_record_ids": [item["source_record_id"] for item in sources],
        "lab81_evidence": evidence,
        "context_records": context,
        "correlation": correlation_core,
        "automatic_evidence_strength": "INDIRECT_ONLY",
        "automatic_direct_evidence_count": 0,
        "causal_authority": False,
        "correlation_is_not_causation": True,
        "lab81_confirmation_threshold_preserved": True,
        "read_only": True,
        "github_issue_mutation": False,
        "production_code_mutation": False,
        "execution_authorized": False,
    }
    core["bundle_sha256"] = _stable_sha256(core)
    validate_evidence_bundle(core)
    return core


def validate_evidence_bundle(bundle: dict[str, Any]) -> None:
    if bundle.get("evidence_bundle_version") != EVIDENCE_BUNDLE_VERSION:
        raise ValueError("unsupported Human root-cause evidence bundle version")
    if bundle.get("acquisition_version") != EVIDENCE_ACQUISITION_VERSION:
        raise ValueError("unsupported Human root-cause evidence acquisition version")
    evidence = bundle.get("lab81_evidence")
    if not isinstance(evidence, list):
        raise ValueError("Human root-cause LAB #81 evidence must be a list")
    for item in evidence:
        if item.get("strength") != "INDIRECT":
            raise ValueError("automatic evidence acquisition cannot emit DIRECT causal evidence")
        if item.get("domain") not in DOMAINS:
            raise ValueError("automatic root-cause evidence domain is invalid")
        if item.get("direction") not in {"SUPPORTS", "NEUTRAL"}:
            raise ValueError("automatic correlation acquisition cannot invent contradiction evidence")
    if int(bundle.get("automatic_direct_evidence_count", -1)) != 0:
        raise ValueError("automatic evidence acquisition direct evidence count must remain zero")
    correlation = bundle.get("correlation")
    if not isinstance(correlation, dict) or correlation.get("correlation_version") != CORRELATION_VERSION:
        raise ValueError("Human root-cause correlation report is invalid")
    if correlation.get("causal_authority") is not False or correlation.get("correlation_is_not_causation") is not True:
        raise ValueError("Human root-cause correlation cannot claim causal authority")
    if bundle.get("causal_authority") is not False:
        raise ValueError("Human root-cause acquisition cannot claim causal authority")
    if bundle.get("lab81_confirmation_threshold_preserved") is not True:
        raise ValueError("LAB #81 confirmation threshold must remain preserved")
    if bundle.get("read_only") is not True or bundle.get("github_issue_mutation") is not False:
        raise ValueError("Human root-cause acquisition must remain read-only")
    if bundle.get("production_code_mutation") is not False or bundle.get("execution_authorized") is not False:
        raise ValueError("Human root-cause acquisition exceeds authority boundary")
    expected = {key: value for key, value in bundle.items() if key != "bundle_sha256"}
    if bundle.get("bundle_sha256") != _stable_sha256(expected):
        raise ValueError("Human root-cause evidence bundle digest mismatch")


def build_lab81_package_from_bundle(
    lineage_report: dict[str, Any],
    bundle: dict[str, Any],
) -> dict[str, Any]:
    validate_generational_lineage_report(lineage_report)
    validate_evidence_bundle(bundle)
    if bundle["lineage_report_sha256"] != lineage_report["report_sha256"]:
        raise ValueError("evidence bundle lineage identity mismatch")
    package = build_investigation_package(
        lineage_report,
        root_fingerprint=bundle["family_root_fingerprint"],
        evidence=bundle["lab81_evidence"],
    )
    validate_investigation_package(package)
    if package["confirmed_root_causes"]:
        raise ValueError(
            "automatic correlation evidence unexpectedly crossed LAB #81 causal confirmation threshold"
        )
    return package


def acquisition_summary(bundle: dict[str, Any]) -> dict[str, Any]:
    validate_evidence_bundle(bundle)
    top = bundle["correlation"]["findings"][0] if bundle["correlation"]["findings"] else None
    return {
        "evidence_bundle_version": EVIDENCE_BUNDLE_VERSION,
        "family_root_fingerprint": bundle["family_root_fingerprint"],
        "health": bundle["health"],
        "source_count": len(bundle["source_record_ids"]),
        "lab81_evidence_count": len(bundle["lab81_evidence"]),
        "context_record_count": len(bundle["context_records"]),
        "top_correlated_domain": top["domain"] if top and top["score"] > 0 else None,
        "top_correlation_score": top["score"] if top else 0,
        "causal_authority": False,
        "automatic_direct_evidence_count": 0,
        "lab81_confirmation_threshold_preserved": True,
    }


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JSON input must be an object")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="roberta-eval-human-root-cause-acquire")
    parser.add_argument("command", choices=("snapshot", "bundle", "correlate", "lab81-package"))
    parser.add_argument("--root-fingerprint", default=None)
    parser.add_argument("--lifecycle", default=None)
    parser.add_argument("--reopen-cycle-ledger", default=None)
    parser.add_argument("--source-snapshot", default=None)
    parser.add_argument("--github", action="store_true", help="explicitly read PR/file/check evidence from GitHub")
    parser.add_argument("--github-token-env", default="GITHUB_TOKEN")
    parser.add_argument("--output", default=None)
    args = parser.parse_args(argv)

    lifecycle = load_lifecycle(Path(args.lifecycle) if args.lifecycle else default_lifecycle_path())
    reopen = load_reopen_cycle_promotion_ledger(
        Path(args.reopen_cycle_ledger)
        if args.reopen_cycle_ledger
        else default_reopen_cycle_promotion_ledger_path()
    )
    lineage = build_generational_lineage_report(lifecycle, reopen)

    if args.source_snapshot:
        snapshot = _load_json(Path(args.source_snapshot))
        validate_source_snapshot(snapshot)
    else:
        transport: EvidenceSourceTransport | None = None
        if args.github:
            transport = GitHubRestEvidenceSourceTransport(os.environ.get(args.github_token_env, ""))
        snapshot = build_source_snapshot(lineage, lifecycle, transport=transport)

    if args.command == "snapshot":
        result: Any = snapshot
    else:
        if not args.root_fingerprint:
            raise ValueError("--root-fingerprint is required for bundle/correlate/lab81-package")
        bundle = build_evidence_bundle(lineage, snapshot, root_fingerprint=args.root_fingerprint)
        if args.command == "bundle":
            result = bundle
        elif args.command == "correlate":
            result = bundle["correlation"]
        else:
            result = build_lab81_package_from_bundle(lineage, bundle)

    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
