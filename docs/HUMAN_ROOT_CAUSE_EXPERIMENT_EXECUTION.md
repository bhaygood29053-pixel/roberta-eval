# Human Root-Cause Controlled Experiment Execution & Reproducibility Gate

LAB #87 executes LAB #85 pre-registered Human root-cause experiment plans without changing their definitions or interpreting their outcomes.

## Authority boundary

The execution harness is an observation layer only.

It may:
- build ephemeral control and intervention environment manifests;
- verify runtime and Human-domain artifact digests;
- execute the exact same ordered corpus in both arms;
- execute the pre-registered deterministic replicate count;
- count targeted Human failures;
- prove case/order/artifact/replicate consistency;
- create immutable execution receipts;
- convert a receipt into LAB #85's existing `result_input` contract.

It may not:
- change the target Human domain;
- change the accepted generation;
- change the corpus digest;
- change minimum case or replicate counts;
- change held-constant Human domains;
- change pre-registered outcome rules;
- label an observation SUPPORTS, FALSIFIES, or ambiguous;
- emit DIRECT evidence;
- name a root cause;
- mutate production code or GitHub issues;
- resume LAB #21/#22 live campaigns.

LAB #85 remains the only layer that converts a qualified controlled-experiment observation into `DIRECT SUPPORTS`, `DIRECT CONTRADICTS`, or no DIRECT evidence. LAB #81 remains the only layer that may name `CONFIRMED_ROOT_CAUSE`.

## Contracts

- `roberta_human_root_cause_execution_environment/v1`
- `roberta_human_root_cause_execution_manifest/v1`
- `roberta_human_root_cause_replicate_receipt/v1`
- `roberta_human_root_cause_execution_receipt/v1`
- `roberta_human_root_cause_reproducibility/v1`
- `roberta_human_root_cause_execution_ledger/v1`

## Frozen experiment definition

Before execution the manifest binds:
- LAB #85 plan ID and full plan digest;
- evidence-bundle and family identity;
- target domain and accepted generation;
- fixed corpus SHA-256;
- ordered case IDs and input digests;
- minimum matched-case count;
- deterministic replicate count;
- manipulated and held-constant Human domains;
- pre-registered outcome rules.

Any later change to those values invalidates the manifest/receipt path.

## Environment verification

Control and intervention receive separate ephemeral environment identities. Each environment records a runtime SHA-256 and a digest for all six Human domains:

- renderer
- policy
- prompt
- service_adapter
- vocabulary_replacement
- shared_human_layer

The target-domain digest must differ between control and intervention. Every held-constant domain digest must be exactly identical.

## Corpus and replicate reproducibility

Both arms run the exact same ordered corpus. Every replicate uses the same control/intervention corpus and a deterministic seed derived from:

`plan_id : corpus_sha256 : replicate_index`

A replicate fails closed if it changes case order, case identity, input digest, environment identity, runtime status, or deterministic seed.

For DIRECT-evidence eligibility downstream, repeated runs must produce identical targeted-failure identities and output digests for each arm. Inconsistent replicates are rejected before LAB #85 is called.

## Execution receipt

A receipt contains observed facts only:
- control/intervention environment identities;
- ordered replicate receipts;
- targeted failure counts and case IDs;
- output digests;
- reproducibility evidence;
- performer identity;
- immutable receipt SHA-256.

The receipt intentionally contains no `outcome`, causal direction, DIRECT-evidence label, or root-cause claim.

## LAB #85 handoff

`receipt_to_lab85_result_input()` converts the accepted receipt into the already-accepted LAB #85 result-input shape. `qualify_receipt_with_lab85()` delegates to LAB #85 unchanged. `submit_receipt_to_lab85()` delegates to the existing LAB #85 one-final-result-per-plan ledger.

This preserves the authority chain:

`LAB #83 correlation → LAB #85 pre-registered plan → LAB #87 execution receipt → LAB #85 qualification/falsification → LAB #81 causal confirmation`

## Execution ledger

The tracked execution ledger starts empty. One plan may have one immutable execution receipt. Exact replay is idempotent; a different receipt for the same frozen plan fails closed.

`production_code_mutation=false`

`github_issue_mutation=false`

`runner_outcome_authority=false`

`lab85_qualification_authority=true`

`execution_authorized=false`
