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

A human-only ROBERTA response without the LAB #21 telemetry contract is `EVIDENCE_REQUIRED`, not a fabricated PASS or FAIL. Live mode never uses the synthetic fixture answer key.

A LAB #21 `PASS` is deliberately bounded: it proves the selected canonical structured claims match the captured accepted evidence and the final response carries `roberta_claim_integrity/v1` PASS. It does **not** certify upstream provider truth or every natural-language sentence, so `live_roberta_qualified` remains false in v1.
