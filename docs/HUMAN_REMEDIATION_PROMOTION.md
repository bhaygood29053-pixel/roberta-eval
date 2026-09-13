# Human ROBERTA v2 remediation promotion gate

This gate converts a review-only Human language remediation proposal into a tracked `bhaygood29053-pixel/roberta-langgraph` issue only after explicit human approval.

## Safety model

Promotion uses two explicit decisions:

1. `--approve` records the reviewer approval and builds an immutable approval receipt.
2. `--create-issue` performs the GitHub issue mutation.

Without `--create-issue`, the command is a dry run. It does not modify GitHub and does not append the promotion ledger.

The promotion ledger is `config/human_remediation_promotion_ledger.json`. It stores the proposal fingerprint, checkpoint evidence key, proposal digest, reviewer approval receipt, and created issue identity. It does not store the full ROBERTA response or the full remediation proposal body.

Duplicate prevention is checked before any GitHub call. A proposal fingerprint or checkpoint-evidence key can map to only one promoted issue. Repeating a successfully promoted proposal returns the existing issue identity rather than creating another issue. Conflicting reuse fails closed.

Promotion itself never edits ROBERTA production code and never authorizes execution. Normal issue review, branch, tests, PR, and merge gates still apply after an issue is created.

## Review first

Generate the latest Human remediation proposal from accepted checkpoints:

```bash
roberta-eval defect-proposals \
  --human-checkpoints \
  --output /tmp/roberta-human-remediation-proposals.jsonl
```

Review and approve it without creating an issue:

```bash
roberta-eval-human-promote \
  --proposals /tmp/roberta-human-remediation-proposals.jsonl \
  --reviewer Bryant \
  --approve \
  --output /tmp/human-promotion-review.json
```

The result should report `APPROVED_DRY_RUN` and `issue_created=false`.

## Create the tracked issue

After approval, explicitly request issue creation. The command uses `GITHUB_TOKEN` by default and sends one issue-create request only after the duplicate ledger check passes:

```bash
export GITHUB_TOKEN=...

roberta-eval-human-promote \
  --proposals /tmp/roberta-human-remediation-proposals.jsonl \
  --reviewer Bryant \
  --approve \
  --create-issue
```

A successful result reports `PROMOTED`, the created issue number/URL, and appends the immutable promotion ledger.

If the same proposal is submitted again, the result is `ALREADY_PROMOTED`; no second issue-create call is made.

## Custom ledger

For experiments or tests, use a separate ledger:

```bash
roberta-eval-human-promote \
  --proposals /tmp/roberta-human-remediation-proposals.jsonl \
  --reviewer Bryant \
  --approve \
  --ledger /tmp/human-remediation-promotion-ledger.json
```

The repository-tracked ledger is intended to preserve accepted promotion history. If the default ledger changes because an issue is promoted locally, checkpoint that ledger change through the normal Git/PR workflow.

## Acceptance boundary

The gate accepts only `human_language_remediation` proposals targeting `bhaygood29053-pixel/roberta-langgraph`. It rejects cluster proposals, alternate repositories, already-promoted proposals, execution-authorized proposals, production-mutation-authorized proposals, and non-deterministic/non-zero-call Human proposals.

The CI promotion gate uses dry-run CLI coverage plus an injected fake GitHub transport. CI never creates real GitHub issues.
