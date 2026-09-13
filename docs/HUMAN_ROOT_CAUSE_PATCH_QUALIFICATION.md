# LAB #91 — Human Root-Cause Candidate Intervention Construction & Patch Qualification

LAB #91 turns a proposed Human-layer code change into a reviewable, evidence-bound candidate patch. It does **not** create or merge a production pull request.

## Authority chain

`LAB #83 correlation → LAB #85 plan → LAB #89 pinned artifact → LAB #91 patch construction/static safety → LAB #89 offline materialization → LAB #87 deterministic execution → LAB #85 DIRECT-evidence qualification → LAB #91 PR-eligibility package`

LAB #81 remains the only root-cause naming authority. LAB #85 remains the DIRECT-evidence authority. LAB #89 remains the runtime-isolation authority.

## Patch identity

A candidate patch is bound to:

- the accepted LAB #89 source pin;
- `bhaygood29053-pixel/roberta-langgraph`;
- exact pinned base commit `becb264b8026b5cbbf99f0d12dea62463510c6ee`;
- one LAB #85 experiment plan;
- one Human target domain;
- existing allowlisted files only.

Only `MODIFY` operations are accepted. Additions, deletions, renames, path traversal, symlinks, binary content, stale control hashes, non-target paths, or undeclared changes fail closed.

The reviewable patch includes deterministic unified diffs plus old/new SHA-256 values. The durable qualification ledger intentionally stores no replacement bodies or diffs.

## Static safety

Before the patch reaches the sandbox, LAB #91 compares the accepted control source with the candidate and blocks newly introduced:

- imports/dependencies;
- network/socket/HTTP clients;
- subprocess/process launch capability;
- environment/secret access;
- dynamic import/eval/exec;
- filesystem mutation primitives;
- protected-core/GitHub mutation references;
- authority escalation such as `execution_authorized=True`.

Static analysis is **not** runtime proof. A static PASS only permits the candidate to continue into LAB #89's offline sandbox.

## Controlled evidence requirement

A candidate may become `PR_ELIGIBLE` only when all of the following are true:

1. patch identity and target-domain ownership are valid;
2. static safety is PASS;
3. LAB #89 materializes exactly the target-domain overlay and preserves all held-constant domain digests;
4. LAB #87 executes the frozen matched corpus with deterministic replicates and emits a valid observations-only receipt;
5. LAB #85 returns `SUPPORTS_HYPOTHESIS`, `admissible_direct_evidence=true`, `direct_evidence_direction=SUPPORTS`, and `direct_evidence_strength=DIRECT`.

A contradiction, ambiguity, non-reproducing control, static-safety block, materialization failure, or runtime failure leaves the candidate ineligible.

## Promotion package

An eligible patch produces `roberta_human_root_cause_patch_promotion_package/v1`, binding:

- patch ID and static-safety ID;
- target repository/base SHA/source pin;
- LAB #85 plan ID;
- materialization ID;
- LAB #87 manifest and receipt IDs;
- LAB #85 result and qualification IDs;
- changed paths and review digest summary.

The package always states:

- `owner_review_still_required=true`;
- `production_pr_created=false`;
- `production_pr_creation_authorized=false`;
- `production_pr_merge_authorized=false`;
- `production_code_mutation=false`;
- `execution_authorized=false`.

A later explicitly authorized workflow may consume the package to prepare a real `roberta-langgraph` remediation PR. LAB #91 itself never does so.

## CLI

```bash
roberta-eval-human-root-cause-patch summary
roberta-eval-human-root-cause-patch validate-package --package /path/to/package.json
```

The tracked ledger starts empty. LAB #21/#22 remain paused.
