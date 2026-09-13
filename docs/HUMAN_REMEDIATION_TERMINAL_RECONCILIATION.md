# Human Remediation Terminal Closure Reconciliation

Contract: `roberta_human_remediation_terminal_reconciliation/v1`

This layer reconciles accepted Human remediation closure evidence with the action queue and dashboard without changing the underlying lifecycle or closure evidence.

## Terminal rule

A remediation becomes terminal `CLOSED` only when:

1. LAB #67 lifecycle status is `RESOLVED`;
2. LAB #71 closure ledger contains the matching proposal fingerprint;
3. proposal digest, issue identity, failure code and resolved checkpoint evidence match;
4. the resolved replay evidence still shows zero occurrences and zero rate for the targeted Human-language defect.

`CLOSED` is a terminal presentation/reconciliation state. It does not rewrite lifecycle `RESOLVED`.

## Action queue behavior

Terminal `CLOSED` records are removed from the active Human remediation action queue. They remain visible in the terminal evidence list with:

- proposal fingerprint;
- issue number and URL;
- closure evidence key;
- reviewer identity;
- failure code/service;
- resolved checkpoint ID and sequence;
- zero targeted failure evidence;
- resolved verification SHA-256.

The action queue therefore represents only work that still requires an owner action.

## GitHub reconciliation

Default summary/queue operations are offline and make no external calls.

An explicit state check is available:

```bash
roberta-eval-human-terminal reconcile --check-github
```

`GITHUB_TOKEN` is required only for that explicit check. The operation is read-only and performs a GET for each terminal issue.

Results:

- `CONSISTENT_CLOSED` — GitHub still reports the issue closed;
- `REOPENED_INCONSISTENCY` — GitHub now reports the issue open;
- `NOT_CHECKED` — no live issue-state reconciliation was requested.

A reopened issue does **not** erase accepted replay proof, closure approval, closure evidence, or the historical terminal CLOSED event. It is reported as an inconsistency requiring owner review.

## Dashboard

The Evaluation Dashboard shows:

- tracked remediations;
- active remediations;
- terminal CLOSED count;
- reopened inconsistency count;
- exact active actions;
- terminal closure evidence summaries.

The dashboard remains presentation-only.

## Authority boundary

- reconciliation is read-only;
- no issue is closed or reopened automatically;
- no production code is modified;
- no evidence is rewritten;
- no execution authority is granted;
- LAB #21/#22 live campaigns remain paused.
