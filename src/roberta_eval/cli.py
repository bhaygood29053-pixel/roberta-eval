from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import __version__
from .config import default_config_path, load_config, validate_config
from .corpus import corpus_summary, materialize_cases, write_corpus
from .grader import grade_records, grader_summary, load_run_jsonl, write_grades
from .registry import load_registry, registry_summary, validate_registry
from .runner import FixtureRobertaTransport, HttpRobertaTransport, run_cases, run_summary, write_run
from .taxonomy import load_taxonomy, taxonomy_summary, validate_taxonomy


def doctor() -> int:
    config = load_config()
    validate_config(config)
    registry = load_registry()
    validate_registry(registry)
    taxonomy = load_taxonomy()
    validate_taxonomy(taxonomy, registry)
    cases = materialize_cases()
    corpus = corpus_summary(cases)
    result = {
        "service": "roberta-eval",
        "version": __version__,
        "status": "ok",
        "config": str(default_config_path()),
        "target": config["lab"]["default_target"],
        "production_mutation_allowed": config["lab"]["production_mutation_allowed"],
        "capability_registry": registry["registry_version"],
        "question_taxonomy": taxonomy["taxonomy_version"],
        "cmis_service_count": len(registry["cmis_services"]),
        "human_workflow_count": len(registry["human_workflows"]),
        "question_class_count": len(taxonomy["classes"]),
        "deterministic_case_count": corpus["case_count"],
        "deterministic_corpus_sha256": corpus["sha256"],
    }
    print(json.dumps(result, sort_keys=True))
    return 0


def capabilities() -> int:
    print(json.dumps(registry_summary(load_registry()), indent=2, sort_keys=True))
    return 0


def taxonomy() -> int:
    print(json.dumps(taxonomy_summary(load_taxonomy()), indent=2, sort_keys=True))
    return 0


def corpus(output: str | None = None) -> int:
    cases = materialize_cases()
    if output:
        write_corpus(Path(output), cases)
    print(json.dumps(corpus_summary(cases), indent=2, sort_keys=True))
    return 0


def run_suite(mode: str, limit: int | None, output: str | None, target: str | None, run_id: str) -> int:
    config = load_config()
    selected_target = target or config["lab"]["default_target"]
    if mode == "http":
        transport = HttpRobertaTransport(selected_target)
    else:
        transport = FixtureRobertaTransport()
        selected_target = "fixture://local"

    records = run_cases(
        materialize_cases(),
        transport=transport,
        run_id=run_id,
        target=selected_target,
        limit=limit,
    )
    if output:
        write_run(Path(output), records)
    print(json.dumps(run_summary(records), indent=2, sort_keys=True))
    return 0


def grade_suite(input_path: str | None, output: str | None, limit: int | None) -> int:
    if input_path:
        records = load_run_jsonl(Path(input_path))
    else:
        records = run_cases(
            materialize_cases(),
            transport=FixtureRobertaTransport(),
            run_id="grader-smoke",
            target="fixture://local",
            limit=limit,
        )
    results = grade_records(records)
    if output:
        write_grades(Path(output), results)
    print(json.dumps(grader_summary(results), indent=2, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="roberta-eval")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("doctor", help="validate Laboratory configuration, registry, and taxonomy")
    subparsers.add_parser("capabilities", help="validate and summarize the capability registry")
    subparsers.add_parser("taxonomy", help="validate and summarize the question taxonomy")
    corpus_parser = subparsers.add_parser("corpus", help="validate and summarize deterministic corpus")
    corpus_parser.add_argument("--write", dest="output", help="write materialized JSONL corpus")
    run_parser = subparsers.add_parser("run", help="execute corpus cases through a ROBERTA transport")
    run_parser.add_argument("--mode", choices=("fixture", "http"), default="fixture")
    run_parser.add_argument("--limit", type=int, default=None)
    run_parser.add_argument("--output", default=None)
    run_parser.add_argument("--target", default=None)
    run_parser.add_argument("--run-id", default="manual-run")
    grade_parser = subparsers.add_parser("grade", help="grade normalized run records")
    grade_parser.add_argument("--input", default=None)
    grade_parser.add_argument("--output", default=None)
    grade_parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    if args.command == "doctor":
        return doctor()
    if args.command == "capabilities":
        return capabilities()
    if args.command == "taxonomy":
        return taxonomy()
    if args.command == "corpus":
        return corpus(args.output)
    if args.command == "run":
        return run_suite(args.mode, args.limit, args.output, args.target, args.run_id)
    if args.command == "grade":
        return grade_suite(args.input, args.output, args.limit)

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
