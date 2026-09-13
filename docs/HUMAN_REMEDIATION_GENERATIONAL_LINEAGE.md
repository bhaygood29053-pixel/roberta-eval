# Human Remediation Generational Lineage Reconciliation

LAB #79 turns reopened Human-language remediation cycles into an auditable generational lineage.

Contracts:

- `roberta_human_remediation_generational_lineage_reconciliation/v1`
- `roberta_human_remediation_lineage_health/v1`

## Why this exists

A remediation can be correctly fixed, replay-verified, resolved and closed, then later recur. LAB #75 proves recurrence. LAB #77 can instantiate a child remediation. Without a lineage reconciler, repeated cycles can look like independent successes even when the same observable Human-language defect keeps returning.

LAB #79 answers a different question:

> Are we eliminating this defect, or repeatedly fixing the same symptom across generations?

The answer is pattern evidence, not causal proof.

## Source authority

LAB #79 consumes only:

1. the accepted Human remediation lifecycle; and
2. the LAB #77 reopen-cycle promotion ledger.

It does not infer lineage from issue titles, timestamps or similarity.

## Generation model

- original remediation root: generation `0`;
- first accepted reopened child: generation `1`;
- child of that child: generation `2`;
- and so on.

Generation is derived from the parent links. It is not trusted from a manually supplied integer. If a lifecycle record carries a stored `generation`, it must equal the derived generation or reconciliation fails closed.

## Integrity gates

Every LAB #77 child must have exactly one promotion edge and one existing parent lifecycle.

The reconciler rejects:

- missing parent lifecycle;
- missing child lifecycle;
- self-parenting;
- cycles;
- duplicate promotion evidence for a child;
- conflicting parentage;
- child lifecycle identity mismatch;
- child proposal digest mismatch;
- lineage evidence mismatch;
- failure-code drift across a family;
- service drift across a family;
- non-`RECURRENT` reopened children;
- stored generation that disagrees with the derived generation.

The tree is therefore evidence-bound rather than label-bound.

## Lineage health policy

The deepest accepted generation determines family health:

| Deepest generation | Health | Meaning |
|---:|---|---|
| 0 | `STABLE_ROOT` | No accepted recurrence cycle exists. |
| 1 | `RECURRENCE_OBSERVED` | The defect returned once after a prior resolution. |
| 2 | `ROOT_CAUSE_WARNING` | The same defect has required remediation across two repeat regressions. Treat this as evidence of a remediation-loop/root-cause risk. |
| 3+ | `CHRONIC_REGRESSION` | The defect continues recurring across three or more repeat regression generations. |

`ROOT_CAUSE_WARNING` and `CHRONIC_REGRESSION` do **not** prove what the underlying causal root cause is. They prove that accepted evidence shows the same failure/service family repeatedly returned after prior remediation cycles.

## Report output

`roberta-eval-human-lineage report` emits:

- family count;
- lineage node count;
- reopen edge count;
- deepest generation;
- repeat-regression family count;
- root-cause-warning family count;
- chronic family count;
- health counts;
- each family root;
- failure code and service;
- repeat-regression count;
- every node with generation, status and parent;
- complete root → leaf paths;
- deterministic report SHA-256.

Example:

```bash
roberta-eval-human-lineage report
```

Validation mode:

```bash
roberta-eval-human-lineage validate
```

Custom inputs:

```bash
roberta-eval-human-lineage \
  --lifecycle /tmp/human-remediation-lifecycle.json \
  --reopen-cycle-ledger /tmp/reopen-cycle-promotions.json \
  validate
```

## Root-cause visibility

The practical product signal is `repeat_regression_count` plus `health`.

A generation-2 family is no longer presented as just another reopened defect. LAB explicitly raises `ROOT_CAUSE_WARNING` so engineering can investigate whether the renderer, policy, prompt boundary, service adapter, vocabulary replacement or another shared layer is allowing the same defect to return.

A generation-3+ family becomes `CHRONIC_REGRESSION` and should be treated as a stronger signal that local symptom fixes are not producing durable elimination.

## Authority boundary

LAB #79 is read-only.

It does not:

- create or reopen GitHub issues;
- create child cycles;
- modify lifecycle records;
- change ROBERTA production code;
- close remediations;
- authorize execution;
- identify a causal root cause automatically.

It only reconciles already accepted remediation evidence and exposes recurrence structure.

LAB #21/#22 live campaigns remain paused.

`read_only=true`
`acyclic_lineage_required=true`
`generation_integrity_required=true`
`advisory_pattern_interpretation=true`
`automatic_issue_creation=false`
`lifecycle_mutation=false`
`production_code_mutation=false`
`execution_authorized=false`
