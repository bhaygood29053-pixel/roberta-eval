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

## Completed

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

## Active

### LAB #3 — Question Taxonomy v1

Define machine-readable question classes and separate evidence, user-style, and conversation-shape dimensions.

Current LAB #3 implementation:
- 15 test classes including all required basic/complex/numerical/comparison/ambiguous/adversarial/false-premise/missing-data/stale-data/unsupported/follow-up/multi-turn classes;
- separate evidence-condition, user-style, and conversation-shape dimensions;
- objective-preservation rule for generated wording variants;
- strict capability-reference and conversation-shape validation;
- CLI and CI taxonomy validation.

Acceptance is complete when the LAB #3 PR is green and merged.

## Next

### LAB #4 — First deterministic corpus

Create the first 100 known-answer cases, then expand to 500.

### LAB #5 — Runtime harness

Run cases through the real local ROBERTA interface and persist normalized test-run records.

### LAB #6 — Deterministic graders

Grade facts, numbers, freshness, evidence fidelity, risk semantics, and execution boundaries.

### LAB #7 — Generated variation

Generate paraphrases and scenario variations without changing the underlying test objective.

### LAB #8 — 2,500-question stress run

Produce the first broad capability map of ROBERTA strengths, failures, and runtime issues.

## Later

- semantic and human-quality graders;
- adversarial suites;
- multi-turn consistency testing;
- failure classification and severity;
- root-cause localization;
- failure clustering;
- permanent regression memory;
- trend intelligence;
- evaluation dashboard;
- GitHub defect promotion;
- release qualification gates;
- 10,000+ and eventually 25,000+ case suites.

## Quality rule

Scale is not success by itself. A smaller suite with trustworthy expectations is more valuable than thousands of poorly specified questions.
