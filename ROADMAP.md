# ROBERTA Evaluation Laboratory Roadmap

## Completed

### LAB #1 — Repository foundation

Goal: establish a minimal, executable, tested Laboratory repository.

Acceptance:
- package installs;
- configuration loads;
- CLI doctor command succeeds;
- smoke tests pass;
- CI exists;
- Laboratory contract, architecture, and roadmap exist.

### LAB #2 — Capability Registry v1

Create the authoritative inventory of ROBERTA services/capabilities, required evidence, supported question families, freshness rules, allowed conclusions, and known limitations.

Current LAB #2 implementation:
- 18 current ROBERTA-side CMIS service contracts represented;
- 10 Human Response v1 workflow families represented;
- source repository/ref/observed commit recorded;
- contract exposure is explicitly separated from live evidence health;
- deterministic validation rejects parity drift, duplicate IDs, unsafe execution authorization, and invalid workflow mappings;
- CLI and CI validate the registry.

Acceptance completed in merged LAB #2.

### LAB #3 — Question Taxonomy v1

Define machine-readable question classes and separate evidence, user-style, and conversation-shape dimensions.

Current LAB #3 implementation:
- 15 test classes including all required basic/complex/numerical/comparison/ambiguous/adversarial/false-premise/missing-data/stale-data/unsupported/follow-up/multi-turn classes;
- separate evidence-condition, user-style, and conversation-shape dimensions;
- objective-preservation rule for generated wording variants;
- strict capability-reference and conversation-shape validation;
- CLI and CI taxonomy validation.

Acceptance completed in merged LAB #3.

### LAB #4 — First deterministic corpus

Create the first 100 known-answer cases, then expand to 500.

Current LAB #4 implementation:
- 54 deterministic service blueprints across all 18 CMIS services;
- 10 objective-preserving wording/style variants per blueprint;
- 540 reproducible known-answer cases;
- machine-readable fixture data and deterministic checks;
- execution-unauthorized check on every case;
- stable case IDs, objective signatures, and corpus SHA-256;
- CLI can materialize byte-stable JSONL;
- CI validates coverage and reproducibility.

Acceptance completed in merged LAB #4.

### LAB #5 — Runtime harness

Run cases through a normalized ROBERTA transport and persist machine-readable test-run records.

Current LAB #5 implementation:
- normalized run-record contract;
- deterministic fixture transport for CI;
- HTTP transport for the local ROBERTA `/v1/roberta` bridge;
- safe per-case transport-error recording;
- latency, service, taxonomy, objective, expected checks, and response capture;
- JSONL run artifacts;
- CLI mode/limit/target/run-id controls.

The deterministic corpus uses synthetic fixtures; HTTP execution support does not by itself claim those synthetic cases are valid live-chain truth.

Acceptance completed in merged LAB #5.

### LAB #6 — Deterministic graders

Grade facts, numbers, freshness, evidence fidelity, risk semantics, execution boundaries, and runtime failures without inventing missing structure.

Current LAB #6 implementation:
- field equality/null/greater-than/less-than checks with numeric-tolerance support;
- freshness and numeric fixture grading through structured evidence;
- canonical forbidden-conclusion checks;
- CRITICAL execution-boundary failures;
- runtime-failure grading;
- text-only/insufficiently structured responses become WARN rather than guessed PASS/FAIL;
- per-case check results plus suite verdict counts;
- CLI/CI grading smoke coverage.

Acceptance completed in merged LAB #6.

### LAB #7 — Generated variation

Generate thousands of reproducible surface variations without changing the underlying test objective or answer key.

Current LAB #7 implementation:
- 60 deterministic surface forms per reviewed blueprint;
- 3,240 generated cases from 54 blueprints;
- all 18 services retained;
- objective signature, fixture, evidence condition, and checks preserved exactly within each blueprint family;
- duplicate IDs/text rejected;
- stable generated-suite SHA-256;
- CLI/CI materialization and validation.

Acceptance completed in merged LAB #7.

### LAB #8 — 2,500-question stress run

Run the first 2,500-case end-to-end Laboratory pipeline qualification and report coverage/verdicts.

Current LAB #8 implementation:
- deterministic round-robin-like selection across surface signatures and blueprints;
- exactly 2,500 generated cases with all 18 services represented;
- fixture transport executes all selected cases;
- deterministic grader evaluates all 2,500 results;
- JSON and Markdown qualification reports;
- explicit boundary: this qualifies Laboratory pipeline scale, not live ROBERTA answer quality;
- CI executes the full qualification.

Acceptance completed in merged LAB #8 with the fixture pipeline gate green.

### LAB #9 — Human & Semantic Quality Grading v1

Add advisory scoring for human-facing response quality without granting subjective graders factual authority.

Current LAB #9 implementation:
- answer-presence, clarity, relevance, uncertainty, recommendation, repetition, and internal-contract-hygiene signals;
- semantic-judge protocol for future independent providers;
- explicit `advisory_only=true` and `factual_authority=false`;
- CLI/CI support over normalized run records.

Acceptance completed in merged LAB #9.

### LAB #10 — Adversarial Suite v1
Add systematic invariant attacks while preserving the underlying known-answer objective.

Current LAB #10 implementation:
- 8 attack families;
- 432 adversarial cases across all 18 services;
- explicit target invariant per attack;
- original fixture/objective/checks preserved;
- attack-specific forbidden conclusion added;
- stable IDs and digest;
- CLI/CI generation.

Acceptance completed in merged LAB #10.

### LAB #11 — Multi-turn Consistency v1
Test fact stability, follow-up consistency, pressure resistance, and execution boundaries across no-new-evidence conversations.

Current LAB #11 implementation:
- 54 conversations / 162 turns across all 18 services;
- three-turn initial/follow-up/pressure-reversal pattern;
- original fixture, checks, evidence condition, and objective preserved across turns;
- structured fact drift without an evidence event is FAIL;
- execution violation in any turn is CRITICAL FAIL;
- missing structured conversation evidence is WARN;
- live HTTP session persistence remains explicitly unqualified until ROBERTA exposes a session/conversation contract.

Acceptance completed in merged LAB #11.

### LAB #12 — Failure Classification v1
Map grader/runtime/conversation findings into stable defect categories and severities.

Current LAB #12 implementation:
- runtime, factual, numerical, freshness, unsupported-conclusion, execution, contradiction, evaluation-incomplete, and evaluation-error categories;
- deterministic severity normalization;
- text-only/missing structure remains evaluation incomplete instead of becoming a ROBERTA defect;
- conversation fact drift maps to contradiction;
- source grader/reason/case/service provenance retained;
- CLI/CI classification.

Acceptance completed in merged LAB #12.

### LAB #13 — Root Cause Localization v1
Use available layer snapshots to identify the first proven incorrect component without guessing when evidence is absent.

Current LAB #13 implementation:
- provider/CMIS/X1 Scout/ROBERTA/laboratory/runtime-transport/unknown layers;
- explicit layer-snapshot states;
- first-proven-incorrect-layer rules;
- missing or inconclusive layer evidence returns UNKNOWN;
- evaluation-incomplete findings remain Laboratory-side;
- execution-boundary violations can localize to the observed ROBERTA response boundary;
- CLI/CI localization.

Acceptance completed in merged LAB #13.

### LAB #14 — Failure Clustering v1
Collapse recurring failures into stable actionable defect clusters.

Current LAB #14 implementation:
- stable cluster identity from category + service + localized layer + grader reason;
- duplicate manifestations collapse to one cluster;
- highest member severity becomes cluster severity;
- UNKNOWN localization remains explicit;
- evaluation-incomplete/error clusters remain non-product defects;
- stable member/run/case provenance;
- deterministic ordering and CLI/CI support.

Acceptance completed in merged LAB #14.

### LAB #15 — Regression Memory v1
Persist confirmed actionable product defects as permanent replayable regression cases.

Current LAB #15 implementation:
- versioned repository regression-memory store;
- confirmation required before promotion;
- evaluation-incomplete/error clusters are ineligible;
- source service and replayability validated;
- stable idempotent regression IDs;
- fixture/objective/checks retained for replay;
- execution remains unauthorized;
- CLI/CI memory validation.

Acceptance completed in merged LAB #15.

### LAB #16 — Trend Intelligence v1
Compare evaluation runs/releases using normalized deterministic and advisory metrics.

Current LAB #16 implementation:
- versioned trend snapshots and repository history;
- normalized PASS/WARN/FAIL rates;
- critical finding and actionable-cluster trends;
- advisory human-quality trend remains non-authoritative;
- explicit higher/lower-is-better directions;
- IMPROVED/REGRESSED/STABLE comparisons;
- incompatible scope rejection and idempotent history append;
- fixture-pipeline vs live-ROBERTA scope preserved.

Acceptance completed in merged LAB #16.

### LAB #17 — Evaluation Dashboard v1
Render compact human-readable quality dashboards directly from machine-authoritative Laboratory records.

Current LAB #17 implementation:
- stable dashboard view model;
- deterministic PASS/WARN/FAIL and coverage;
- advisory human-quality section explicitly non-authoritative;
- failure-cluster and regression-memory counts;
- trend-history/current-direction fields;
- qualification scope and live-vs-fixture boundary;
- Markdown/JSON output and CI rendering.

Acceptance completed in merged LAB #17.

### LAB #18 — GitHub Defect Promotion v1
Generate reviewable, deduplicated GitHub issue proposals from explicitly confirmed actionable clusters.

Current LAB #18 implementation:
- confirmation-gated issue proposal generation;
- stable cluster fingerprint;
- provider/CMIS -> CMIS repository routing;
- Scout/ROBERTA -> ROBERTA repository routing;
- Laboratory -> roberta-eval routing;
- UNKNOWN localization remains unassigned;
- evaluator/incomplete clusters are ineligible;
- evidence IDs, occurrence count, severity, and replay guidance included;
- proposal generation never claims an issue was created.

Acceptance completed in merged LAB #18.

### LAB #19 — Release Qualification v1
Define evidence-aware release gates with deterministic blocking authority and advisory human-quality warnings.

Current LAB #19 implementation:
- versioned release policy;
- QUALIFIED / QUALIFIED_WITH_ADVISORY_WARNINGS / BLOCKED / EVIDENCE_REQUIRED states;
- deterministic failures and critical findings block;
- regression replay failures block;
- deterministic regression can block;
- low human-quality score warns but cannot override facts;
- live scope requires live-qualified evidence;
- current fixture pipeline can qualify only its own scope.

Acceptance completed in merged LAB #19.

### LAB #20 — 10k/25k Scale Suites
Scale the deterministic fixture pipeline to 10,000 and 25,000 cases while preserving reviewed blueprint semantics.

Current LAB #20 implementation:
- 500 deterministic wording surfaces per reviewed blueprint;
- 27,000-case source scale suite from 54 blueprints;
- stable unique IDs and suite/selection digests;
- original service, fixture, evidence condition, objective signature, and checks preserved;
- deterministic 10k and 25k selections cover all 18 services;
- full fixture transport + deterministic grading qualification;
- exact PASS/WARN/FAIL reporting;
- explicit non-live boundary;
- CI executes both 10,000-case and 25,000-case gates.

Acceptance completed by the green LAB #20 merge.


### LAB #21 — Live Evidence-Backed Evaluation v1

Create a real-subject live evaluation track that is explicitly separate from synthetic fixture qualification.

Current LAB #21 implementation:
- XNT and AGI seed subjects across 10 live service/question families (20-case smoke plan);
- no synthetic fixture or hardcoded live answer key;
- balanced small-run selection across service/taxonomy groups;
- explicit `live_evidence` run-record mode;
- read-only evaluation telemetry contract for evidence, canonical claims, provenance, freshness, and execution boundary;
- `EVIDENCE_REQUIRED` when telemetry is absent instead of guessed PASS/FAIL;
- claim-to-evidence path validation when telemetry is present;
- accepted `roberta_claim_integrity/v1` PASS required for bounded live PASS;
- bounded evidence-contract qualification kept separate from provider-truth/full-natural-language certification;
- deterministic CI validates the live plan and Laboratory logic without provider keys.

Acceptance completes when the LAB #21 PR is green and merged; live ROBERTA qualification additionally depends on ROBERTA exposing the read-only telemetry contract.

## Quality rule

Scale is not success by itself. A smaller suite with trustworthy expectations is more valuable than thousands of poorly specified questions.
