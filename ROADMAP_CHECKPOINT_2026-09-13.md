# ROBERTA Evaluation Laboratory Roadmap Checkpoint — 2026-09-13

This checkpoint supersedes the current-execution portion of `ROADMAP_CHECKPOINT_2026-09-12.md` where later accepted Human-remediation/root-cause work applies. Historical LAB #1-#22 records remain unchanged.

## Current accepted state

The offline Human ROBERTA v2 remediation/root-cause control path is now accepted through **LAB #91**.

The control chain now extends beyond closure management into recurrence/root-cause investigation and evidence-backed candidate patch qualification:

`DETECTED -> PROPOSED -> APPROVED -> GITHUB_ISSUE -> FIX_MERGED -> REPLAY_VERIFIED -> IMPROVED / RESOLVED -> CLOSED -> REOPEN ADJUDICATION -> CHILD CYCLE / LINEAGE -> ROOT-CAUSE INVESTIGATION -> CORRELATION -> DIRECT EXPERIMENT -> CONTROLLED EXECUTION -> PINNED ARTIFACT SANDBOX -> CANDIDATE PATCH QUALIFICATION -> PR_ELIGIBLE`

## Accepted sequence after LAB #71

- LAB #73 — terminal closure reconciliation — COMPLETE.
- LAB #75 — reopen adjudication gate — COMPLETE.
- LAB #77 — reopen-cycle promotion / parent-child lineage — COMPLETE.
- LAB #79 — generational lineage reconciliation — COMPLETE.
- LAB #81 — root-cause investigation / closure sufficiency gate — COMPLETE.
- LAB #83 — root-cause evidence acquisition & correlation — COMPLETE.
- LAB #85 — DIRECT-evidence qualification & falsification — COMPLETE.
- LAB #87 — controlled experiment execution & reproducibility — COMPLETE.
- LAB #89 — pinned ROBERTA artifact materialization / offline sandbox — COMPLETE.
- LAB #91 — candidate intervention construction & patch qualification — COMPLETE via PR #92 / merge `85b07b1f2f9451d2baa62d4b05e4218a0d3b0f38`.

## LAB #91 authority boundary

LAB #91 may certify an intervention as `PR_ELIGIBLE` only after:

1. exact target-domain patch identity is bound to the pinned accepted ROBERTA control commit;
2. static safety rejects hidden dependency/network/process/environment/filesystem/dynamic-execution/protected-core/GitHub-mutation/authority changes;
3. the exact patch passes LAB #89 target-domain-only materialization/offline sandbox;
4. LAB #87 produces the immutable reproducibility manifest/receipt;
5. LAB #85 independently returns `SUPPORTS_HYPOTHESIS` + admissible `DIRECT SUPPORTS`.

A `PR_ELIGIBLE` package does **not** create or merge a production `roberta-langgraph` PR. Production PR promotion remains a future explicit owner-approved gate.

## Root-cause authority model

- LAB #83 correlation may rank suspects but cannot create causal proof.
- LAB #85 may qualify/falsify pre-registered DIRECT evidence.
- LAB #87 executes frozen experiments but has no outcome authority.
- LAB #89 materializes/exercises pinned public ROBERTA artifacts offline but has no causal authority.
- LAB #91 may declare a tested patch PR-eligible but cannot promote it into production GitHub work automatically.
- LAB #81 remains the sole root-cause naming authority under the accepted evidence threshold.

## Current role of the Laboratory

The Laboratory supports real ROBERTA Cohort 001 findings by turning repeated Human-quality defects into deterministic, reviewable remediation/root-cause evidence without replacing real-user product proof.

It should be used to:

1. ingest accepted content-free Human-quality evidence;
2. detect recurring defects and preserve parent-child lineage;
3. prevent merged PRs/clean replays from being mistaken for root-cause resolution;
4. isolate/falsify repeated failure domains with deterministic experiments;
5. qualify candidate Human patches offline before any production promotion.

## Pause boundary

Broad live LAB #21/#22 campaigns remain paused unless explicitly resumed.

Offline deterministic Human-quality/root-cause tooling may continue on accepted/saved evidence without resuming broad live campaigns.

## Current product linkage

Cohort 001 remains the flagship product-proof track. The Laboratory is supporting evidence/remediation infrastructure for observed Human/product defects such as C07 backend-language leakage and future repeated Human failures; it must not displace the fixed beta scenario pack or invent product gaps without user evidence.

## Repository checkpoint

Observed `roberta-eval` main immediately before this checkpoint write: `85b07b1f2f9451d2baa62d4b05e4218a0d3b0f38`.

No open `roberta-eval` PR is part of this checkpoint. LAB #93 — Production PR Promotion Gate — is the proposed next exact task but is **not implemented or accepted** at this checkpoint.

`production_code_mutation=false` unless separately approved through normal repository workflow.
`production_pr_created=false` for LAB #91.
`execution_authorized=false`.
