from __future__ import annotations

import argparse
import ast
import difflib
import hashlib
import json
from copy import deepcopy
from pathlib import Path, PurePosixPath
from typing import Any

from .human_remediation_root_cause import DOMAINS
from .human_root_cause_artifact_sandbox import (
    MaterializedHumanSandboxAdapter,
    lab87_corpus_cases,
    load_source_pin,
    materialize_candidate_artifact,
    materialize_control_artifact,
    validate_artifact_manifest,
    validate_materialization,
    validate_source_pin,
)
from .human_root_cause_direct_evidence import (
    qualify_experiment_result,
    validate_experiment_plan,
    validate_experiment_qualification,
    validate_experiment_result,
)
from .human_root_cause_experiment_execution import (
    build_execution_manifest,
    corpus_sha256,
    execute_controlled_experiment,
    receipt_to_lab85_result_input,
    validate_execution_manifest,
    validate_execution_receipt,
)

PATCH_VERSION = "roberta_human_root_cause_candidate_patch/v1"
STATIC_SAFETY_VERSION = "roberta_human_root_cause_patch_static_safety/v1"
PATCH_QUALIFICATION_VERSION = "roberta_human_root_cause_patch_qualification/v1"
PROMOTION_PACKAGE_VERSION = "roberta_human_root_cause_patch_promotion_package/v1"
PATCH_LEDGER_VERSION = "roberta_human_root_cause_patch_qualification_ledger/v1"

TARGET_REPOSITORY = "bhaygood29053-pixel/roberta-langgraph"

_FORBIDDEN_NEW_IMPORT_ROOTS = frozenset(
    {
        "aiohttp",
        "anthropic",
        "boto3",
        "github",
        "httpx",
        "langchain",
        "openai",
        "requests",
        "socket",
        "subprocess",
        "urllib3",
        "websockets",
    }
)

_FORBIDDEN_CALL_PREFIXES = (
    "socket.",
    "requests.",
    "httpx.",
    "aiohttp.",
    "urllib.",
    "urllib3.",
    "subprocess.",
    "os.system",
    "os.popen",
    "os.getenv",
    "os.putenv",
    "os.unsetenv",
    "shutil.",
    "importlib.",
    "pathlib.Path.write_",
    "pathlib.Path.unlink",
    "pathlib.Path.rename",
    "pathlib.Path.replace",
    "pathlib.Path.mkdir",
    "Path.write_",
    "Path.unlink",
    "Path.rename",
    "Path.replace",
    "Path.mkdir",
)

_FORBIDDEN_CALL_NAMES = frozenset(
    {
        "__import__",
        "compile",
        "eval",
        "exec",
    }
)

_FORBIDDEN_TEXT_TOKENS = (
    "roberta_core",
    "private_core",
    "execution_authorized=true",
    '"execution_authorized":true',
    "'execution_authorized':true",
    "production_code_mutation=true",
    '"production_code_mutation":true',
    "'production_code_mutation':true",
    "runner_outcome_authority=true",
    '"runner_outcome_authority":true',
    "'runner_outcome_authority':true",
    "api.github.com",
    "github.com/repos/",
)

_AUTHORITY_BOOLEAN_NAMES = frozenset(
    {
        "execution_authorized",
        "production_code_mutation",
        "runner_outcome_authority",
        "production_runtime_touched",
        "github_issue_mutation",
        "production_pr_created",
        "production_pr_merge_authorized",
    }
)


def _stable_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _bytes_sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(ch in "0123456789abcdefABCDEF" for ch in value)


def _is_sha1(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 40 and all(ch in "0123456789abcdefABCDEF" for ch in value)


def default_patch_ledger_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "human_root_cause_patch_qualification_ledger.json"


def empty_patch_ledger() -> dict[str, Any]:
    return {
        "ledger_version": PATCH_LEDGER_VERSION,
        "policy": {
            "accepted_control_source_required": True,
            "target_domain_only": True,
            "static_safety_required": True,
            "lab89_runtime_isolation_authority": True,
            "lab87_reproducibility_authority": True,
            "lab85_direct_evidence_authority": True,
            "support_required_for_pr_eligibility": True,
            "one_pr_eligible_patch_per_plan": True,
            "replacement_bodies_stored": False,
            "production_pr_created": False,
            "production_pr_merge_authorized": False,
            "production_code_mutation": False,
            "execution_authorized": False,
        },
        "qualifications": [],
    }


def load_patch_ledger(path: Path | None = None) -> dict[str, Any]:
    source = path or default_patch_ledger_path()
    payload = json.loads(source.read_text(encoding="utf-8"))
    validate_patch_ledger(payload)
    return payload


def write_patch_ledger(path: Path, ledger: dict[str, Any]) -> None:
    validate_patch_ledger(ledger)
    path.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _safe_repo_path(path: str) -> str:
    if not isinstance(path, str) or not path.strip():
        raise ValueError("candidate patch path is required")
    value = PurePosixPath(path)
    if value.is_absolute() or ".." in value.parts or "." in value.parts:
        raise ValueError("candidate patch path traversal is not allowed")
    normalized = value.as_posix()
    if normalized != path or normalized.startswith("/"):
        raise ValueError("candidate patch path is not canonical")
    return normalized


def _decode_text(path: Path) -> str:
    raw = path.read_bytes()
    if b"\x00" in raw:
        raise ValueError("candidate patch cannot target binary content")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("candidate patch control file is not UTF-8 text") from exc


def _unified_diff(path: str, old: str, new: str) -> str:
    return "".join(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            lineterm="\n",
        )
    )


def _validate_patch_file_shape(item: dict[str, Any]) -> None:
    if not isinstance(item, dict):
        raise ValueError("candidate patch file entry must be an object")
    _safe_repo_path(item.get("path"))
    if not _is_sha256(item.get("control_sha256")) or not _is_sha256(item.get("replacement_sha256")):
        raise ValueError("candidate patch file digest is invalid")
    if item["control_sha256"].lower() == item["replacement_sha256"].lower():
        raise ValueError("candidate patch file must actually change")
    if not isinstance(item.get("replacement_utf8"), str):
        raise ValueError("candidate patch replacement must be UTF-8 text")
    if "\x00" in item["replacement_utf8"]:
        raise ValueError("candidate patch replacement contains binary NUL data")
    if not isinstance(item.get("review_diff"), str) or not item["review_diff"]:
        raise ValueError("candidate patch review diff is required")
    if item.get("operation") != "MODIFY":
        raise ValueError("candidate patch only supports MODIFY operations")


def construct_candidate_patch(
    pin: dict[str, Any],
    plan: dict[str, Any],
    control_manifest: dict[str, Any],
    *,
    control_root: Path,
    replacements: dict[str, str],
    constructed_by: str,
    rationale: str,
) -> dict[str, Any]:
    validate_source_pin(pin)
    validate_experiment_plan(plan)
    validate_artifact_manifest(control_manifest, pin=pin)
    if control_manifest.get("arm") != "CONTROL":
        raise ValueError("candidate patch requires a CONTROL materialization")
    if pin["repository"] != TARGET_REPOSITORY:
        raise ValueError("candidate patch target repository is not accepted")
    if not _is_sha1(pin.get("commit_sha")):
        raise ValueError("candidate patch requires an explicit control commit")
    if not isinstance(replacements, dict) or not replacements:
        raise ValueError("candidate patch must contain at least one replacement")
    constructed_by = constructed_by.strip()
    rationale = rationale.strip()
    if not constructed_by or not rationale:
        raise ValueError("candidate patch constructor and rationale are required")

    specs = {item["path"]: item for item in pin["files"]}
    control_files = {item["path"]: item for item in control_manifest["files"]}
    target_domain = plan["target_domain"]
    rows: list[dict[str, Any]] = []
    for raw_path, replacement in sorted(replacements.items()):
        path = _safe_repo_path(raw_path)
        if path not in specs or path not in control_files:
            raise ValueError("candidate patch path is outside the accepted LAB #89 source pin")
        if specs[path]["owner_domain"] != target_domain:
            raise ValueError("candidate patch attempted to modify a non-target Human domain")
        if not isinstance(replacement, str) or "\x00" in replacement:
            raise ValueError("candidate patch replacement must be UTF-8 text")
        file_path = Path(control_root) / PurePosixPath(path)
        if not file_path.is_file() or file_path.is_symlink():
            raise ValueError("candidate patch control path is missing or symlinked")
        old = _decode_text(file_path)
        old_sha = _bytes_sha256(old.encode("utf-8"))
        if old_sha != control_files[path]["sha256"]:
            raise ValueError("candidate patch control file does not match accepted materialization")
        new_sha = _bytes_sha256(replacement.encode("utf-8"))
        if new_sha == old_sha:
            raise ValueError("candidate patch replacement does not change the file")
        rows.append(
            {
                "path": path,
                "owner_domain": target_domain,
                "operation": "MODIFY",
                "control_sha256": old_sha,
                "replacement_sha256": new_sha,
                "replacement_utf8": replacement,
                "review_diff": _unified_diff(path, old, replacement),
            }
        )

    core = {
        "candidate_patch_version": PATCH_VERSION,
        "target_repository": pin["repository"],
        "base_commit_sha": pin["commit_sha"],
        "source_pin_sha256": pin["source_pin_sha256"],
        "experiment_plan_id": plan["plan_id"],
        "family_root_fingerprint": plan["family_root_fingerprint"],
        "target_domain": target_domain,
        "files": rows,
        "changed_paths": [row["path"] for row in rows],
        "constructed_by": constructed_by,
        "rationale": rationale,
        "reviewable": True,
        "file_additions": 0,
        "file_deletions": 0,
        "file_renames": 0,
        "target_domain_only": True,
        "production_pr_created": False,
        "production_pr_merge_authorized": False,
        "production_code_mutation": False,
        "execution_authorized": False,
    }
    core["patch_id"] = _stable_sha256(core)
    validate_candidate_patch(core, pin=pin, plan=plan, control_manifest=control_manifest, control_root=control_root)
    return core


def validate_candidate_patch(
    patch: dict[str, Any],
    *,
    pin: dict[str, Any],
    plan: dict[str, Any],
    control_manifest: dict[str, Any],
    control_root: Path,
) -> None:
    validate_source_pin(pin)
    validate_experiment_plan(plan)
    validate_artifact_manifest(control_manifest, pin=pin)
    if patch.get("candidate_patch_version") != PATCH_VERSION:
        raise ValueError("unsupported candidate patch version")
    if patch.get("target_repository") != pin["repository"] or patch.get("base_commit_sha") != pin["commit_sha"]:
        raise ValueError("candidate patch source identity mismatch")
    if patch.get("source_pin_sha256") != pin["source_pin_sha256"]:
        raise ValueError("candidate patch source-pin identity mismatch")
    if patch.get("experiment_plan_id") != plan["plan_id"] or patch.get("family_root_fingerprint") != plan["family_root_fingerprint"]:
        raise ValueError("candidate patch experiment identity mismatch")
    if patch.get("target_domain") != plan["target_domain"]:
        raise ValueError("candidate patch target-domain mismatch")
    files = patch.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("candidate patch files are required")
    specs = {item["path"]: item for item in pin["files"]}
    control_files = {item["path"]: item for item in control_manifest["files"]}
    seen: set[str] = set()
    for item in files:
        _validate_patch_file_shape(item)
        path = item["path"]
        if path in seen:
            raise ValueError("candidate patch contains duplicate path")
        if path not in specs or specs[path]["owner_domain"] != plan["target_domain"]:
            raise ValueError("candidate patch records non-target or unaccepted path")
        if item.get("owner_domain") != plan["target_domain"]:
            raise ValueError("candidate patch file owner-domain mismatch")
        if item["control_sha256"] != control_files[path]["sha256"]:
            raise ValueError("candidate patch control digest is stale")
        file_path = Path(control_root) / PurePosixPath(path)
        if not file_path.is_file() or file_path.is_symlink():
            raise ValueError("candidate patch control path is missing or symlinked")
        old = _decode_text(file_path)
        if _bytes_sha256(old.encode("utf-8")) != item["control_sha256"]:
            raise ValueError("candidate patch control bytes differ from accepted materialization")
        if _bytes_sha256(item["replacement_utf8"].encode("utf-8")) != item["replacement_sha256"]:
            raise ValueError("candidate patch replacement digest mismatch")
        if _unified_diff(path, old, item["replacement_utf8"]) != item["review_diff"]:
            raise ValueError("candidate patch review diff does not match file bodies")
        seen.add(path)
    if patch.get("changed_paths") != sorted(seen):
        raise ValueError("candidate patch changed-path summary mismatch")
    for key, expected in {
        "reviewable": True,
        "file_additions": 0,
        "file_deletions": 0,
        "file_renames": 0,
        "target_domain_only": True,
        "production_pr_created": False,
        "production_pr_merge_authorized": False,
        "production_code_mutation": False,
        "execution_authorized": False,
    }.items():
        if patch.get(key) != expected:
            raise ValueError(f"candidate patch policy mismatch: {key}")
    expected = {key: value for key, value in patch.items() if key != "patch_id"}
    if patch.get("patch_id") != _stable_sha256(expected):
        raise ValueError("candidate patch digest mismatch")


def _imports(tree: ast.AST) -> set[str]:
    values: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                values.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            prefix = "." * node.level
            values.add(prefix + (node.module or ""))
    return values


def _qualified_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        left = _qualified_name(node.value)
        return f"{left}.{node.attr}" if left else node.attr
    return None


def _literal_true(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value is True


def _open_write_mode(node: ast.Call) -> bool:
    name = _qualified_name(node.func)
    if name not in {"open", "Path.open", "pathlib.Path.open"}:
        return False
    mode: str | None = None
    if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str):
        mode = node.args[1].value
    for kw in node.keywords:
        if kw.arg == "mode" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            mode = kw.value.value
    return isinstance(mode, str) and any(ch in mode for ch in "wax+")


def _danger_features(text: str, *, path: str) -> set[str]:
    features: set[str] = set()
    lower = text.lower().replace(" ", "")
    for token in _FORBIDDEN_TEXT_TOKENS:
        if token in lower:
            features.add(f"text:{token}")
    if not path.endswith(".py"):
        return features
    try:
        tree = ast.parse(text, filename=path)
    except SyntaxError as exc:
        raise ValueError(f"candidate patch replacement is not valid Python: {path}") from exc
    for imported in _imports(tree):
        root = imported.lstrip(".").split(".", 1)[0]
        if root in _FORBIDDEN_NEW_IMPORT_ROOTS:
            features.add(f"forbidden_import:{imported}")
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _qualified_name(node.func)
            if name in _FORBIDDEN_CALL_NAMES:
                features.add(f"call:{name}")
            if name and any(name.startswith(prefix) for prefix in _FORBIDDEN_CALL_PREFIXES):
                features.add(f"call:{name}")
            if _open_write_mode(node):
                features.add("call:open_write_mode")
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
            targets: list[ast.AST] = []
            value: ast.AST | None = None
            if isinstance(node, ast.Assign):
                targets = list(node.targets)
                value = node.value
            elif isinstance(node, ast.AnnAssign):
                targets = [node.target]
                value = node.value
            else:
                targets = [node.target]
                value = node.value
            if value is not None and _literal_true(value):
                for target in targets:
                    name = _qualified_name(target)
                    if name and name.split(".")[-1] in _AUTHORITY_BOOLEAN_NAMES:
                        features.add(f"authority_true:{name}")
    return features


def _static_file_safety(path: str, old: str, new: str) -> dict[str, Any]:
    old_features = _danger_features(old, path=path)
    new_features = _danger_features(new, path=path)
    introduced_features = sorted(new_features - old_features)

    old_imports: set[str] = set()
    new_imports: set[str] = set()
    if path.endswith(".py"):
        try:
            old_tree = ast.parse(old, filename=path)
            new_tree = ast.parse(new, filename=path)
        except SyntaxError as exc:
            raise ValueError(f"candidate patch Python parse failed: {path}") from exc
        old_imports = _imports(old_tree)
        new_imports = _imports(new_tree)
    introduced_imports = sorted(new_imports - old_imports)

    blockers: list[str] = []
    if introduced_imports:
        blockers.append("NEW_IMPORT_OR_DEPENDENCY")
    if introduced_features:
        blockers.append("NEW_FORBIDDEN_CAPABILITY")
    return {
        "path": path,
        "control_imports": sorted(old_imports),
        "candidate_imports": sorted(new_imports),
        "introduced_imports": introduced_imports,
        "introduced_forbidden_features": introduced_features,
        "status": "PASS" if not blockers else "BLOCKED",
        "blockers": blockers,
    }


def qualify_patch_static_safety(
    patch: dict[str, Any],
    *,
    pin: dict[str, Any],
    plan: dict[str, Any],
    control_manifest: dict[str, Any],
    control_root: Path,
) -> dict[str, Any]:
    validate_candidate_patch(
        patch,
        pin=pin,
        plan=plan,
        control_manifest=control_manifest,
        control_root=control_root,
    )
    rows: list[dict[str, Any]] = []
    for item in patch["files"]:
        path = item["path"]
        old = _decode_text(Path(control_root) / PurePosixPath(path))
        rows.append(_static_file_safety(path, old, item["replacement_utf8"]))
    blockers = sorted({blocker for row in rows for blocker in row["blockers"]})
    core = {
        "patch_static_safety_version": STATIC_SAFETY_VERSION,
        "patch_id": patch["patch_id"],
        "experiment_plan_id": plan["plan_id"],
        "target_domain": plan["target_domain"],
        "file_results": rows,
        "blockers": blockers,
        "status": "PASS" if not blockers else "BLOCKED",
        "new_dependencies_allowed": False,
        "new_network_capabilities_allowed": False,
        "authority_escalation_allowed": False,
        "static_analysis_is_runtime_proof": False,
        "lab89_runtime_isolation_required": True,
        "production_code_mutation": False,
        "execution_authorized": False,
    }
    core["static_safety_id"] = _stable_sha256(core)
    validate_patch_static_safety(core, patch=patch)
    return core


def validate_patch_static_safety(safety: dict[str, Any], *, patch: dict[str, Any]) -> None:
    if safety.get("patch_static_safety_version") != STATIC_SAFETY_VERSION:
        raise ValueError("unsupported candidate patch static-safety version")
    if safety.get("patch_id") != patch.get("patch_id"):
        raise ValueError("candidate patch static-safety identity mismatch")
    rows = safety.get("file_results")
    if not isinstance(rows, list) or len(rows) != len(patch.get("files", [])):
        raise ValueError("candidate patch static-safety file results are invalid")
    blockers = sorted({blocker for row in rows for blocker in row.get("blockers", [])})
    if safety.get("blockers") != blockers:
        raise ValueError("candidate patch static-safety blockers mismatch")
    expected_status = "PASS" if not blockers else "BLOCKED"
    if safety.get("status") != expected_status:
        raise ValueError("candidate patch static-safety status mismatch")
    for key, expected in {
        "new_dependencies_allowed": False,
        "new_network_capabilities_allowed": False,
        "authority_escalation_allowed": False,
        "static_analysis_is_runtime_proof": False,
        "lab89_runtime_isolation_required": True,
        "production_code_mutation": False,
        "execution_authorized": False,
    }.items():
        if safety.get(key) != expected:
            raise ValueError(f"candidate patch static-safety policy mismatch: {key}")
    expected = {key: value for key, value in safety.items() if key != "static_safety_id"}
    if safety.get("static_safety_id") != _stable_sha256(expected):
        raise ValueError("candidate patch static-safety digest mismatch")


def patch_to_lab89_overlay(patch: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "path": item["path"],
            "expected_control_sha256": item["control_sha256"],
            "content_utf8": item["replacement_utf8"],
        }
        for item in patch["files"]
    ]


def _promotion_package(
    *,
    patch: dict[str, Any],
    safety: dict[str, Any],
    pin: dict[str, Any],
    plan: dict[str, Any],
    materialization: dict[str, Any],
    lab87_manifest: dict[str, Any],
    lab87_receipt: dict[str, Any],
    lab85_result: dict[str, Any],
    lab85_qualification: dict[str, Any],
    qualified_by: str,
) -> dict[str, Any]:
    if safety["status"] != "PASS":
        raise ValueError("blocked candidate patch cannot be made PR-eligible")
    if lab85_result["outcome"] != "SUPPORTS_HYPOTHESIS":
        raise ValueError("candidate patch requires LAB #85 SUPPORTS_HYPOTHESIS")
    if (
        lab85_qualification["admissible_direct_evidence"] is not True
        or lab85_qualification["direct_evidence_direction"] != "SUPPORTS"
        or lab85_qualification["direct_evidence_strength"] != "DIRECT"
    ):
        raise ValueError("candidate patch requires LAB #85 DIRECT SUPPORTS")
    core = {
        "patch_promotion_package_version": PROMOTION_PACKAGE_VERSION,
        "patch_id": patch["patch_id"],
        "static_safety_id": safety["static_safety_id"],
        "target_repository": pin["repository"],
        "base_commit_sha": pin["commit_sha"],
        "source_pin_sha256": pin["source_pin_sha256"],
        "experiment_plan_id": plan["plan_id"],
        "target_domain": plan["target_domain"],
        "changed_paths": list(patch["changed_paths"]),
        "materialization_id": materialization["materialization_id"],
        "lab87_manifest_id": lab87_manifest["manifest_id"],
        "lab87_receipt_id": lab87_receipt["receipt_id"],
        "lab85_result_id": lab85_result["result_id"],
        "lab85_qualification_id": lab85_qualification["qualification_id"],
        "lab85_outcome": lab85_result["outcome"],
        "direct_evidence_direction": lab85_qualification["direct_evidence_direction"],
        "qualified_by": qualified_by.strip(),
        "review_summary": {
            "rationale": patch["rationale"],
            "files": [
                {
                    "path": item["path"],
                    "control_sha256": item["control_sha256"],
                    "replacement_sha256": item["replacement_sha256"],
                }
                for item in patch["files"]
            ],
        },
        "pr_eligible": True,
        "owner_review_still_required": True,
        "production_pr_created": False,
        "production_pr_creation_authorized": False,
        "production_pr_merge_authorized": False,
        "production_code_mutation": False,
        "execution_authorized": False,
    }
    if not core["qualified_by"]:
        raise ValueError("candidate patch qualification reviewer is required")
    core["promotion_package_id"] = _stable_sha256(core)
    validate_promotion_package(
        core,
        patch=patch,
        safety=safety,
        pin=pin,
        plan=plan,
        materialization=materialization,
        lab87_manifest=lab87_manifest,
        lab87_receipt=lab87_receipt,
        lab85_result=lab85_result,
        lab85_qualification=lab85_qualification,
    )
    return core


def validate_promotion_package(
    package: dict[str, Any],
    *,
    patch: dict[str, Any],
    safety: dict[str, Any],
    pin: dict[str, Any],
    plan: dict[str, Any],
    materialization: dict[str, Any],
    lab87_manifest: dict[str, Any],
    lab87_receipt: dict[str, Any],
    lab85_result: dict[str, Any],
    lab85_qualification: dict[str, Any],
) -> None:
    if package.get("patch_promotion_package_version") != PROMOTION_PACKAGE_VERSION:
        raise ValueError("unsupported candidate patch promotion-package version")
    expected_ids = {
        "patch_id": patch["patch_id"],
        "static_safety_id": safety["static_safety_id"],
        "source_pin_sha256": pin["source_pin_sha256"],
        "experiment_plan_id": plan["plan_id"],
        "materialization_id": materialization["materialization_id"],
        "lab87_manifest_id": lab87_manifest["manifest_id"],
        "lab87_receipt_id": lab87_receipt["receipt_id"],
        "lab85_result_id": lab85_result["result_id"],
        "lab85_qualification_id": lab85_qualification["qualification_id"],
    }
    for key, value in expected_ids.items():
        if package.get(key) != value:
            raise ValueError(f"candidate patch promotion-package evidence mismatch: {key}")
    if package.get("target_repository") != pin["repository"] or package.get("base_commit_sha") != pin["commit_sha"]:
        raise ValueError("candidate patch promotion-package target identity mismatch")
    if package.get("changed_paths") != patch["changed_paths"]:
        raise ValueError("candidate patch promotion-package changed paths mismatch")
    if package.get("lab85_outcome") != "SUPPORTS_HYPOTHESIS" or package.get("direct_evidence_direction") != "SUPPORTS":
        raise ValueError("candidate patch promotion package lacks supporting controlled evidence")
    for key, expected in {
        "pr_eligible": True,
        "owner_review_still_required": True,
        "production_pr_created": False,
        "production_pr_creation_authorized": False,
        "production_pr_merge_authorized": False,
        "production_code_mutation": False,
        "execution_authorized": False,
    }.items():
        if package.get(key) != expected:
            raise ValueError(f"candidate patch promotion-package policy mismatch: {key}")
    expected = {key: value for key, value in package.items() if key != "promotion_package_id"}
    if package.get("promotion_package_id") != _stable_sha256(expected):
        raise ValueError("candidate patch promotion-package digest mismatch")


def qualify_candidate_patch(
    pin: dict[str, Any],
    plan: dict[str, Any],
    patch: dict[str, Any],
    control_manifest: dict[str, Any],
    *,
    control_root: Path,
    intervention_root: Path,
    sandbox_cases: list[dict[str, Any]],
    qualified_by: str,
) -> dict[str, Any]:
    validate_candidate_patch(
        patch,
        pin=pin,
        plan=plan,
        control_manifest=control_manifest,
        control_root=control_root,
    )
    safety = qualify_patch_static_safety(
        patch,
        pin=pin,
        plan=plan,
        control_manifest=control_manifest,
        control_root=control_root,
    )
    if safety["status"] != "PASS":
        core = {
            "patch_qualification_version": PATCH_QUALIFICATION_VERSION,
            "patch_id": patch["patch_id"],
            "experiment_plan_id": plan["plan_id"],
            "static_safety": safety,
            "status": "BLOCKED_STATIC_SAFETY",
            "pr_eligible": False,
            "promotion_package": None,
            "production_pr_created": False,
            "production_pr_merge_authorized": False,
            "production_code_mutation": False,
            "execution_authorized": False,
        }
        core["qualification_id"] = _stable_sha256(core)
        return core

    intervention, materialization = materialize_candidate_artifact(
        pin,
        plan,
        control_manifest,
        control_root=Path(control_root),
        candidate_root=Path(intervention_root),
        overlay=patch_to_lab89_overlay(patch),
    )
    validate_materialization(
        materialization,
        plan=plan,
        pin=pin,
        control=control_manifest,
        intervention=intervention,
    )

    corpus_cases = lab87_corpus_cases(sandbox_cases)
    if corpus_sha256(corpus_cases) != plan["corpus_sha256"]:
        raise ValueError("candidate patch sandbox corpus does not match LAB #85 plan")
    lab87_manifest = build_execution_manifest(
        plan,
        corpus_cases=corpus_cases,
        control_runtime_sha256=control_manifest["tree_sha256"],
        intervention_runtime_sha256=intervention["tree_sha256"],
        control_domain_digests=control_manifest["domain_digests"],
        intervention_domain_digests=intervention["domain_digests"],
    )
    validate_execution_manifest(lab87_manifest, plan=plan)
    adapter = MaterializedHumanSandboxAdapter(
        pin=pin,
        control_root=Path(control_root),
        intervention_root=Path(intervention_root),
        sandbox_cases=sandbox_cases,
    )
    lab87_receipt = execute_controlled_experiment(
        plan,
        lab87_manifest,
        adapter,
        performed_by=f"LAB-91:{qualified_by.strip()}",
    )
    validate_execution_receipt(lab87_receipt, plan=plan, manifest=lab87_manifest)

    result_input = receipt_to_lab85_result_input(plan, lab87_manifest, lab87_receipt)
    lab85_result, lab85_qualification = qualify_experiment_result(
        plan,
        result_input,
        verified_by=qualified_by,
    )
    validate_experiment_result(lab85_result, plan=plan)
    validate_experiment_qualification(lab85_qualification, result=lab85_result)

    eligible = (
        lab85_result["outcome"] == "SUPPORTS_HYPOTHESIS"
        and lab85_qualification["admissible_direct_evidence"] is True
        and lab85_qualification["direct_evidence_direction"] == "SUPPORTS"
        and lab85_qualification["direct_evidence_strength"] == "DIRECT"
    )
    package = None
    if eligible:
        package = _promotion_package(
            patch=patch,
            safety=safety,
            pin=pin,
            plan=plan,
            materialization=materialization,
            lab87_manifest=lab87_manifest,
            lab87_receipt=lab87_receipt,
            lab85_result=lab85_result,
            lab85_qualification=lab85_qualification,
            qualified_by=qualified_by,
        )

    core = {
        "patch_qualification_version": PATCH_QUALIFICATION_VERSION,
        "patch_id": patch["patch_id"],
        "experiment_plan_id": plan["plan_id"],
        "target_domain": plan["target_domain"],
        "static_safety": safety,
        "materialization": materialization,
        "intervention_manifest": intervention,
        "lab87_manifest": lab87_manifest,
        "lab87_receipt": lab87_receipt,
        "lab85_result": lab85_result,
        "lab85_qualification": lab85_qualification,
        "status": "PR_ELIGIBLE" if eligible else "EVIDENCE_NOT_SUPPORTING",
        "pr_eligible": eligible,
        "promotion_package": package,
        "production_pr_created": False,
        "production_pr_merge_authorized": False,
        "production_code_mutation": False,
        "execution_authorized": False,
    }
    core["qualification_id"] = _stable_sha256(core)
    validate_patch_qualification(core, patch=patch, pin=pin, plan=plan)
    return core


def validate_patch_qualification(
    qualification: dict[str, Any],
    *,
    patch: dict[str, Any],
    pin: dict[str, Any],
    plan: dict[str, Any],
) -> None:
    if qualification.get("patch_qualification_version") != PATCH_QUALIFICATION_VERSION:
        raise ValueError("unsupported candidate patch qualification version")
    if qualification.get("patch_id") != patch.get("patch_id") or qualification.get("experiment_plan_id") != plan["plan_id"]:
        raise ValueError("candidate patch qualification identity mismatch")
    safety = qualification.get("static_safety")
    if not isinstance(safety, dict):
        raise ValueError("candidate patch qualification lacks static-safety evidence")
    validate_patch_static_safety(safety, patch=patch)
    eligible = qualification.get("pr_eligible") is True
    if eligible:
        if qualification.get("status") != "PR_ELIGIBLE":
            raise ValueError("PR-eligible patch qualification status mismatch")
        result = qualification.get("lab85_result")
        lab85q = qualification.get("lab85_qualification")
        package = qualification.get("promotion_package")
        if not isinstance(result, dict) or not isinstance(lab85q, dict) or not isinstance(package, dict):
            raise ValueError("PR-eligible patch lacks controlled evidence package")
        if result.get("outcome") != "SUPPORTS_HYPOTHESIS":
            raise ValueError("PR-eligible patch lacks LAB #85 support")
        if lab85q.get("direct_evidence_direction") != "SUPPORTS" or lab85q.get("direct_evidence_strength") != "DIRECT":
            raise ValueError("PR-eligible patch lacks LAB #85 DIRECT SUPPORTS")
        validate_promotion_package(
            package,
            patch=patch,
            safety=safety,
            pin=pin,
            plan=plan,
            materialization=qualification["materialization"],
            lab87_manifest=qualification["lab87_manifest"],
            lab87_receipt=qualification["lab87_receipt"],
            lab85_result=result,
            lab85_qualification=lab85q,
        )
    else:
        if qualification.get("promotion_package") is not None:
            raise ValueError("non-eligible patch cannot contain a promotion package")
    for key, expected in {
        "production_pr_created": False,
        "production_pr_merge_authorized": False,
        "production_code_mutation": False,
        "execution_authorized": False,
    }.items():
        if qualification.get(key) != expected:
            raise ValueError(f"candidate patch qualification policy mismatch: {key}")
    expected = {key: value for key, value in qualification.items() if key != "qualification_id"}
    if qualification.get("qualification_id") != _stable_sha256(expected):
        raise ValueError("candidate patch qualification digest mismatch")


def _ledger_row(qualification: dict[str, Any]) -> dict[str, Any]:
    safety = qualification["static_safety"]
    row = {
        "patch_id": qualification["patch_id"],
        "experiment_plan_id": qualification["experiment_plan_id"],
        "qualification_id": qualification["qualification_id"],
        "static_safety_id": safety["static_safety_id"],
        "status": qualification["status"],
        "pr_eligible": qualification["pr_eligible"],
    }
    if qualification.get("materialization"):
        row["materialization_id"] = qualification["materialization"]["materialization_id"]
    if qualification.get("lab87_manifest"):
        row["lab87_manifest_id"] = qualification["lab87_manifest"]["manifest_id"]
    if qualification.get("lab87_receipt"):
        row["lab87_receipt_id"] = qualification["lab87_receipt"]["receipt_id"]
    if qualification.get("lab85_result"):
        row["lab85_result_id"] = qualification["lab85_result"]["result_id"]
        row["lab85_outcome"] = qualification["lab85_result"]["outcome"]
    if qualification.get("lab85_qualification"):
        row["lab85_qualification_id"] = qualification["lab85_qualification"]["qualification_id"]
    if qualification.get("promotion_package"):
        row["promotion_package_id"] = qualification["promotion_package"]["promotion_package_id"]
        row["target_repository"] = qualification["promotion_package"]["target_repository"]
        row["base_commit_sha"] = qualification["promotion_package"]["base_commit_sha"]
        row["changed_paths"] = list(qualification["promotion_package"]["changed_paths"])
    return row


def validate_patch_ledger(ledger: dict[str, Any]) -> None:
    if ledger.get("ledger_version") != PATCH_LEDGER_VERSION:
        raise ValueError("unsupported candidate patch qualification-ledger version")
    required = empty_patch_ledger()["policy"]
    if not isinstance(ledger.get("policy"), dict):
        raise ValueError("candidate patch ledger policy is required")
    for key, expected in required.items():
        if ledger["policy"].get(key) != expected:
            raise ValueError(f"candidate patch ledger policy mismatch: {key}")
    rows = ledger.get("qualifications")
    if not isinstance(rows, list):
        raise ValueError("candidate patch ledger qualifications must be a list")
    patch_ids: set[str] = set()
    evidence_ids: set[str] = set()
    eligible_plans: set[str] = set()
    for sequence, row in enumerate(rows, start=1):
        if row.get("sequence") != sequence:
            raise ValueError("candidate patch ledger sequence is invalid")
        for key in ("patch_id", "experiment_plan_id", "qualification_id", "static_safety_id"):
            if not _is_sha256(row.get(key)):
                raise ValueError(f"candidate patch ledger identity is invalid: {key}")
        if row["patch_id"] in patch_ids:
            raise ValueError("candidate patch ledger contains duplicate patch")
        patch_ids.add(row["patch_id"])
        for key in ("materialization_id", "lab87_manifest_id", "lab87_receipt_id", "lab85_result_id", "lab85_qualification_id", "promotion_package_id"):
            value = row.get(key)
            if value is not None:
                if not _is_sha256(value):
                    raise ValueError(f"candidate patch ledger evidence identity is invalid: {key}")
                if value in evidence_ids:
                    raise ValueError("candidate patch ledger reuses controlled evidence identity")
                evidence_ids.add(value)
        if row.get("pr_eligible") is True:
            if row.get("status") != "PR_ELIGIBLE" or not _is_sha1(row.get("base_commit_sha")):
                raise ValueError("candidate patch ledger PR-eligible row is incomplete")
            plan_id = row["experiment_plan_id"]
            if plan_id in eligible_plans:
                raise ValueError("candidate patch ledger allows multiple PR-eligible patches for one plan")
            eligible_plans.add(plan_id)
    if ledger.get("production_code_mutation", False) is not False or ledger.get("execution_authorized", False) is not False:
        raise ValueError("candidate patch ledger exceeds authority boundary")


def record_patch_qualification(
    ledger: dict[str, Any],
    qualification: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    validate_patch_ledger(ledger)
    if not _is_sha256(qualification.get("patch_id")) or not _is_sha256(qualification.get("qualification_id")):
        raise ValueError("candidate patch qualification lacks deterministic identities")
    row = _ledger_row(qualification)
    existing = next((item for item in ledger["qualifications"] if item["patch_id"] == row["patch_id"]), None)
    if existing is not None:
        comparable = {key: value for key, value in existing.items() if key != "sequence"}
        if comparable != row:
            raise ValueError("conflicting candidate patch qualification for patch identity")
        return deepcopy(ledger), {"status": "UNCHANGED", "patch_id": row["patch_id"]}
    if row["pr_eligible"]:
        conflict = next(
            (
                item
                for item in ledger["qualifications"]
                if item["experiment_plan_id"] == row["experiment_plan_id"] and item.get("pr_eligible") is True
            ),
            None,
        )
        if conflict is not None:
            raise ValueError("a different candidate patch is already PR-eligible for this experiment plan")
    updated = deepcopy(ledger)
    updated["qualifications"].append({"sequence": len(updated["qualifications"]) + 1, **row})
    validate_patch_ledger(updated)
    return updated, {"status": "RECORDED", "patch_id": row["patch_id"], "pr_eligible": row["pr_eligible"]}


def ledger_summary(ledger: dict[str, Any]) -> dict[str, Any]:
    validate_patch_ledger(ledger)
    rows = ledger["qualifications"]
    return {
        "ledger_version": PATCH_LEDGER_VERSION,
        "qualification_count": len(rows),
        "pr_eligible_count": sum(1 for row in rows if row.get("pr_eligible") is True),
        "blocked_or_not_supporting_count": sum(1 for row in rows if row.get("pr_eligible") is not True),
        "production_pr_created": False,
        "production_pr_merge_authorized": False,
        "production_code_mutation": False,
        "execution_authorized": False,
    }


def _main_summary(args: argparse.Namespace) -> int:
    ledger = load_patch_ledger(Path(args.ledger) if args.ledger else None)
    print(json.dumps(ledger_summary(ledger), indent=2, sort_keys=True))
    return 0


def _main_validate_package(args: argparse.Namespace) -> int:
    payload = json.loads(Path(args.package).read_text(encoding="utf-8"))
    if payload.get("patch_promotion_package_version") != PROMOTION_PACKAGE_VERSION:
        raise ValueError("unsupported candidate patch promotion package")
    if payload.get("pr_eligible") is not True:
        raise ValueError("candidate patch promotion package is not PR-eligible")
    if payload.get("production_pr_created") is not False or payload.get("production_pr_merge_authorized") is not False:
        raise ValueError("candidate patch promotion package exceeds GitHub mutation boundary")
    if not _is_sha256(payload.get("promotion_package_id")):
        raise ValueError("candidate patch promotion-package ID is invalid")
    expected = {key: value for key, value in payload.items() if key != "promotion_package_id"}
    if payload["promotion_package_id"] != _stable_sha256(expected):
        raise ValueError("candidate patch promotion-package digest mismatch")
    print(json.dumps({"status": "VALID", "promotion_package_id": payload["promotion_package_id"]}, indent=2, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ROBERTA Human root-cause candidate patch qualification gate")
    sub = parser.add_subparsers(dest="command", required=True)
    summary = sub.add_parser("summary")
    summary.add_argument("--ledger")
    summary.set_defaults(func=_main_summary)
    package = sub.add_parser("validate-package")
    package.add_argument("--package", required=True)
    package.set_defaults(func=_main_validate_package)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
