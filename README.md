# ROBERTA Evaluation Laboratory

`roberta-eval` is the independent evaluation and stress-testing laboratory for ROBERTA.

Its purpose is to generate and run large, diverse test suites across ROBERTA capabilities, compare answers against available evidence and deterministic expectations, discover defects and recurring behavioral patterns, preserve regressions, and measure whether ROBERTA is actually improving over time.

## Core rule

The Laboratory evaluates ROBERTA; it does not silently change ROBERTA, Scout, CMIS, or provider evidence to make tests pass.

## Initial milestones

1. Repository foundation and Laboratory contract
2. ROBERTA capability registry
3. Question taxonomy
4. Deterministic evaluation corpus
5. Question generation
6. Live ROBERTA runtime test harness
7. Evidence fidelity grading
8. Failure classification, clustering, and trend analysis
9. Permanent regression memory
10. Release qualification

See `ROADMAP.md`, `ARCHITECTURE.md`, and `LAB_CONTRACT.md` as the project develops.

## Zero-token Human ROBERTA v2 grading

Human-language grading is deterministic by default and does **not** require DeepSeek or another LLM judge.

The existing `quality` command now runs the Human ROBERTA v2 language gate over saved `roberta_eval_run_record/v1` JSONL records. It checks Quick/Normal responses for internal engineering language, report-style status dumps, meaning-after-jargon, and execution-authority leakage. Deep Dive remains the explicit technical surface.

Grade an already-captured run without making another ROBERTA or model call:

```bash
roberta-eval quality \
  --input /tmp/roberta-live-run.jsonl \
  --output /tmp/roberta-human-quality.jsonl
```

The summary includes:

- `human_v2.verdict_counts.PASS`
- `human_v2.verdict_counts.LANGUAGE_DEFECT`
- `ai_judge_used=false`
- `judge_model_calls=0`
- `zero_judge_tokens=true`

This grader never rewrites the saved reply, facts, recommendations, evidence, or execution state. It hashes and returns the original reply for traceability. An AI semantic judge remains an optional future advisory signal only and is disabled by default in `config/lab.toml`.

A low-token workflow is therefore:

1. run a small live ROBERTA sample once;
2. save the JSONL responses;
3. run `roberta-eval quality` repeatedly offline as rules and regressions improve;
4. use the deterministic fixture/generator/stress suites for large-volume testing without model calls;
5. use an AI judge only if deliberately enabled for a difficult subjective review.

## Live evidence-backed evaluation

Synthetic fixture cases and live ROBERTA cases are intentionally separate.

Use a balanced deterministic smoke run when you want broad fixture coverage:

```bash
roberta-eval run --mode fixture --limit 20 --selection balanced
```

Materialize the first real-subject X1 live plan:

```bash
roberta-eval live-plan --limit 20 --write /tmp/roberta-live-plan.jsonl
```

Run it against the local ROBERTA bridge:

```bash
roberta-eval live-run \
  --target http://127.0.0.1:8766 \
  --limit 20 \
  --run-id live-smoke-001 \
  --output /tmp/roberta-live-run.jsonl
```

Then grade only the structured live evidence telemetry:

```bash
roberta-eval live-grade \
  --input /tmp/roberta-live-run.jsonl \
  --output /tmp/roberta-live-grades.jsonl
```

Turn those grades into the LAB #22 remediation map:

```bash
roberta-eval live-diagnose \
  --input /tmp/roberta-live-grades.jsonl \
  --json /tmp/roberta-live-diagnostics.json \
  --markdown /tmp/roberta-live-diagnostics.md
```

LAB #22 keeps `EVIDENCE_REQUIRED` separate from a factual ROBERTA failure and
prioritizes runtime, telemetry, canonical-claim, evidence-metadata, Claim
Integrity, claim/evidence, and execution-boundary remediation deterministically.

Current checkpoint: `live-smoke-004` completed with 20/20 runtime OK, 8 PASS, 12 EVIDENCE_REQUIRED, and 0 FAIL. The owner has paused all active Evaluation Laboratory work. No LAB #21/#22 runs, `live-smoke-005`, new evaluation campaigns, grading/diagnostics, trend analysis, or eval-driven regression promotion should run until explicitly resumed. Protected `roberta-core` #89 / PR #90 is not an active eval gate while this pause is in effect. LAB #53 is a bounded tooling/setup change and does not by itself resume those paused live campaigns.

A human-only ROBERTA response without the LAB #21 telemetry contract is `EVIDENCE_REQUIRED`, not a fabricated PASS or FAIL. Live mode never uses the synthetic fixture answer key.

A LAB #21 `PASS` is deliberately bounded: it proves the selected canonical structured claims match the captured accepted evidence and the final response carries `roberta_claim_integrity/v1` PASS. It does **not** certify upstream provider truth or every natural-language sentence, so `live_roberta_qualified` remains false in v1.
