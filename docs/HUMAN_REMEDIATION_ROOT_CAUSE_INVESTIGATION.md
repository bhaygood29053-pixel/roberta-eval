# Human Remediation Root-Cause Investigation Gate

LAB #81 activates when LAB #79 reports a Human remediation family as `ROOT_CAUSE_WARNING` or `CHRONIC_REGRESSION`.

Contracts:

- `roberta_human_remediation_root_cause_investigation/v1`
- `roberta_human_remediation_root_cause_evidence/v1`
- `roberta_human_remediation_root_cause_finding/v1`
- `roberta_human_remediation_root_cause_ledger/v1`
- `roberta_human_remediation_root_cause_disposition/v1`
- `roberta_human_remediation_root_cause_sufficiency_gate/v1`

## Why this exists

A repeated Human-language defect can pass a local fix and replay, then recur again in a later accepted checkpoint. At generation 2 or later, another clean replay is no longer treated as sufficient evidence that the underlying engineering problem has been durably eliminated.

LAB #81 forces a separate question:

> What shared Human-facing layer is allowing this defect to recur, and what evidence supports that conclusion?

The investigation may rank likely domains, but it cannot name a root cause without evidence.

## Investigation domains

Every package covers exactly six domains:

1. `renderer`
2. `policy`
3. `prompt`
4. `service_adapter`
5. `vocabulary_replacement`
6. `shared_human_layer`

Missing evidence remains unknown. The gate never treats absence of evidence as proof.

## Evidence model

Evidence is explicit and source-identified. Each item records:

- domain;
- accepted remediation generation;
- direction: `SUPPORTS`, `CONTRADICTS`, or `NEUTRAL`;
- strength: `DIRECT` or `INDIRECT`;
- source reference;
- optional artifact SHA-256;
- human-readable statement;
- deterministic evidence ID.

Evidence generation must exist in the accepted lineage family.

## Root-cause confirmation threshold

A domain becomes `CONFIRMED_ROOT_CAUSE` only when all of the following are true:

- at least two `DIRECT` supporting evidence items exist;
- support spans at least two accepted remediation generations;
- contradictory evidence count is zero.

Otherwise the domain is one of:

- `SUSPECTED`
- `INCONCLUSIVE`
- `RULED_OUT`

This is intentionally conservative. A repeated symptom by itself is not a causal claim.

## Deterministic ranking

Domains are ranked from explicit evidence using:

- direct support;
- indirect support;
- number of generations carrying support;
- direct contradiction;
- indirect contradiction.

The ranking is deterministic and tie-broken by the fixed domain order. Ranking means investigation priority, not proof.

## Investigation package

For a warning/chronic family the package freezes:

- LAB #79 lineage report identity;
- family SHA-256;
- root remediation fingerprint;
- failure code and service;
- deepest generation and repeat-regression count;
- complete lineage paths and nodes;
- normalized evidence;
- six ranked findings;
- confirmed root-cause domains, if any;
- suspected domains;
- evidence gaps;
- required findings that must be addressed before sufficiency can pass;
- deterministic package ID and digest.

## Owner disposition

Registration does not mean the investigation is addressed.

An explicit owner disposition is required.

Two accepted modes exist:

### `CONFIRMED_ROOT_CAUSE_ADDRESSED`

Use only when the package actually contains one or more confirmed root-cause domains. Every confirmed domain must be included in `addressed_domains`, and external evidence references for the remediation must be supplied.

### `LEADING_FINDINGS_ADDRESSED`

Use when the investigation has evidence-backed suspected findings but does not meet the confirmation threshold. All required leading findings must be covered, evidence references must be supplied, and the rationale must explicitly avoid claiming an unproven causal root cause.

An entirely inconclusive package with no evidence-backed leading finding cannot be marked addressed.

## Sufficiency rule

For `STABLE_ROOT` and `RECURRENCE_OBSERVED`, LAB #81 is not required.

For `ROOT_CAUSE_WARNING` and `CHRONIC_REGRESSION`:

1. no current package → `BLOCKED_INVESTIGATION_REQUIRED`;
2. package exists but no approved disposition → `BLOCKED_FINDINGS_UNADDRESSED`;
3. current package plus approved evidence-backed disposition → `ROOT_CAUSE_FINDINGS_ADDRESSED`.

For generation 2+:

- `ordinary_symptom_fix_sufficient=false`
- `replay_success_alone_sufficient=false`

A clean replay can still prove that the current symptom disappeared. It cannot, by itself, satisfy the root-cause investigation gate.

## CLI

Create a package without persisting it:

```bash
roberta-eval-human-root-cause package \
  --root-fingerprint <root> \
  --evidence evidence.jsonl
```

Register the current package:

```bash
roberta-eval-human-root-cause register \
  --root-fingerprint <root> \
  --evidence evidence.jsonl
```

Address a confirmed root cause:

```bash
roberta-eval-human-root-cause address \
  --package-id <package-id> \
  --owner Bryant \
  --mode CONFIRMED_ROOT_CAUSE_ADDRESSED \
  --domain renderer \
  --evidence-ref PR#123 \
  --evidence-ref test::renderer-regression \
  --rationale "The confirmed renderer path was corrected and regression-tested." \
  --approve
```

Check whether a remediation is sufficient under LAB #81:

```bash
roberta-eval-human-root-cause sufficiency --fingerprint <proposal-fingerprint>
```

## Authority boundary

LAB #81 persists evaluation evidence and owner dispositions only.

It does not:

- identify a causal root cause without evidence;
- create or close GitHub issues;
- modify ROBERTA production code;
- execute trades or other production actions;
- resume LAB #21/#22 live evaluation campaigns.

`root_cause_claims_require_evidence=true`
`generation_2_plus_investigation_required=true`
`symptom_fix_alone_sufficient=false`
`replay_success_alone_sufficient=false`
`automatic_issue_creation=false`
`production_code_mutation=false`
`execution_authorized=false`
