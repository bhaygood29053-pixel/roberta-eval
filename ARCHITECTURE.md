# Architecture

## System relationship

```text
Providers / chain evidence
          |
          v
         CMIS
          |
          v
       X1 Scout
          |
          v
       ROBERTA
          ^
          |
   tests / evaluates
          |
   roberta-eval
```

The Laboratory is intentionally separate from ROBERTA production code.

## Initial modules

```text
src/roberta_eval/
  config.py       repository and run configuration
  cli.py          operator entry point
  registry.py     capability registry validation
  taxonomy.py     question taxonomy validation
  corpus.py       deterministic corpus materialization and validation
  runner.py       fixture/HTTP transports and normalized run records
  grader.py       deterministic check evaluation and verdicts
  generator.py    reproducible high-volume surface variation
  stress.py       large-suite qualification and reporting
  quality.py      advisory human-response quality scoring
  adversarial.py  invariant-targeted adversarial suite generation
  conversation.py multi-turn generation, execution, and fact-consistency grading
  classifier.py   stable failure categories and severity normalization
  root_cause.py   conservative layer localization from explicit snapshots
  clustering.py   stable recurring-defect clustering
  regression_memory.py confirmed replayable defect memory
  trends.py       normalized longitudinal quality comparisons
  dashboard.py    presentation-only evaluation view model and Markdown
  github_promotion.py review-gated GitHub defect proposals
  release_qualification.py evidence-aware release gates
  scale.py        10k/25k deterministic scale generation and qualification

config/
  capabilities.json       ROBERTA capability inventory
  question_taxonomy.json  test-class and generation dimensions
  corpus_blueprints.json  reviewed known-answer case blueprints and style variants
  generation_surfaces.json deterministic high-volume wording surfaces
  adversarial_attacks.json named invariant-attack wrappers
  conversation_patterns.json multi-turn no-new-evidence patterns
  regression_memory.json permanent confirmed regression cases
  trend_history.json versioned longitudinal evaluation snapshots
  release_policy.json deterministic blocking and advisory warning policy
  scale_surfaces.json 500 controlled scale surfaces per reviewed blueprint

future/
  generators/     question/scenario generation
  runners/        runtime execution
  collectors/     ROBERTA/Scout/CMIS evidence capture
  graders/        deterministic and semantic grading
  classifiers/    failure taxonomy
  clustering/     recurring failure grouping
  regressions/    permanent failure cases
  trends/         longitudinal quality analysis
  reporting/      machine and human reports
```

## Evaluation record

Every executed case should eventually produce a durable record containing at least:

- test ID and suite version;
- timestamp;
- capability and question type;
- question and conversation context;
- ROBERTA response;
- route/service metadata when available;
- relevant evidence snapshot or reference;
- runtime status and latency;
- deterministic checks;
- semantic scores if used;
- failure category, severity, and likely layer;
- Laboratory version and ROBERTA version/commit.

## Design principles

1. Reproducibility before scale.
2. Deterministic grading before subjective grading.
3. Preserve raw evidence separately from interpretations.
4. A failure is not actionable until its expected behavior is explainable.
5. One underlying defect should not become hundreds of duplicate engineering issues.
6. Real failures become regression memory.
7. The Laboratory itself must be tested and versioned.

## Runtime harness boundary

The deterministic corpus is fixture-backed and may be executed through the fixture transport in CI. The HTTP transport is a real ROBERTA bridge adapter, but running a synthetic fixture question against a live chain does not convert the synthetic answer key into live truth. Live semantic qualification requires live-eligible cases and evidence capture.

## Deterministic grading boundary

Structured checks are authoritative only when the run record exposes the required structured evidence. A live text-only answer that lacks the necessary structure is WARN/UNSCORABLE for that check; the grader does not infer hidden facts from prose. Semantic grading is a later, separate layer.

## Stress qualification semantics

The default 2,500-case stress gate qualifies Laboratory pipeline scale using fixture evidence. The report carries `live_roberta_qualified=false`. Live ROBERTA quality claims require a separate live-eligible corpus, HTTP execution, and evidence-aware grading.

## Advisory semantic/human-quality boundary

Human-quality scores are secondary signals. They may identify poor clarity, weak uncertainty language, repetitive output, missing recommendations, or internal-contract leakage, but they cannot change deterministic facts, erase deterministic failures, or serve as factual authority. Future semantic judges must implement the same advisory boundary.

## Multi-turn runtime boundary

The current public HTTP adapter posts individual messages and does not expose an explicit session/conversation identifier. Therefore fixture multi-turn consistency is qualified, but live HTTP context retention remains unqualified until ROBERTA exposes and documents a session contract.

## Failure-classification boundary

A failure classifier labels observed grader/runtime findings; it does not create facts. Missing structured evidence is classified as evaluation incompleteness rather than silently promoted into a ROBERTA defect.

## Root-cause localization boundary

Localization is evidence-driven. Without a sufficient layer snapshot, product defects remain `unknown`; the Laboratory does not infer a failing component merely from the shape of an answer.

## Failure-clustering boundary

Clusters represent repeated manifestations of the same classified defect identity. The Laboratory does not cluster solely on wording similarity, and evaluation-incomplete findings remain separate from actionable product defects.

## Regression-memory boundary

Permanent regression memory is confirmation-gated. Evaluation-system failures, unconfirmed clusters, and non-replayable cases are not silently promoted into product regressions.

## Trend-intelligence boundary

Deterministic correctness trends and advisory human-quality trends are separate. Fixture-pipeline history cannot be relabeled as live ROBERTA quality history, and advisory improvement cannot erase deterministic regression.

## Dashboard boundary

The dashboard is presentation-only. It must preserve source qualification scope and cannot recompute evidence, overrule deterministic graders, or represent fixture results as live ROBERTA proof.

## GitHub defect-promotion boundary

The Laboratory produces reviewable issue proposals only from explicitly confirmed actionable clusters. Proposal generation does not create an issue automatically, and UNKNOWN localization remains unassigned until evidence improves.

## Release-qualification boundary

Deterministic failures, critical findings, failed regression replays, and deterministic regressions may block qualification. Advisory human-quality metrics can warn but cannot override a deterministic block. Live release qualification requires live-qualified evidence.

## Scale-suite boundary

The 10,000-case and 25,000-case gates qualify Laboratory scale behavior over synthetic fixture evidence. They preserve the reviewed blueprint answer keys and carry `live_roberta_qualified=false`; scale alone does not convert fixture evidence into live ROBERTA proof.
