# ROBERTA Evaluation Laboratory Roadmap

## Active

### LAB #1 — Repository foundation

Goal: establish a minimal, executable, tested Laboratory repository.

Acceptance:
- package installs;
- configuration loads;
- CLI doctor command succeeds;
- smoke tests pass;
- CI exists;
- Laboratory contract, architecture, and roadmap exist.

## Next

### LAB #2 — Capability Registry v1

Create the authoritative inventory of ROBERTA services/capabilities, required evidence, supported question families, freshness rules, allowed conclusions, and known limitations.

### LAB #3 — Question Taxonomy v1

Define basic, complex, ambiguous, adversarial, missing-data, stale-data, numerical, comparison, follow-up, multi-turn, and unsupported-question classes.

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
