# Human Remediation Reopen Adjudication Gate

Contracts:

- `roberta_human_remediation_reopen_adjudication/v1`
- `roberta_human_remediation_reopen_adjudication_ledger/v1`
- `roberta_human_remediation_reopen_cycle_seed/v1`

This gate handles the case where LAB #73 reports `REOPENED_INCONSISTENCY` for a remediation that was previously proven `RESOLVED` and closed.

## Core rule

A GitHub reopen is **not** evidence that the Human-language defect returned.

The prior resolution and closure evidence remain immutable. The reopen must receive an explicit owner adjudication before any further remediation action is allowed.

Allowed classifications:

1. `ADMINISTRATIVE_NON_QUALITY`
2. `GENUINE_HUMAN_QUALITY_REGRESSION`

## Administrative / non-quality reopen

An administrative classification means the GitHub issue was reopened for bookkeeping, discussion, follow-up, or another reason that does not establish a Human-quality regression.

The gate:

- records the explicit owner decision;
- preserves historical terminal `CLOSED` evidence;
- stores no regression checkpoint evidence;
- sets `new_cycle_eligible=false`;
- does not create a new remediation cycle.

## Genuine Human-quality regression

A genuine regression classification is fail-closed until fresh accepted evidence exists.

The supplied Human checkpoint must:

1. be explicitly accepted in Human checkpoint history;
2. have a sequence strictly greater than the checkpoint that originally resolved the defect;
3. contain the **same targeted failure code**;
4. show `count > 0` and `rate > 0` for that failure code.

A stale checkpoint, a clean newer checkpoint, a missing checkpoint, or a checkpoint that contains a different defect cannot confirm the regression.

When the requirements pass, the gate emits a deterministic `new_cycle_id` and marks the adjudication `new_cycle_eligible=true`.

It still does **not** mutate lifecycle state or create a GitHub issue automatically.

## CLI

Summary:

```bash
roberta-eval-human-reopen summary
```

Summary against an explicit terminal reconciliation report:

```bash
roberta-eval-human-reopen summary \
  --terminal-report /tmp/terminal-reconciliation.json
```

Administrative adjudication:

```bash
roberta-eval-human-reopen adjudicate \
  --terminal-report /tmp/terminal-reconciliation.json \
  --fingerprint <proposal-fingerprint> \
  --owner Bryant \
  --classification ADMINISTRATIVE_NON_QUALITY \
  --approve
```

Confirmed quality regression:

```bash
roberta-eval-human-reopen adjudicate \
  --terminal-report /tmp/terminal-reconciliation.json \
  --fingerprint <proposal-fingerprint> \
  --owner Bryant \
  --classification GENUINE_HUMAN_QUALITY_REGRESSION \
  --checkpoint-id <fresh-accepted-checkpoint> \
  --approve
```

After a genuine regression has been accepted, emit the deterministic seed that a later workflow can use to begin a new remediation cycle:

```bash
roberta-eval-human-reopen cycle-seed \
  --fingerprint <prior-proposal-fingerprint>
```

## Duplicate and conflict behavior

The reopen event identity is bound to:

- prior proposal fingerprint;
- closure evidence key;
- issue identity;
- failure code;
- prior resolved checkpoint;
- observed issue state `open`.

Replaying the exact same adjudication is idempotent. Reusing that reopen event with a different classification, owner/evidence payload, or regression checkpoint fails closed.

## Dashboard

The Evaluation Dashboard exposes:

- pending owner adjudications;
- administrative/non-quality adjudications;
- confirmed Human-quality regressions;
- new-cycle eligibility;
- fresh checkpoint identity for confirmed regressions.

The dashboard remains presentation-only.

## Authority boundary

- explicit owner adjudication is required;
- a GitHub reopen is not regression proof;
- fresh accepted checkpoint evidence is mandatory for genuine regression;
- prior CLOSED/RESOLVED evidence is preserved;
- no issue is opened, closed, or reopened automatically;
- no production code is modified;
- no new remediation lifecycle is created automatically;
- no execution authority is granted;
- LAB #21/#22 live campaigns remain paused.
