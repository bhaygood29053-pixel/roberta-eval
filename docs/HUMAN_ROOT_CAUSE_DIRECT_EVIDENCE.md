# Human Root-Cause Direct Evidence Qualification & Falsification Gate

## Purpose

LAB #85 converts LAB #83 correlation suspects into deterministic, pre-registered isolation/falsification experiments. It defines when an experiment is strong enough to become LAB #81 `DIRECT` evidence and when it must be rejected, retained as contradiction, or treated as inconclusive.

The authority chain is:

`LAB #83 correlation → LAB #85 isolation/falsification experiment → qualified DIRECT evidence → LAB #81 causal confirmation`

Correlation never becomes causal proof by itself.

## Contracts

- `roberta_human_root_cause_experiment_plan/v1`
- `roberta_human_root_cause_experiment_result/v1`
- `roberta_human_root_cause_experiment_qualification/v1`
- `roberta_human_root_cause_direct_evidence_ledger/v1`
- `roberta_human_root_cause_direct_evidence_bundle/v1`
- `roberta_human_root_cause_direct_confirmation/v1`

## Suspect selection

Experiment plans are generated only for positive LAB #83 domain correlations that have accepted implementation generations. The LAB #83 score determines investigation order only; it has `causal_authority=false`.

## Isolation requirements

Every plan is pre-registered before a result exists and must contain:

- exactly one LAB #81 target domain;
- one accepted remediation generation;
- one fixed corpus SHA-256 shared by control and intervention;
- a minimum of 20 matched cases;
- at least two deterministic replicates;
- an accepted baseline control;
- an isolated ephemeral target-domain correction;
- all five non-target Human domains held artifact-identical;
- proof that the target artifact changed;
- predetermined support, falsification, ambiguity, and non-reproducing-control outcomes;
- no post-hoc outcome editing;
- one final result per plan.

A plan that manipulates multiple domains, lacks a control, lacks a falsification rule, lacks a fixed corpus, or is not tied to an accepted LAB #83 generation fails closed.

## Outcome rules

The targeted defect must first reproduce in the control arm.

### `SUPPORTS_HYPOTHESIS`

The control reproduces one or more targeted failures and the isolated intervention reduces the targeted failure count to zero.

This becomes LAB #81:

- `direction=SUPPORTS`
- `strength=DIRECT`

### `FALSIFIES_HYPOTHESIS`

The control reproduces the targeted failure and the isolated intervention leaves the failure unchanged or worse.

This is retained, never discarded, as:

- `direction=CONTRADICTS`
- `strength=DIRECT`

### `AMBIGUOUS_NO_DIRECT_EVIDENCE`

The intervention improves the count but does not eliminate the targeted defect. This is not promoted to DIRECT evidence.

### `NON_REPRODUCING_CONTROL`

The control does not reproduce the targeted defect. The experiment cannot support or falsify the target-domain hypothesis and emits no DIRECT evidence.

## Artifact isolation proof

A result must prove:

- the target-domain artifact digest changed between control and intervention;
- every non-target domain has the same control and intervention digest;
- the corpus is identical in both arms;
- case counts are matched;
- both runtimes pass;
- deterministic replicates agree.

If any non-target domain changes, the experiment is non-isolating and is rejected.

## One final result per plan

The ledger permits exactly one final result for a pre-registered plan. Re-submitting the exact same result is idempotent. Submitting a different outcome for the same plan fails closed.

This prevents outcome shopping or repeatedly rerunning an experiment until a preferred causal result appears.

## Cross-generation confirmation

One qualified experiment in one generation can never confirm a root cause.

A domain becomes a LAB #81 confirmation candidate only when:

1. qualified `DIRECT SUPPORTS` evidence exists in at least two accepted remediation generations; and
2. there are zero qualified `DIRECT CONTRADICTS` experiments for that domain.

Even then, LAB #85 does not name the root cause. It hands the qualified evidence to LAB #81, which remains the sole causal confirmation authority.

Any contradiction blocks the LAB #85 confirmation-candidate state and LAB #81 sees that contradiction in its evidence set.

## CLI

Generate plans from an accepted LAB #83 bundle:

```bash
roberta-eval-human-root-cause-direct plans \
  --acquisition-bundle /tmp/lab83-bundle.json \
  --corpus-sha256 <64-hex-corpus-digest> \
  --top-n 3 \
  --output /tmp/direct-plans.json
```

Register plans before results exist:

```bash
roberta-eval-human-root-cause-direct register-plans \
  --plans /tmp/direct-plans.json
```

Record one final result:

```bash
roberta-eval-human-root-cause-direct record-result \
  --plan-id <plan-id> \
  --result /tmp/result.json \
  --verified-by Bryant
```

Build the qualified direct-evidence bundle:

```bash
roberta-eval-human-root-cause-direct bundle \
  --acquisition-bundle /tmp/lab83-bundle.json
```

Feed LAB #81:

```bash
roberta-eval-human-root-cause-direct lab81-package \
  --lineage-report /tmp/lineage.json \
  --acquisition-bundle /tmp/lab83-bundle.json
```

Inspect the tracked ledger:

```bash
roberta-eval-human-root-cause-direct summary
```

## Authority boundary

LAB #85 does not execute production changes, mutate GitHub issues, authorize trading/execution, or resume LAB #21/#22. Experiment interventions are defined as ephemeral evaluation variants only.

`direct_evidence_requires_qualified_experiment=true`

`falsification_required=true`

`single_generation_confirmation=false`

`cross_generation_confirmation_required=true`

`lab81_confirmation_authority=true`

`production_code_mutation=false`

`execution_authorized=false`
