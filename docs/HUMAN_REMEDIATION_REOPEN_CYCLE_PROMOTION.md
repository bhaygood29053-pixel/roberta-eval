# Human Remediation Reopen Cycle Promotion Gate

Contracts:

- `roberta_human_remediation_reopen_cycle_promotion/v1`
- `roberta_human_remediation_reopen_cycle_promotion_ledger/v1`
- `roberta_human_remediation_reopen_cycle_promotion_result/v1`

This gate converts a LAB #75 confirmed Human-quality regression into a new remediation lifecycle **only after explicit owner approval**.

## Why this gate exists

LAB #73 can detect that a previously closed GitHub issue was reopened. LAB #75 then requires an explicit owner adjudication and fresh accepted checkpoint evidence before classifying that reopen as a genuine Human-quality regression.

Even after LAB #75 confirms regression, its `new_cycle_eligible` seed is still evidence only. It does not create a remediation lifecycle automatically.

LAB #77 is the explicit boundary that may instantiate the child remediation.

## Required chain

```text
Prior remediation RESOLVED
→ issue CLOSED
→ REOPENED_INCONSISTENCY
→ owner adjudicates GENUINE_HUMAN_QUALITY_REGRESSION
→ fresh accepted checkpoint proves same defect returned
→ LAB #75 new_cycle_eligible seed
→ owner explicitly approves LAB #77 promotion
→ child remediation DETECTED → PROPOSED
```

The child then follows the normal existing pipeline:

```text
Approve proposal
→ Create issue
→ Fix issue
→ Accept new checkpoint
→ Replay
→ Improve / Resolve
→ Close
```

LAB #77 does not bypass any later gate.

## Parent CLOSED evidence

Promotion requires all of the following to still agree:

- LAB #75 adjudication is `GENUINE_HUMAN_QUALITY_REGRESSION`;
- `new_cycle_eligible=true`;
- parent lifecycle still has status `RESOLVED`;
- parent issue identity matches the seed;
- LAB #71 closure ledger contains the same parent proposal fingerprint;
- closure evidence key matches;
- closure ledger still records the accepted issue closure;
- prior resolved checkpoint identity matches the seed.

An administrative/non-quality reopen cannot enter this gate.

## Parent → child lineage

Every child lifecycle stores immutable lineage containing:

- parent proposal fingerprint;
- parent lifecycle ID;
- child proposal fingerprint;
- child lifecycle ID;
- LAB #75 `new_cycle_id`;
- closure evidence key;
- reopen event key;
- parent issue number and URL;
- failure code and service;
- prior resolved checkpoint ID/sequence;
- fresh recurrence checkpoint ID/sequence/corpus SHA-256;
- targeted failure count/rate;
- LAB #75 adjudicator;
- LAB #75 adjudication SHA-256;
- LAB #77 cycle promoter.

The original parent remains `RESOLVED`; it is never rewritten into the child cycle.

## Deterministic child identity

The child proposal fingerprint is deterministically derived from the accepted LAB #75 seed. It does **not** depend on who promotes it.

This means the same regression seed cannot produce two child lifecycles simply because two people attempt promotion. The promotion ledger independently binds the explicit promoter identity, so a later attempt with conflicting owner/evidence fails closed rather than producing another child.

## Canonical child proposal

The child lifecycle is deliberately created as a normal `human_language_remediation` proposal with status `PROPOSED`.

The canonical proposal can be regenerated later:

```bash
roberta-eval-human-reopen-cycle proposal \
  --child-fingerprint <child-fingerprint>
```

That lets the existing Human remediation approval and issue-promotion gates operate on the exact proposal digest already stored in the child lifecycle.

## Promote

```bash
roberta-eval-human-reopen-cycle promote \
  --parent-fingerprint <prior-closed-fingerprint> \
  --owner Bryant \
  --approve
```

`--approve` is mandatory. Promotion updates only LAB remediation state and the LAB #77 promotion ledger.

It does not create or reopen a GitHub issue and does not modify ROBERTA production code.

## Summary

```bash
roberta-eval-human-reopen-cycle summary
```

The summary exposes the parent→child remediation graph, child status, reopened-cycle counts, regression checkpoint, and promoter identity.

## Duplicate / recovery behavior

- Exact duplicate promotion is idempotent.
- The same LAB #75 `new_cycle_id`, reopen event, or child fingerprint cannot create a second child.
- Conflicting promoter or evidence reuse fails closed.
- If lifecycle persistence succeeds but promotion-ledger persistence is interrupted, a retry recognizes the deterministic existing child and can append the missing promotion ledger entry without creating another child.

## Authority boundary

- explicit owner approval is required;
- parent CLOSED evidence is required;
- administrative reopen cannot be promoted;
- no automatic GitHub issue creation;
- no automatic issue reopening;
- no production-code mutation;
- no execution authority;
- LAB #21/#22 live campaigns remain paused.
