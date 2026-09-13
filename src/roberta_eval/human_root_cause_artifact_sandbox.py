from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from copy import deepcopy
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

from .human_remediation_root_cause import DOMAINS
from .human_root_cause_direct_evidence import (
    record_experiment_result,
    validate_direct_evidence_ledger,
    validate_experiment_plan,
)
from .human_root_cause_experiment_execution import (
    build_execution_manifest,
    corpus_sha256,
    execute_controlled_experiment,
    receipt_to_lab85_result_input,
    submit_receipt_to_lab85,
    validate_execution_receipt,
)

SOURCE_PIN_VERSION = "roberta_human_root_cause_source_pin/v1"
ARTIFACT_MANIFEST_VERSION = "roberta_human_root_cause_artifact_manifest/v1"
MATERIALIZATION_VERSION = "roberta_human_root_cause_artifact_materialization/v1"
SANDBOX_RUNTIME_VERSION = "roberta_human_root_cause_offline_sandbox/v1"
SANDBOX_CASE_VERSION = "roberta_human_root_cause_sandbox_case/v1"
SANDBOX_HANDOFF_VERSION = "roberta_human_root_cause_sandbox_handoff/v1"
ARTIFACT_SANDBOX_LEDGER_VERSION = "roberta_human_root_cause_artifact_sandbox_ledger/v1"

ROBERTA_REPOSITORY = "bhaygood29053-pixel/roberta-langgraph"
ROBERTA_RENDERER_ENTRYPOINT = "roberta.human_response_renderer:render_human_response"


def _stable_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _bytes_sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(ch in "0123456789abcdefABCDEF" for ch in value)


def _is_sha40(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 40 and all(ch in "0123456789abcdefABCDEF" for ch in value)


def default_source_pin_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "human_root_cause_artifact_source.json"


def default_artifact_sandbox_ledger_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "human_root_cause_artifact_sandbox_ledger.json"


def load_source_pin(path: Path | None = None) -> dict[str, Any]:
    source = path or default_source_pin_path()
    payload = json.loads(source.read_text(encoding="utf-8"))
    validate_source_pin(payload)
    return payload


def validate_source_pin(pin: dict[str, Any]) -> None:
    if pin.get("source_pin_version") != SOURCE_PIN_VERSION:
        raise ValueError("unsupported ROBERTA artifact source-pin version")
    if pin.get("repository") != ROBERTA_REPOSITORY:
        raise ValueError("artifact sandbox source must be the accepted ROBERTA public repository")
    if not _is_sha40(pin.get("commit_sha")):
        raise ValueError("artifact sandbox source commit SHA is invalid")
    if pin.get("accepted") is not True or pin.get("floating_ref") is not False:
        raise ValueError("artifact sandbox requires an explicitly accepted immutable source commit")
    if pin.get("runtime_entrypoint") != ROBERTA_RENDERER_ENTRYPOINT:
        raise ValueError("artifact sandbox runtime entrypoint must use the accepted Human renderer")
    files = pin.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("artifact sandbox source pin requires an allowlisted file set")
    seen: set[str] = set()
    represented: set[str] = set()
    for item in files:
        if not isinstance(item, dict):
            raise ValueError("artifact sandbox source file entry must be an object")
        path = item.get("path")
        domain = item.get("owner_domain")
        if not isinstance(path, str) or not path.strip() or path in seen:
            raise ValueError("artifact sandbox source file path is invalid or duplicated")
        pure = PurePosixPath(path)
        if pure.is_absolute() or ".." in pure.parts:
            raise ValueError("artifact sandbox source file path escapes the materialized tree")
        if domain not in DOMAINS:
            raise ValueError("artifact sandbox source file owner domain is invalid")
        seen.add(path)
        represented.add(domain)
    empty_domains = pin.get("empty_domains_allowed") or []
    if not isinstance(empty_domains, list) or any(domain not in DOMAINS for domain in empty_domains):
        raise ValueError("artifact sandbox empty-domain policy is invalid")
    if represented | set(empty_domains) != set(DOMAINS):
        raise ValueError("artifact sandbox source pin must account for every Human domain")
    for key, expected in {
        "read_only_source": True,
        "production_runtime_touched": False,
        "production_code_mutation": False,
        "execution_authorized": False,
    }.items():
        if pin.get(key) != expected:
            raise ValueError(f"artifact sandbox source-pin policy mismatch: {key}")
    expected = {key: value for key, value in pin.items() if key != "source_pin_sha256"}
    if pin.get("source_pin_sha256") != _stable_sha256(expected):
        raise ValueError("artifact sandbox source-pin digest mismatch")


class ArtifactSource(Protocol):
    def get_file(self, *, repository: str, commit_sha: str, path: str) -> bytes: ...


class GitHubRawArtifactSource:
    """Explicit read-only source transport. Not used by default or by CI acceptance."""

    def __init__(self, token: str = "", *, api_base: str = "https://api.github.com") -> None:
        self._token = token.strip()
        self._api_base = api_base.rstrip("/")

    def get_file(self, *, repository: str, commit_sha: str, path: str) -> bytes:
        if repository != ROBERTA_REPOSITORY or not _is_sha40(commit_sha):
            raise ValueError("artifact source identity is not an accepted ROBERTA commit")
        encoded = urllib.parse.quote(path, safe="/")
        url = f"{self._api_base}/repos/{repository}/contents/{encoded}?ref={commit_sha}"
        headers = {
            "Accept": "application/vnd.github.raw+json",
            "User-Agent": "roberta-eval-artifact-sandbox",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        request = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"ROBERTA artifact read failed: HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"ROBERTA artifact read failed: {exc.reason}") from exc


def _domain_digest(files: list[dict[str, Any]], domain: str) -> str:
    rows = [
        {"path": item["path"], "sha256": item["sha256"]}
        for item in files
        if item["owner_domain"] == domain
    ]
    rows.sort(key=lambda item: item["path"])
    return _stable_sha256(rows)


def _manifest_from_root(
    *,
    pin: dict[str, Any],
    root: Path,
    arm: str,
) -> dict[str, Any]:
    validate_source_pin(pin)
    if arm not in {"CONTROL", "INTERVENTION"}:
        raise ValueError("artifact manifest arm is invalid")
    files: list[dict[str, Any]] = []
    for spec in pin["files"]:
        path = spec["path"]
        file_path = root / PurePosixPath(path)
        if not file_path.is_file():
            raise ValueError(f"materialized ROBERTA artifact is missing allowlisted file: {path}")
        content = file_path.read_bytes()
        files.append(
            {
                "path": path,
                "owner_domain": spec["owner_domain"],
                "sha256": _bytes_sha256(content),
                "size_bytes": len(content),
            }
        )
    expected_paths = {item["path"] for item in pin["files"]}
    observed_paths = {
        file.relative_to(root).as_posix()
        for file in root.rglob("*")
        if file.is_file()
    }
    if observed_paths != expected_paths:
        raise ValueError("materialized ROBERTA artifact contains missing or extra files")
    files.sort(key=lambda item: item["path"])
    domain_digests = {domain: _domain_digest(files, domain) for domain in DOMAINS}
    core = {
        "artifact_manifest_version": ARTIFACT_MANIFEST_VERSION,
        "source_pin_sha256": pin["source_pin_sha256"],
        "repository": pin["repository"],
        "commit_sha": pin["commit_sha"],
        "arm": arm,
        "runtime_entrypoint": pin["runtime_entrypoint"],
        "files": files,
        "domain_digests": domain_digests,
        "tree_sha256": _stable_sha256(
            [{"path": item["path"], "owner_domain": item["owner_domain"], "sha256": item["sha256"]} for item in files]
        ),
        "ephemeral": True,
        "production_runtime_touched": False,
        "production_code_mutation": False,
        "execution_authorized": False,
    }
    core["manifest_sha256"] = _stable_sha256(core)
    validate_artifact_manifest(core, pin=pin)
    return core


def validate_artifact_manifest(manifest: dict[str, Any], *, pin: dict[str, Any]) -> None:
    validate_source_pin(pin)
    if manifest.get("artifact_manifest_version") != ARTIFACT_MANIFEST_VERSION:
        raise ValueError("unsupported ROBERTA artifact-manifest version")
    if manifest.get("source_pin_sha256") != pin["source_pin_sha256"]:
        raise ValueError("ROBERTA artifact manifest source-pin identity mismatch")
    if manifest.get("repository") != pin["repository"] or manifest.get("commit_sha") != pin["commit_sha"]:
        raise ValueError("ROBERTA artifact manifest source identity mismatch")
    if manifest.get("arm") not in {"CONTROL", "INTERVENTION"}:
        raise ValueError("ROBERTA artifact manifest arm is invalid")
    files = manifest.get("files")
    if not isinstance(files, list) or len(files) != len(pin["files"]):
        raise ValueError("ROBERTA artifact manifest file set is invalid")
    expected_specs = {item["path"]: item["owner_domain"] for item in pin["files"]}
    observed_paths: set[str] = set()
    for item in files:
        if item.get("path") not in expected_specs or item.get("owner_domain") != expected_specs[item["path"]]:
            raise ValueError("ROBERTA artifact manifest contains an unaccepted path/domain mapping")
        if not _is_sha256(item.get("sha256")) or not isinstance(item.get("size_bytes"), int) or item["size_bytes"] < 0:
            raise ValueError("ROBERTA artifact file digest/size is invalid")
        observed_paths.add(item["path"])
    if observed_paths != set(expected_specs):
        raise ValueError("ROBERTA artifact manifest path set does not match source pin")
    domain_digests = manifest.get("domain_digests")
    if not isinstance(domain_digests, dict) or set(domain_digests) != set(DOMAINS):
        raise ValueError("ROBERTA artifact manifest must digest every Human domain")
    for domain in DOMAINS:
        if domain_digests[domain] != _domain_digest(files, domain):
            raise ValueError(f"ROBERTA artifact domain digest mismatch: {domain}")
    if manifest.get("tree_sha256") != _stable_sha256(
        [{"path": item["path"], "owner_domain": item["owner_domain"], "sha256": item["sha256"]} for item in files]
    ):
        raise ValueError("ROBERTA artifact tree digest mismatch")
    for key, expected in {
        "runtime_entrypoint": pin["runtime_entrypoint"],
        "ephemeral": True,
        "production_runtime_touched": False,
        "production_code_mutation": False,
        "execution_authorized": False,
    }.items():
        if manifest.get(key) != expected:
            raise ValueError(f"ROBERTA artifact-manifest policy mismatch: {key}")
    expected = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    if manifest.get("manifest_sha256") != _stable_sha256(expected):
        raise ValueError("ROBERTA artifact manifest digest mismatch")


def materialize_control_artifact(
    pin: dict[str, Any],
    source: ArtifactSource,
    *,
    root: Path,
) -> dict[str, Any]:
    validate_source_pin(pin)
    if root.exists():
        if any(root.iterdir()):
            raise ValueError("control artifact materialization root must be empty")
    else:
        root.mkdir(parents=True)
    for spec in pin["files"]:
        content = source.get_file(
            repository=pin["repository"],
            commit_sha=pin["commit_sha"],
            path=spec["path"],
        )
        if not isinstance(content, (bytes, bytearray)):
            raise ValueError("artifact source must return raw file bytes")
        destination = root / PurePosixPath(spec["path"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(bytes(content))
    return _manifest_from_root(pin=pin, root=root, arm="CONTROL")


def _overlay_digest(overlay: list[dict[str, Any]]) -> str:
    normalized = [
        {
            "path": item["path"],
            "expected_control_sha256": item["expected_control_sha256"],
            "replacement_sha256": _bytes_sha256(item["content_utf8"].encode("utf-8")),
        }
        for item in overlay
    ]
    normalized.sort(key=lambda item: item["path"])
    return _stable_sha256(normalized)


def materialize_candidate_artifact(
    pin: dict[str, Any],
    plan: dict[str, Any],
    control_manifest: dict[str, Any],
    *,
    control_root: Path,
    candidate_root: Path,
    overlay: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    validate_source_pin(pin)
    validate_experiment_plan(plan)
    validate_artifact_manifest(control_manifest, pin=pin)
    if control_manifest["arm"] != "CONTROL":
        raise ValueError("candidate materialization requires a CONTROL artifact manifest")
    if not isinstance(overlay, list) or not overlay:
        raise ValueError("candidate intervention overlay must contain at least one target-domain change")
    specs = {item["path"]: item for item in pin["files"]}
    control_files = {item["path"]: item for item in control_manifest["files"]}
    seen: set[str] = set()
    target = plan["target_domain"]
    for item in overlay:
        if not isinstance(item, dict):
            raise ValueError("candidate overlay entry must be an object")
        path = item.get("path")
        if path in seen or path not in specs:
            raise ValueError("candidate overlay path is duplicated or outside the accepted artifact")
        if specs[path]["owner_domain"] != target:
            raise ValueError("candidate overlay attempted to change a non-target Human domain")
        if item.get("expected_control_sha256") != control_files[path]["sha256"]:
            raise ValueError("candidate overlay control-file digest does not match materialized control")
        if not isinstance(item.get("content_utf8"), str):
            raise ValueError("candidate overlay replacement content must be UTF-8 text")
        seen.add(path)
    if candidate_root.exists():
        if any(candidate_root.iterdir()):
            raise ValueError("candidate artifact materialization root must be empty")
    else:
        candidate_root.mkdir(parents=True)
    for spec in pin["files"]:
        source_file = control_root / PurePosixPath(spec["path"])
        destination = candidate_root / PurePosixPath(spec["path"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_file, destination)
    for item in overlay:
        (candidate_root / PurePosixPath(item["path"])).write_text(item["content_utf8"], encoding="utf-8")
    candidate = _manifest_from_root(pin=pin, root=candidate_root, arm="INTERVENTION")
    candidate_files = {item["path"]: item for item in candidate["files"]}
    changed_paths = sorted(
        path for path in control_files if control_files[path]["sha256"] != candidate_files[path]["sha256"]
    )
    if changed_paths != sorted(seen):
        raise ValueError("candidate artifact changed files outside the declared target-domain overlay")
    if control_manifest["domain_digests"][target] == candidate["domain_digests"][target]:
        raise ValueError("candidate intervention did not change the target Human domain digest")
    for domain in plan["held_constant_domains"]:
        if control_manifest["domain_digests"][domain] != candidate["domain_digests"][domain]:
            raise ValueError(f"candidate artifact changed held-constant Human domain: {domain}")
    evidence = {
        "materialization_version": MATERIALIZATION_VERSION,
        "experiment_plan_id": plan["plan_id"],
        "source_pin_sha256": pin["source_pin_sha256"],
        "source_commit_sha": pin["commit_sha"],
        "target_domain": target,
        "control_manifest_sha256": control_manifest["manifest_sha256"],
        "intervention_manifest_sha256": candidate["manifest_sha256"],
        "control_tree_sha256": control_manifest["tree_sha256"],
        "intervention_tree_sha256": candidate["tree_sha256"],
        "overlay_sha256": _overlay_digest(overlay),
        "changed_paths": changed_paths,
        "held_constant_domains": deepcopy(plan["held_constant_domains"]),
        "target_domain_only_overlay": True,
        "source_content_mutation": False,
        "production_runtime_touched": False,
        "production_code_mutation": False,
        "execution_authorized": False,
    }
    evidence["materialization_id"] = _stable_sha256(evidence)
    validate_materialization(evidence, plan=plan, pin=pin, control=control_manifest, intervention=candidate)
    return candidate, evidence


def validate_materialization(
    evidence: dict[str, Any],
    *,
    plan: dict[str, Any],
    pin: dict[str, Any],
    control: dict[str, Any],
    intervention: dict[str, Any],
) -> None:
    validate_experiment_plan(plan)
    validate_source_pin(pin)
    validate_artifact_manifest(control, pin=pin)
    validate_artifact_manifest(intervention, pin=pin)
    if evidence.get("materialization_version") != MATERIALIZATION_VERSION:
        raise ValueError("unsupported ROBERTA artifact materialization version")
    if evidence.get("experiment_plan_id") != plan["plan_id"] or evidence.get("target_domain") != plan["target_domain"]:
        raise ValueError("artifact materialization plan identity mismatch")
    if evidence.get("source_pin_sha256") != pin["source_pin_sha256"] or evidence.get("source_commit_sha") != pin["commit_sha"]:
        raise ValueError("artifact materialization source identity mismatch")
    if evidence.get("control_manifest_sha256") != control["manifest_sha256"] or evidence.get("intervention_manifest_sha256") != intervention["manifest_sha256"]:
        raise ValueError("artifact materialization manifest identity mismatch")
    if evidence.get("held_constant_domains") != plan["held_constant_domains"]:
        raise ValueError("artifact materialization held-constant domains differ from LAB #85 plan")
    if not evidence.get("changed_paths"):
        raise ValueError("artifact materialization requires at least one changed target-domain path")
    spec_domains = {item["path"]: item["owner_domain"] for item in pin["files"]}
    if any(spec_domains.get(path) != plan["target_domain"] for path in evidence["changed_paths"]):
        raise ValueError("artifact materialization records non-target file change")
    for domain in plan["held_constant_domains"]:
        if control["domain_digests"][domain] != intervention["domain_digests"][domain]:
            raise ValueError("artifact materialization held-constant domain digest mismatch")
    for key, expected in {
        "target_domain_only_overlay": True,
        "source_content_mutation": False,
        "production_runtime_touched": False,
        "production_code_mutation": False,
        "execution_authorized": False,
    }.items():
        if evidence.get(key) != expected:
            raise ValueError(f"artifact materialization policy mismatch: {key}")
    expected = {key: value for key, value in evidence.items() if key != "materialization_id"}
    if evidence.get("materialization_id") != _stable_sha256(expected):
        raise ValueError("artifact materialization digest mismatch")


def normalize_sandbox_cases(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(cases, list) or not cases:
        raise ValueError("artifact sandbox cases must be a non-empty list")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in cases:
        if not isinstance(item, dict):
            raise ValueError("artifact sandbox case must be an object")
        case_id = item.get("case_id")
        decision = item.get("response_decision")
        depth = item.get("response_depth", "normal")
        predicate = item.get("failure_predicate")
        if not isinstance(case_id, str) or not case_id.strip() or case_id in seen:
            raise ValueError("artifact sandbox case_id is invalid or duplicated")
        if not isinstance(decision, dict):
            raise ValueError("artifact sandbox response_decision must be an object")
        if depth not in {"quick", "normal", "deep_dive"}:
            raise ValueError("artifact sandbox response_depth is invalid")
        if not isinstance(predicate, dict) or predicate.get("kind") not in {"contains_any", "contains_all", "equals"}:
            raise ValueError("artifact sandbox failure predicate is invalid")
        terms = predicate.get("terms")
        if not isinstance(terms, list) or not terms or any(not isinstance(term, str) or not term for term in terms):
            raise ValueError("artifact sandbox failure predicate terms are invalid")
        core = {
            "sandbox_case_version": SANDBOX_CASE_VERSION,
            "case_id": case_id.strip(),
            "response_decision": deepcopy(decision),
            "response_depth": depth,
            "failure_predicate": {"kind": predicate["kind"], "terms": list(terms)},
        }
        core["input_sha256"] = _stable_sha256(core)
        normalized.append(core)
        seen.add(case_id)
    return normalized


def lab87_corpus_cases(cases: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {"case_id": item["case_id"], "input_sha256": item["input_sha256"]}
        for item in normalize_sandbox_cases(cases)
    ]


def _predicate_matches(text: str, predicate: dict[str, Any]) -> bool:
    kind = predicate["kind"]
    terms = predicate["terms"]
    if kind == "contains_any":
        return any(term in text for term in terms)
    if kind == "contains_all":
        return all(term in text for term in terms)
    return text == terms[0]


_BOOTSTRAP = r'''
import importlib, json, socket, sys
class _BlockedSocket:
    def __init__(self, *args, **kwargs):
        raise RuntimeError("network disabled in ROBERTA root-cause sandbox")
socket.socket = _BlockedSocket
socket.create_connection = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("network disabled in ROBERTA root-cause sandbox"))
payload = json.loads(sys.stdin.read())
module_name, fn_name = payload["entrypoint"].split(":", 1)
module = importlib.import_module(module_name)
fn = getattr(module, fn_name)
text = fn(payload["response_decision"], response_depth=payload["response_depth"])
if not isinstance(text, str):
    raise TypeError("Human renderer returned non-text output")
sys.stdout.write(json.dumps({"text": text}, sort_keys=True))
'''


class MaterializedHumanSandboxAdapter:
    def __init__(
        self,
        *,
        pin: dict[str, Any],
        control_root: Path,
        intervention_root: Path,
        sandbox_cases: list[dict[str, Any]],
        timeout_seconds: int = 20,
    ) -> None:
        validate_source_pin(pin)
        self.pin = deepcopy(pin)
        self.control_root = Path(control_root)
        self.intervention_root = Path(intervention_root)
        self.cases = {item["case_id"]: item for item in normalize_sandbox_cases(sandbox_cases)}
        self.timeout_seconds = timeout_seconds

    def _render(self, *, root: Path, case: dict[str, Any]) -> str:
        source_root = root / "src"
        if not source_root.is_dir():
            raise ValueError("materialized ROBERTA sandbox is missing src/")
        env = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONPATH": str(source_root),
            "PYTHONHASHSEED": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
            "ROBERTA_OFFLINE_SANDBOX": "1",
            "NO_PROXY": "*",
            "no_proxy": "*",
        }
        payload = {
            "entrypoint": self.pin["runtime_entrypoint"],
            "response_decision": case["response_decision"],
            "response_depth": case["response_depth"],
        }
        completed = subprocess.run(
            [sys.executable, "-c", _BOOTSTRAP],
            input=json.dumps(payload, sort_keys=True),
            text=True,
            capture_output=True,
            cwd=root,
            env=env,
            timeout=self.timeout_seconds,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"offline ROBERTA sandbox failed: {completed.stderr.strip()}")
        parsed = json.loads(completed.stdout)
        text = parsed.get("text")
        if not isinstance(text, str):
            raise RuntimeError("offline ROBERTA sandbox returned invalid renderer output")
        return text

    def run_arm(
        self,
        *,
        plan: dict[str, Any],
        arm: str,
        environment: dict[str, Any],
        cases: list[dict[str, str]],
        deterministic_seed: str,
    ) -> dict[str, Any]:
        validate_experiment_plan(plan)
        if arm not in {"CONTROL", "INTERVENTION"}:
            raise ValueError("offline ROBERTA sandbox arm is invalid")
        root = self.control_root if arm == "CONTROL" else self.intervention_root
        rows: list[dict[str, Any]] = []
        for expected in cases:
            case = self.cases.get(expected["case_id"])
            if case is None or case["input_sha256"] != expected["input_sha256"]:
                raise ValueError("offline ROBERTA sandbox case identity drift detected")
            text = self._render(root=root, case=case)
            rows.append(
                {
                    "case_id": case["case_id"],
                    "input_sha256": case["input_sha256"],
                    "targeted_failure": _predicate_matches(text, case["failure_predicate"]),
                    "output_sha256": _bytes_sha256(text.encode("utf-8")),
                }
            )
        return {
            "arm": arm,
            "runtime_status": "PASS",
            "deterministic_seed": deterministic_seed,
            "environment_id": environment["environment_id"],
            "case_results": rows,
        }


def execute_materialized_sandbox(
    plan: dict[str, Any],
    pin: dict[str, Any],
    control_manifest: dict[str, Any],
    intervention_manifest: dict[str, Any],
    materialization: dict[str, Any],
    *,
    control_root: Path,
    intervention_root: Path,
    sandbox_cases: list[dict[str, Any]],
    performed_by: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    validate_materialization(
        materialization,
        plan=plan,
        pin=pin,
        control=control_manifest,
        intervention=intervention_manifest,
    )
    cases = lab87_corpus_cases(sandbox_cases)
    if corpus_sha256(cases) != plan["corpus_sha256"]:
        raise ValueError("materialized sandbox corpus does not match pre-registered LAB #85 plan")
    manifest = build_execution_manifest(
        plan,
        corpus_cases=cases,
        control_runtime_sha256=control_manifest["tree_sha256"],
        intervention_runtime_sha256=intervention_manifest["tree_sha256"],
        control_domain_digests=control_manifest["domain_digests"],
        intervention_domain_digests=intervention_manifest["domain_digests"],
    )
    adapter = MaterializedHumanSandboxAdapter(
        pin=pin,
        control_root=control_root,
        intervention_root=intervention_root,
        sandbox_cases=sandbox_cases,
    )
    receipt = execute_controlled_experiment(plan, manifest, adapter, performed_by=performed_by)
    validate_execution_receipt(receipt, plan=plan, manifest=manifest)
    handoff = {
        "sandbox_handoff_version": SANDBOX_HANDOFF_VERSION,
        "experiment_plan_id": plan["plan_id"],
        "source_pin_sha256": pin["source_pin_sha256"],
        "materialization_id": materialization["materialization_id"],
        "lab87_manifest_id": manifest["manifest_id"],
        "lab87_receipt_id": receipt["receipt_id"],
        "runner_outcome_authority": False,
        "lab85_qualification_authority": True,
        "production_runtime_touched": False,
        "production_code_mutation": False,
        "execution_authorized": False,
    }
    handoff["handoff_id"] = _stable_sha256(handoff)
    return receipt, handoff


def qualify_materialized_receipt_with_lab85(
    plan: dict[str, Any],
    receipt: dict[str, Any],
    *,
    verified_by: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    result_input = receipt_to_lab85_result_input(plan, receipt)
    from .human_root_cause_direct_evidence import qualify_experiment_result
    return qualify_experiment_result(plan, result_input, verified_by=verified_by)


def submit_materialized_receipt_to_lab85(
    direct_evidence_ledger: dict[str, Any],
    plan: dict[str, Any],
    receipt: dict[str, Any],
    *,
    verified_by: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    validate_direct_evidence_ledger(direct_evidence_ledger)
    return submit_receipt_to_lab85(
        direct_evidence_ledger,
        plan,
        receipt,
        verified_by=verified_by,
    )


def empty_artifact_sandbox_ledger() -> dict[str, Any]:
    return {
        "ledger_version": ARTIFACT_SANDBOX_LEDGER_VERSION,
        "policy": {
            "accepted_control_source_required": True,
            "target_domain_only_overlay": True,
            "one_materialization_per_plan": True,
            "production_faithful_offline_sandbox": True,
            "runner_outcome_authority": False,
            "lab85_qualification_authority": True,
            "production_runtime_touched": False,
            "production_code_mutation": False,
            "github_issue_mutation": False,
            "execution_authorized": False,
        },
        "materializations": [],
    }


def validate_artifact_sandbox_ledger(ledger: dict[str, Any]) -> None:
    if ledger.get("ledger_version") != ARTIFACT_SANDBOX_LEDGER_VERSION:
        raise ValueError("unsupported artifact-sandbox ledger version")
    required = empty_artifact_sandbox_ledger()["policy"]
    if not isinstance(ledger.get("policy"), dict):
        raise ValueError("artifact-sandbox ledger policy is required")
    for key, expected in required.items():
        if ledger["policy"].get(key) != expected:
            raise ValueError(f"artifact-sandbox ledger policy mismatch: {key}")
    rows = ledger.get("materializations")
    if not isinstance(rows, list):
        raise ValueError("artifact-sandbox ledger materializations must be a list")
    plan_ids: set[str] = set()
    for sequence, row in enumerate(rows, start=1):
        if row.get("sequence") != sequence or not _is_sha256(row.get("experiment_plan_id")):
            raise ValueError("artifact-sandbox ledger sequence/plan identity is invalid")
        if row["experiment_plan_id"] in plan_ids:
            raise ValueError("artifact-sandbox ledger contains duplicate plan materialization")
        plan_ids.add(row["experiment_plan_id"])
        for key in ("source_pin_sha256", "materialization_id", "control_manifest_sha256", "intervention_manifest_sha256", "overlay_sha256"):
            if not _is_sha256(row.get(key)):
                raise ValueError(f"artifact-sandbox ledger evidence identity is invalid: {key}")
        if not isinstance(row.get("changed_paths"), list) or not row["changed_paths"]:
            raise ValueError("artifact-sandbox ledger changed_paths is invalid")
    if ledger.get("production_code_mutation", False) is not False or ledger.get("execution_authorized", False) is not False:
        raise ValueError("artifact-sandbox ledger exceeds authority boundary")


def record_materialization(
    ledger: dict[str, Any],
    materialization: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    validate_artifact_sandbox_ledger(ledger)
    plan_id = materialization.get("experiment_plan_id")
    if not _is_sha256(plan_id) or not _is_sha256(materialization.get("materialization_id")):
        raise ValueError("artifact materialization is missing deterministic identities")
    row = {
        "experiment_plan_id": plan_id,
        "source_pin_sha256": materialization["source_pin_sha256"],
        "materialization_id": materialization["materialization_id"],
        "control_manifest_sha256": materialization["control_manifest_sha256"],
        "intervention_manifest_sha256": materialization["intervention_manifest_sha256"],
        "overlay_sha256": materialization["overlay_sha256"],
        "changed_paths": list(materialization["changed_paths"]),
        "target_domain": materialization["target_domain"],
    }
    existing = next((item for item in ledger["materializations"] if item["experiment_plan_id"] == plan_id), None)
    if existing is not None:
        comparable = {key: value for key, value in existing.items() if key != "sequence"}
        if comparable != row:
            raise ValueError("conflicting artifact materialization for pre-registered experiment plan")
        return deepcopy(ledger), {"status": "UNCHANGED", "materialization_id": existing["materialization_id"]}
    updated = deepcopy(ledger)
    updated["materializations"].append({"sequence": len(updated["materializations"]) + 1, **row})
    validate_artifact_sandbox_ledger(updated)
    return updated, {"status": "RECORDED", "materialization_id": materialization["materialization_id"]}


def load_artifact_sandbox_ledger(path: Path | None = None) -> dict[str, Any]:
    source = path or default_artifact_sandbox_ledger_path()
    payload = json.loads(source.read_text(encoding="utf-8"))
    validate_artifact_sandbox_ledger(payload)
    return payload


def write_artifact_sandbox_ledger(path: Path, ledger: dict[str, Any]) -> None:
    validate_artifact_sandbox_ledger(ledger)
    path.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="roberta-eval-human-root-cause-sandbox")
    sub = parser.add_subparsers(dest="command", required=True)

    pin_cmd = sub.add_parser("source-pin")
    pin_cmd.add_argument("--source-pin", default=None)

    ledger_cmd = sub.add_parser("summary")
    ledger_cmd.add_argument("--ledger", default=None)

    corpus_cmd = sub.add_parser("corpus")
    corpus_cmd.add_argument("--cases", required=True)

    args = parser.parse_args(argv)
    if args.command == "source-pin":
        pin = load_source_pin(Path(args.source_pin) if args.source_pin else None)
        print(json.dumps(pin, indent=2, sort_keys=True))
        return 0
    if args.command == "corpus":
        payload = json.loads(Path(args.cases).read_text(encoding="utf-8"))
        rows = payload.get("cases") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            raise ValueError("sandbox cases JSON must contain a cases list")
        corpus = lab87_corpus_cases(rows)
        print(json.dumps({"cases": corpus, "corpus_sha256": corpus_sha256(corpus)}, indent=2, sort_keys=True))
        return 0
    ledger = load_artifact_sandbox_ledger(Path(args.ledger) if args.ledger else None)
    print(json.dumps({
        "ledger_version": ledger["ledger_version"],
        "materialization_count": len(ledger["materializations"]),
        "target_domain_only_overlay": True,
        "production_faithful_offline_sandbox": True,
        "runner_outcome_authority": False,
        "production_runtime_touched": False,
        "execution_authorized": False,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
