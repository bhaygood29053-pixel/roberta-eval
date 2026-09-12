# ROBERTA Evaluation Laboratory Roadmap Checkpoint — 2026-09-12

This checkpoint supersedes the broad **Workstream status — PAUSED BY OWNER** wording in `ROADMAP.md` for current execution status. The historical LAB #1-#22 acceptance record in `ROADMAP.md` remains authoritative.

## Current accepted state

The Evaluation Laboratory remains split into two deliberately different modes:

### Live evidence campaigns — PAUSED

Do not start or resume:

- LAB #21 / LAB #22 live campaigns;
- `live-smoke-005` or a later live-smoke sequence;
- new provider/live-evidence evaluation campaigns;
- eval-driven production remediation or regression promotion from new live runs;
- protected `roberta-core` #89 / PR #90 solely because historical LAB evidence exists.

The preserved live baseline remains:

```text
runtime OK:         20 / 20
PASS:               8
EVIDENCE_REQUIRED:  12
FAIL:               0
```

### Offline Human-quality evaluation — ACTIVE / ACCEPTED

Offline deterministic grading does **not** resume the paused live LAB campaigns.

Accepted on 2026-09-12:

- Human ROBERTA v2 zero-token language grading via PR #54 / merge `7c3a205a1fcaea4f282e9bec8728e42fae823348`;
- batch/replay zero-token Human v2 grading via Issue #55 / PR #56 / merge `6fecbfd937a961dc07df0ecd0d5d6288a294e983`;
- one `quality` command may replay one saved JSONL file or recursively grade saved-run directories;
- duplicate saved replies remain visible and graded;
- summaries expose PASS/LANGUAGE_DEFECT by service, response depth, and failure code;
- single-file compatibility remains supported;
- `ai_judge_used=false`;
- `judge_model_calls=0`;
- `external_calls=0`;
- `zero_judge_tokens=true`;
- `advisory_only=true`;
- `factual_authority=false`;
- `execution_authorized=false`.

Current accepted main at this checkpoint: `6fecbfd937a961dc07df0ecd0d5d6288a294e983`.

## Active execution order

1. Use offline Human-v2 grading only on already-saved ROBERTA outputs when needed for presentation-quality analysis.
2. Feed repeated language defects into deterministic Human-response regressions without granting the evaluator factual authority.
3. Keep live LAB #21/#22 campaigns paused until explicitly resumed.
4. Do not treat open production PRs as accepted because an evaluator identified a historical gap.
5. Preserve zero-token/offline grading as the default quality-analysis path when no new live evidence is required.

## Relationship to current product roadmap

The Evaluation Laboratory is a supporting quality system. ROBERTA Cohort 001 is the current flagship product task. Evaluation work should help explain observed cohort defects, not replace real-user product proof with synthetic or evaluator-only success.

Last reconciled: **2026-09-12 America/New_York**.
