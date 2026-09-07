# LAB #22 — Live Qualification Diagnostics v1

Status: **accepted / read-only diagnostic capability**

Tracking issue: #45

Accepted via PR #46 / merge `7eefde5355e99453f43cb4662226200b156cf7a0`.

## Purpose

LAB #22 turns LAB #21 live-grade JSONL into a deterministic remediation map.

It does not re-grade ROBERTA, reinterpret prose, or invent provider truth. It
starts only after LAB #21 has already produced one of:

- `PASS`
- `EVIDENCE_REQUIRED`
- `FAIL`

## Contract

`roberta_live_qualification_diagnostics/v1`

Input:

- LAB #21 `roberta_live_evidence_grader/v1` JSONL only.

Output:

- overall PASS / EVIDENCE_REQUIRED / FAIL counts;
- service-by-service verdict coverage;
- stable reason counts;
- deterministic remediation groups;
- likely owner repository;
- likely component/layer;
- affected services;
- occurrence count;
- priority;
- qualification-blocking state;
- whether the finding is a product-defect candidate;
- one recommended next action.

## Why this distinction matters

`EVIDENCE_REQUIRED` is not a factual ROBERTA failure.

Examples:

- missing telemetry;
- zero canonical claims;
- missing provenance;
- missing freshness metadata;
- missing Claim Integrity coverage.

Those conditions block qualification, but LAB #22 must not turn them into
fabricated factual defects.

`FAIL` is reserved for conditions LAB #21 can actually establish, including:

- runtime/transport failure;
- Claim Integrity not PASS;
- canonical claim/evidence disagreement;
- execution-boundary violation.

## Deterministic routing

The first v1 routing table is intentionally conservative.

### ROBERTA public shell / roberta-langgraph

- runtime/bridge failure;
- evaluation telemetry contract/version gaps;
- canonical claim projection gaps;
- evidence provenance/freshness projection gaps;
- claim-to-evidence path projection mismatches.

### Protected ROBERTA core / roberta-core

- missing or rejected `roberta_claim_integrity/v1`;
- execution-boundary violation.

### Laboratory / roberta-eval

Any previously unseen LAB #21 reason remains an unclassified Laboratory
diagnostic until an explicit routing rule is reviewed. LAB #22 never guesses a
product owner from an unknown reason.

## Priority policy

`P0`

- runtime failures blocking every live question;
- execution-boundary violations;
- Claim Integrity failures;
- proven canonical claim/evidence mismatches.

`P1`

- telemetry contract gaps;
- zero/malformed canonical claim coverage;
- missing Claim Integrity coverage.

`P2`

- missing evidence metadata;
- new unclassified diagnostic reasons.

Priority is deterministic and does not imply financial, legal, or security risk.

## CLI

```bash
roberta-eval live-diagnose \
  --input results/live-smoke-002.grades.jsonl \
  --json results/live-smoke-002.diagnostics.json \
  --markdown results/live-smoke-002.diagnostics.md
```

The command exits non-zero only when actual LAB #21 `FAIL` results are
present. A pure `EVIDENCE_REQUIRED` report remains qualification-blocking but
does not masquerade as a product failure.

## Confirmed 503 regression context

The first live failure cluster observed before LAB #22 was the stateless bridge
regression:

- normal and evaluation requests both returned HTTP 503;
- the public bridge reported `roberta_unavailable (ValueError)`;
- the failure began after the checkpoint-enabled runtime restart;
- root cause: the bridge compiled only a checkpointed graph while `thread_id`
  remained optional;
- accepted fix: stateless graph for no-thread requests and checkpointed graph
  only for explicit `thread_id` requests.

The accepted public fix is ROBERTA #401 / PR #402, merge
`4c872b4ac9fb25dda0994632e9e2f7dc4cc8cdfc`.

Protected compatibility is roberta-core #86 / PR #87, merge
`18c6d82377876c0627edb741e5c36f1f339dbbdc`.

That defect already has runtime-mode regression proof in the public and
protected ROBERTA repositories. LAB #22 classifies any recurrence as
`runtime_transport_failure`, P0, owned by the ROBERTA bridge/runtime path.

## Qualification boundary

LAB #22 does not certify:

- upstream provider truth;
- every natural-language sentence;
- live market correctness beyond LAB #21's structured evidence contract;
- execution authority.

The Laboratory remains read-only.
