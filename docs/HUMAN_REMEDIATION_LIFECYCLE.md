# Human ROBERTA v2 Remediation Lifecycle

## Purpose

The Evaluation Laboratory tracks a confirmed Human-language problem from detection through verified improvement without treating engineering activity as proof of product quality.

The lifecycle is:

`DETECTED → PROPOSED → APPROVED → GITHUB_ISSUE → FIX_MERGED → REPLAY_VERIFIED → IMPROVED / RESOLVED`

A GitHub issue, pull request, or merged fix is not enough to mark a Human defect resolved.

## Persistent contract

The tracked store is `config/human_remediation_lifecycle.json` using `roberta_human_remediation_lifecycle/v1`.

It stores only remediation metadata, checkpoint identifiers, normalized defect metrics, issue/fix identities, and verification evidence. It does not store raw ROBERTA replies or full proposal bodies.

## Register a generated proposal

```bash
roberta-eval-human-lifecycle register \
  --proposals /tmp/roberta-human-remediation-proposals.jsonl
```

Registration records deterministic `DETECTED` and `PROPOSED` events. Re-registering the identical proposal is idempotent; conflicting content under the same proposal fingerprint fails closed.

## Synchronize an approved GitHub promotion

After LAB #65 has created and recorded the remediation issue:

```bash
roberta-eval-human-lifecycle sync-promotion
```

The lifecycle consumes the accepted promotion ledger and records `APPROVED` and `GITHUB_ISSUE`. It does not create another issue.

## Record a merged fix

A merged remediation PR must be explicitly recorded with its actual repository, PR number, merge SHA, and verifier:

```bash
roberta-eval-human-lifecycle record-fix \
  --fingerprint <proposal-fingerprint> \
  --pr-number 123 \
  --merge-sha <40-character-merge-sha> \
  --verified-by Bryant
```

At that moment the tracker freezes the current accepted Human-checkpoint sequence. That sequence becomes the verification floor.

`FIX_MERGED` is an engineering milestone only. It is never treated as `IMPROVED` or `RESOLVED` by itself.

## Verify with a later accepted checkpoint

After a new Human corpus is explicitly accepted as a checkpoint:

```bash
roberta-eval-human-lifecycle verify-replay \
  --fingerprint <proposal-fingerprint>
```

The verification checkpoint must have been accepted after the fix's frozen checkpoint floor.

For the exact failure code that caused the remediation:

- zero current occurrences → `RESOLVED`;
- non-zero occurrences with a lower normalized rate than the proposal baseline → `IMPROVED`;
- otherwise → `REPLAY_VERIFIED` and the defect remains open.

A later accepted checkpoint can advance an `IMPROVED` or `REPLAY_VERIFIED` remediation to `RESOLVED`.

## Summary

```bash
roberta-eval-human-lifecycle summary
```

The Evaluation Dashboard also reads the lifecycle ledger and displays tracked, active, replay-verified, improved, and resolved remediation counts plus active defect stages.

## Authority boundary

Lifecycle evaluation is deterministic and zero-judge-token. It does not call a model, provider, RPC, or HTTP service. It does not modify ROBERTA production code, merge a PR, create evidence, or authorize execution. GitHub merge evidence is recorded explicitly; Human-quality closure requires a later accepted checkpoint.
