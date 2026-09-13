# Human Root-Cause Evidence Acquisition & Correlation Gate

LAB #83 automatically assembles admissible evidence for LAB #81 Human root-cause investigations without converting correlation into causal proof.

Contracts:

- `roberta_human_root_cause_evidence_acquisition/v1`
- `roberta_human_root_cause_source_snapshot/v1`
- `roberta_human_root_cause_source_record/v1`
- `roberta_human_root_cause_correlation/v1`
- `roberta_human_root_cause_evidence_bundle/v1`

## Why this exists

LAB #81 introduced the evidence threshold for naming a Human root cause. Before LAB #83, evidence still had to be assembled manually.

LAB #83 automates the evidence-gathering step across accepted remediation generations while keeping LAB #81 as the only causal authority.

The rule is explicit:

> Correlation can rank suspects. Correlation cannot manufacture causal proof.

## Accepted sources

For each lifecycle generation that contains accepted `FIX_MERGED` evidence, LAB #83 can assemble:

1. lifecycle fix identity: repository, PR number, accepted merge SHA, verifier;
2. read-only GitHub PR metadata when explicitly enabled;
3. PR changed-file metadata;
4. successful GitHub check-run metadata associated with the accepted merge SHA;
5. accepted Human replay/checkpoint outcomes already stored in the remediation lifecycle.

Missing source data stays missing. LAB does not infer a changed file, check result, PR identity, or replay result that is not present in accepted evidence.

## Merge-identity binding

When read-only GitHub acquisition is enabled, the source PR must resolve to the exact repository/PR identity stored in the lifecycle and the observed `merge_commit_sha` must equal the lifecycle's accepted `merge_sha`.

Any mismatch fails closed.

This prevents current GitHub state from silently replacing the evidence identity that originally closed the remediation cycle.

## Six Human domains

Changed artifacts are deterministically mapped to the same six LAB #81 investigation domains:

- `renderer`
- `policy`
- `prompt`
- `service_adapter`
- `vocabulary_replacement`
- `shared_human_layer`

A file may map to more than one domain when its path legitimately crosses layers, for example a shared Human renderer.

## Artifact kinds

LAB #83 distinguishes:

- `IMPLEMENTATION_ARTIFACT`
- `TEST_ARTIFACT`
- `CI_CONFIGURATION`
- `DOCUMENTATION`
- `OTHER_ARTIFACT`

Only implementation-artifact associations are emitted as automatic `SUPPORTS` evidence to LAB #81. Test artifacts are emitted as `NEUTRAL` context evidence. CI, documentation, successful checks, and accepted replays remain contextual provenance rather than causal proof.

## Automatic evidence can never be DIRECT

This is the central safety boundary.

Every LAB #83 evidence item supplied to LAB #81 has:

```text
strength=INDIRECT
```

The acquisition validator rejects any automatically produced `DIRECT` item.

Therefore even if the renderer changes in three separate remediation generations and each change is followed by successful checks and accepted replay, LAB #83 can only increase renderer's correlation/suspicion ranking.

It cannot independently make renderer `CONFIRMED_ROOT_CAUSE`.

LAB #81 still requires:

- at least two `DIRECT` supporting evidence items;
- those direct items must span at least two accepted generations;
- contradictory evidence count must be zero.

## Correlation model

For each of the six domains LAB #83 records:

- implementation-change count;
- implementation generations;
- implementation paths;
- changed test count and generations;
- successful check count associated with fixes that touched the domain;
- accepted `IMPROVED`/`RESOLVED` replay count following those fixes.

The deterministic signal is one of:

- `NO_OBSERVED_ASSOCIATION`
- `TEST_ONLY_ASSOCIATION`
- `SINGLE_GENERATION_ASSOCIATION`
- `REPEATED_CROSS_GENERATION_ASSOCIATION`

A numeric score orders the domains for investigation efficiency only.

Every correlation finding contains:

```text
causal_authority=false
correlation_is_not_causation=true
root_cause_confirmation_authority=LAB_81_ONLY
```

## Read-only GitHub acquisition

Live GitHub reads are opt-in:

```bash
roberta-eval-human-root-cause-acquire snapshot --github
```

The transport performs only GET requests for:

- the accepted pull request;
- changed files;
- check runs on the accepted merge commit.

No issue, PR, branch, file, review, or repository state is mutated.

A token may be supplied through `GITHUB_TOKEN`; public repository reads can operate without one, subject to GitHub rate limits.

Default operation performs zero external calls and uses lifecycle evidence only.

## CLI

Build a source snapshot from accepted lifecycle history only:

```bash
roberta-eval-human-root-cause-acquire snapshot
```

Build a source snapshot with explicit read-only GitHub enrichment:

```bash
roberta-eval-human-root-cause-acquire snapshot --github
```

Build the evidence bundle for one lineage family:

```bash
roberta-eval-human-root-cause-acquire bundle \
  --root-fingerprint <root-fingerprint> \
  --github
```

Show only the correlation report:

```bash
roberta-eval-human-root-cause-acquire correlate \
  --root-fingerprint <root-fingerprint> \
  --github
```

Pass the automatically acquired evidence through LAB #81:

```bash
roberta-eval-human-root-cause-acquire lab81-package \
  --root-fingerprint <root-fingerprint> \
  --github
```

`lab81-package` explicitly fails if automatic correlation evidence somehow crosses LAB #81's causal confirmation threshold. That invariant should be impossible because automatic evidence is `INDIRECT_ONLY`.

## Evidence identity and conflicts

Each source record, changed artifact, check, replay context record, source snapshot, correlation report, and evidence bundle receives a deterministic SHA-256 identity.

Exact duplicates are collapsed where appropriate.

Conflicting reuse of the same source identity fails closed. Examples include:

- a lifecycle PR whose source merge SHA differs from accepted lifecycle evidence;
- the same changed-file source reference appearing with different artifact content;
- a bundle associated with a different lineage report digest.

## Authority boundary

LAB #83:

- may gather accepted source evidence;
- may classify artifacts into Human investigation domains;
- may calculate repeated cross-generation correlations;
- may rank domains for investigation priority;
- may feed `INDIRECT` evidence into LAB #81.

LAB #83 does **not**:

- generate `DIRECT` evidence automatically;
- name a root cause;
- overrule LAB #81;
- create or close GitHub issues;
- modify ROBERTA production code;
- authorize execution;
- resume LAB #21/#22 live campaigns.

`automatic_evidence_acquisition=true`
`automatic_direct_evidence_count=0`
`correlation_is_not_causation=true`
`lab81_confirmation_threshold_preserved=true`
`read_only=true`
`github_issue_mutation=false`
`production_code_mutation=false`
`execution_authorized=false`
