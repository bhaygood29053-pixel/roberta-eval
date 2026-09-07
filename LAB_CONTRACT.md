# ROBERTA Evaluation Laboratory Contract v1

## Mission

The ROBERTA Evaluation Laboratory exists to discover defects, regressions, weak patterns, and capability gaps in ROBERTA by running controlled, reproducible evaluation workloads at scale.

The Laboratory should eventually generate and execute thousands of realistic, deterministic, adversarial, ambiguous, and multi-turn questions across the services ROBERTA exposes.

## Authority boundaries

The Laboratory MAY:

- invoke ROBERTA through approved runtime interfaces;
- capture ROBERTA responses, routing metadata, latency, errors, and available supporting evidence;
- compare answers with deterministic fixtures and accepted evidence;
- grade measurable response properties;
- use semantic grading for subjective properties when clearly separated from deterministic grading;
- classify, cluster, trend, and report failures;
- preserve confirmed failures as permanent regression cases;
- recommend likely root causes and candidate remediation work;
- propose engineering issues for human review.

The Laboratory MUST NOT:

- execute financial transactions;
- authorize execution on ROBERTA's behalf;
- alter CMIS, Scout, provider, or ROBERTA evidence to manufacture a passing result;
- silently weaken an expected result after a failure;
- treat an AI judge as authoritative when deterministic evidence is available;
- automatically modify production ROBERTA behavior merely because a generated grader prefers another answer;
- mark an unsupported capability as a ROBERTA defect without first checking the capability registry.

## Evaluation hierarchy

When deciding correctness, prefer evidence in this order:

1. deterministic fixture or invariant;
2. accepted CMIS/provider evidence and explicit contracts;
3. accepted Scout interpretation contracts;
4. semantic evaluation for qualities that cannot be determined mechanically.

## Defect ownership

A detected failure should be localized when possible:

- provider evidence wrong -> provider/source investigation;
- provider correct, CMIS wrong -> CMIS defect;
- CMIS correct, Scout wrong -> Scout defect;
- upstream evidence correct, ROBERTA answer wrong -> ROBERTA synthesis/orchestration defect;
- evaluation expectation wrong -> Laboratory defect.

## Regression rule

A confirmed production defect should become a permanent regression case before or with the fix whenever practical.

## Change rule

The Laboratory may recommend and test changes. Production changes remain subject to the normal repository acceptance and merge process.

## Success criterion

The Laboratory succeeds when it makes ROBERTA measurably more reliable and human-useful while reducing the chance that fixes introduce new failures.
