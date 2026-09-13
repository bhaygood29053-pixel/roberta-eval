# Human Remediation Closure Promotion Gate

Contract: `roberta_human_remediation_closure_ledger/v1`

CLI: `roberta-eval-human-close`

This gate is the final control between a LAB-proven Human remediation resolution and changing the state of the corresponding `roberta-langgraph` GitHub issue.

## Required evidence

Closure is eligible only when all of the following are already true:

1. LAB #67 lifecycle status is exactly `RESOLVED`.
2. LAB #69 closure gate returns `READY_TO_CLOSE` and `CLOSE_AS_RESOLVED`.
3. A promoted `roberta-langgraph` issue identity exists and agrees across lifecycle and promotion evidence.
4. The latest lifecycle replay verification outcome is `RESOLVED`.
5. The resolved checkpoint is an explicitly accepted Human checkpoint.
6. The targeted failure count and normalized failure rate are both zero in that accepted checkpoint.

A merged fix, an `IMPROVED` result, or a `REPLAY_VERIFIED` result is insufficient.

## Double opt-in

Approval alone is a dry run:

```bash
roberta-eval-human-close \
  --fingerprint <proposal-fingerprint> \
  --reviewer Bryant \
  --approve
```

The command validates and freezes closure evidence but does not change GitHub.

Closing the issue additionally requires `--close-issue`:

```bash
roberta-eval-human-close \
  --fingerprint <proposal-fingerprint> \
  --reviewer Bryant \
  --approve \
  --close-issue
```

The GitHub token is read from `GITHUB_TOKEN` by default. A different environment variable can be selected with `--github-token-env`.

## Immutable closure evidence

The closure approval binds:

- proposal fingerprint and proposal digest;
- exact GitHub repository, issue number, and issue URL;
- failure code;
- resolved checkpoint ID and accepted checkpoint sequence;
- zero targeted failure count/rate;
- SHA-256 of the resolved verification record;
- reviewer identity;
- deterministic closure evidence key;
- `READY_TO_CLOSE` gate state.

The closure ledger is written only after GitHub returns the expected issue identity with state `closed`.

## Duplicate and failure behavior

- repeated closure of the same accepted evidence returns `ALREADY_CLOSED` and makes no second GitHub mutation;
- reuse of a proposal fingerprint, issue identity, or closure evidence key with conflicting evidence fails closed;
- GitHub errors or unexpected response state leave the closure ledger unchanged;
- missing explicit approval fails before any GitHub call;
- premature lifecycle state fails before any GitHub call.

## Authority boundary

Closing a remediation issue changes only GitHub issue state. It does not modify ROBERTA production code, modify CMIS/Scout evidence, authorize execution, or certify unrelated Human behavior.

The gate is deterministic and uses no AI judge. CI tests use an injected fake GitHub close transport and never close a real issue.

LAB #21/#22 live campaigns remain paused unless explicitly resumed by the owner.
