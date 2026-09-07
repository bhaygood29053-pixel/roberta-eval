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

config/
  capabilities.json       ROBERTA capability inventory
  question_taxonomy.json  test-class and generation dimensions
  corpus_blueprints.json  reviewed known-answer case blueprints and style variants
  generation_surfaces.json deterministic high-volume wording surfaces

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
