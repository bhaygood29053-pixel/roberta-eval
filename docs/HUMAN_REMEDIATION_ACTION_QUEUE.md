# Human Remediation Action Queue and Closure Gate

## Purpose

LAB #69 turns the Human remediation lifecycle into an exact work queue. The queue does not guess what engineering should do next and it does not close GitHub issues. It reads accepted Laboratory evidence and emits one deterministic next action for each tracked Human-language remediation.

## Action contract

`roberta_human_remediation_action_queue/v1` maps evidence to exactly one action:

| Evidence state | Next action |
| --- | --- |
| Proposal registered, no approval receipt | `APPROVE_PROPOSAL` |
| Explicit LAB #65 approval dry-run receipt persisted | `CREATE_ISSUE` |
| Promoted GitHub issue exists, no merged fix recorded | `FIX_ISSUE` |
| Fix merged, no accepted checkpoint newer than verification floor | `ACCEPT_NEW_CHECKPOINT` |
| Fix merged and a newer accepted checkpoint exists | `REPLAY_AGAIN` |
| Replay verified or improved, no still-newer checkpoint exists | `ACCEPT_NEW_CHECKPOINT` |
| Replay verified or improved and a still-newer accepted checkpoint exists | `REPLAY_AGAIN` |
| Lifecycle status `RESOLVED` | `CLOSE_AS_RESOLVED` |

The queue can use the LAB #65 promotion ledger even before LAB #67 lifecycle synchronization, but it fails closed if issue identity or proposal evidence conflicts.

## Persisting approval evidence

LAB #65 intentionally does not write a promotion ledger entry for an approval dry run. LAB #69 therefore adds a separate immutable approval registry:

`config/human_remediation_approval_registry.json`

Persist an approval result created by `roberta-eval-human-promote --approve --output ...`:

```bash
roberta-eval-human-actions \
  --approval-registry config/human_remediation_approval_registry.json \
  record-approval \
  --result /tmp/human-promotion-approval.json
```

Only `APPROVED_DRY_RUN` results are accepted. A result that already created an issue is rejected because created-issue authority belongs to the promotion ledger.

The registry stores approval identity, proposal SHA-256, checkpoint IDs, failure code, reviewer identity, and the promotion evidence key. It does not store raw ROBERTA responses or proposal bodies.

## Queue

```bash
roberta-eval-human-actions queue
```

The output includes:

- lifecycle status;
- effective evidence stage;
- exact next action and plain-language label;
- GitHub issue identity when one exists;
- latest accepted checkpoint sequence;
- latest replay-verification sequence;
- closure readiness;
- zero-call / no-execution boundary fields.

## Closure gate

Check one remediation by proposal fingerprint:

```bash
roberta-eval-human-actions closure-check \
  --fingerprint <proposal-fingerprint>
```

The closure gate returns `READY_TO_CLOSE` only when both are true:

1. lifecycle status is exactly `RESOLVED`; and
2. a promoted GitHub issue identity exists.

Every other state returns `BLOCKED` with explicit blockers and the next required action.

`FIX_MERGED`, `REPLAY_VERIFIED`, and `IMPROVED` are never closure proof. A remediation becomes `RESOLVED` only through LAB #67 replay verification using a later explicitly accepted Human checkpoint with zero occurrences of the targeted failure code.

## Dashboard

The Evaluation Dashboard now shows:

- action counts;
- closure-ready issue count;
- exact next action for each tracked remediation;
- effective stage and GitHub issue number;
- a fail-closed closure policy reminder.

## Authority boundary

The action queue and closure gate are deterministic and read-only:

- `judge_model_calls=0`;
- `external_calls=0` for queue and closure analysis;
- `auto_close_issue=false`;
- `production_code_mutation=false`;
- `execution_authorized=false`.

The queue does not create issues, merge fixes, accept checkpoints, replay ROBERTA, or close GitHub issues. Those actions remain explicit operations in their existing authoritative workflows.
