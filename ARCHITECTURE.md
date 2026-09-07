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

future/
  registry/       capability registry
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
