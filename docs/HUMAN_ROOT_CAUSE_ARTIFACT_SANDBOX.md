# Human Root-Cause Artifact Materialization & Sandbox Gate

LAB #89 connects the accepted ROBERTA public Human renderer to the controlled experiment chain without touching the production runtime.

## Authority chain

`accepted roberta-langgraph commit → materialized control artifact → target-domain-only candidate overlay → offline sandbox → LAB #87 observations receipt → LAB #85 qualification/falsification → LAB #81 root-cause authority`

LAB #89 never decides whether an experiment supports or falsifies a causal hypothesis.

## Accepted control source

The tracked source pin is `config/human_root_cause_artifact_source.json`.

It binds to:

- repository: `bhaygood29053-pixel/roberta-langgraph`;
- immutable accepted commit SHA;
- public Human renderer entrypoint `roberta.human_response_renderer:render_human_response`;
- a fixed public-shell file allowlist;
- one owner Human domain per materialized file.

The public shell intentionally does not materialize protected recommendation/opinion source. Those domains may be represented by an explicit empty-domain digest. The sandbox materializes only the public deterministic Human surface needed for the bounded experiment.

`roberta/__init__.py` is deliberately not materialized. The sandbox therefore imports `roberta` as a namespace package and loads the public renderer/contract directly instead of booting the broader ROBERTA graph or protected core.

## Materialization

The control tree is read from the pinned commit through a read-only `ArtifactSource` and written to an ephemeral directory. LAB records:

- each allowlisted path;
- its byte SHA-256 and size;
- its single owner domain;
- each Human-domain digest;
- the whole artifact-tree digest;
- the immutable source pin and commit.

Exact rematerialization must reproduce the same tree and domain digests.

## Candidate intervention

The candidate begins as an exact copy of the control artifact. An overlay entry must provide:

- an existing allowlisted path;
- that file's observed control SHA-256;
- replacement UTF-8 content.

Every overlay path must be owned by the LAB #85 target domain. New paths, deletions, undeclared changes, stale control digests, or changes to any held-constant domain fail closed.

The overlay body is not stored in the durable materialization ledger. The ledger keeps only deterministic evidence identities and changed paths.

## Production-faithful offline sandbox

`MaterializedHumanSandboxAdapter` invokes the accepted public renderer call shape:

`render_human_response(response_decision, response_depth=...)`

Each render occurs in a fresh Python subprocess with:

- `PYTHONPATH` pointing only at the materialized public `src/` tree;
- a scrubbed environment;
- deterministic Python hash seed;
- socket creation and network connections blocked in the bootstrap;
- no production endpoint configuration;
- no GitHub writes;
- no CMIS, provider, model, or protected-core calls;
- a hard subprocess timeout.

Cases carry a deterministic response-decision payload, response depth, and a deterministic failure predicate. Their full case definition is hashed into the LAB #87 corpus identity.

The sandbox returns only output digests and targeted-failure booleans. It has no causal-outcome vocabulary.

## LAB #87 and LAB #85 handoff

LAB #89 maps the materialized tree and per-domain digests into LAB #87's accepted execution manifest, then uses LAB #87's deterministic replicate runner unchanged.

The resulting LAB #87 receipt contains observations only. `qualify_materialized_receipt_with_lab85()` converts that receipt through LAB #87's accepted adapter into LAB #85's existing result contract. LAB #85 alone emits `DIRECT SUPPORTS`, `DIRECT CONTRADICTS`, or no DIRECT evidence.

LAB #81 remains the only authority that may name `CONFIRMED_ROOT_CAUSE`.

## Safety boundary

LAB #89 does not:

- mutate `roberta-langgraph`;
- alter the production ROBERTA runtime;
- start the ROBERTA graph or protected core;
- contact CMIS, chain providers, models, or production endpoints;
- create or close remediation issues as part of experiment execution;
- execute trades or other production actions;
- resume LAB #21/#22 live evaluation campaigns.

`production_runtime_touched=false`

`production_code_mutation=false`

`runner_outcome_authority=false`

`lab85_qualification_authority=true`

`execution_authorized=false`
