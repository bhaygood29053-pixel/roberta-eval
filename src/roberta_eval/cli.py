from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import __version__
from .adversarial import adversarial_summary, generate_adversarial_cases, write_adversarial
from .config import default_config_path, load_config, validate_config
from .corpus import corpus_summary, materialize_cases, write_corpus
from .conversation import conversation_summary, consistency_summary, generate_conversations, grade_conversation_runs, run_conversations, write_conversations
from .classifier import classification_summary, classify_results, load_jsonl as load_classification_jsonl, write_findings
from .clustering import cluster_findings, cluster_summary, load_jsonl as load_cluster_jsonl, write_clusters
from .grader import grade_records, grader_summary, load_run_jsonl, write_grades
from .dashboard import build_dashboard, write_dashboard_json, write_dashboard_markdown
from .generator import generate_cases, generated_summary, write_generated
from .github_promotion import build_issue_proposals, load_jsonl as load_proposal_jsonl, proposal_summary, write_proposals
from .live import grade_live_records, live_case_summary, live_grader_summary, materialize_live_cases, write_live_cases, write_live_grades
from .quality import grade_human_quality_records, human_quality_summary, write_quality
from .root_cause import localization_summary, localize_findings, load_jsonl as load_localization_jsonl, write_localizations
from .regression_memory import load_memory, memory_summary, validate_memory
from .release_qualification import qualify_release, write_qualification
from .registry import load_registry, registry_summary, validate_registry
from .runner import FixtureRobertaTransport, HttpRobertaTransport, run_cases, run_summary, select_cases, write_run
from .scale import run_scale_qualification, scale_summary, generate_scale_cases, write_scale_report
from .stress import run_stress_qualification, write_stress_json, write_stress_markdown
from .taxonomy import load_taxonomy, taxonomy_summary, validate_taxonomy
from .trends import history_summary, load_history, validate_history


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


def run_suite(mode: str, limit: int | None, output: str | None, target: str | None, run_id: str, selection: str = "sequential") -> int:
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
        selection=selection,
    )
    if output:
        write_run(Path(output), records)
    print(json.dumps(run_summary(records), indent=2, sort_keys=True))
    return 0


def live_plan_suite(limit: int | None, output: str | None) -> int:
    cases = select_cases(
        materialize_live_cases(),
        limit=limit,
        strategy="balanced",
    )
    if output:
        write_live_cases(Path(output), cases)
    print(json.dumps(live_case_summary(cases), indent=2, sort_keys=True))
    return 0


def live_run_suite(
    limit: int | None,
    output: str | None,
    target: str | None,
    run_id: str,
) -> int:
    config = load_config()
    selected_target = target or config["lab"]["default_target"]
    cases = select_cases(
        materialize_live_cases(),
        limit=limit,
        strategy="balanced",
    )
    records = run_cases(
        cases,
        transport=HttpRobertaTransport(selected_target),
        run_id=run_id,
        target=selected_target,
    )
    if output:
        write_run(Path(output), records)
    summary = run_summary(records)
    summary["qualification_scope"] = "live_roberta"
    summary["synthetic_ground_truth_used"] = False
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def live_grade_suite(input_path: str, output: str | None) -> int:
    records = load_run_jsonl(Path(input_path))
    results = grade_live_records(records)
    if output:
        write_live_grades(Path(output), results)
    summary = live_grader_summary(results)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if summary["verdict_counts"]["FAIL"] else 0


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


def generate_suite(output: str | None) -> int:
    cases = generate_cases()
    if output:
        write_generated(Path(output), cases)
    print(json.dumps(generated_summary(cases), indent=2, sort_keys=True))
    return 0


def stress_suite(limit: int, json_output: str | None, markdown_output: str | None) -> int:
    report = run_stress_qualification(limit=limit)
    if json_output:
        write_stress_json(Path(json_output), report)
    if markdown_output:
        write_stress_markdown(Path(markdown_output), report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["accepted"] else 1


def quality_suite(input_path: str, output: str | None) -> int:
    records = load_run_jsonl(Path(input_path))
    results = grade_human_quality_records(records)
    if output:
        write_quality(Path(output), results)
    print(json.dumps(human_quality_summary(results), indent=2, sort_keys=True))
    return 0


def adversarial_suite(output: str | None) -> int:
    cases = generate_adversarial_cases()
    if output:
        write_adversarial(Path(output), cases)
    print(json.dumps(adversarial_summary(cases), indent=2, sort_keys=True))
    return 0


def conversation_suite(output: str | None) -> int:
    conversations = generate_conversations()
    runs = run_conversations(conversations)
    grades = grade_conversation_runs(runs)
    if output:
        write_conversations(Path(output), conversations)
    payload = {
        "suite": conversation_summary(conversations),
        "consistency": consistency_summary(grades),
        "live_http_session_qualified": False,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["consistency"]["verdict_counts"]["FAIL"] == 0 else 1


def classify_suite(input_path: str, output: str | None) -> int:
    grade_results = load_classification_jsonl(Path(input_path))
    findings = classify_results(grade_results)
    if output:
        write_findings(Path(output), findings)
    print(json.dumps(classification_summary(findings), indent=2, sort_keys=True))
    return 0


def localize_suite(input_path: str, output: str | None) -> int:
    findings = load_localization_jsonl(Path(input_path))
    results = localize_findings(findings)
    if output:
        write_localizations(Path(output), results)
    print(json.dumps(localization_summary(results), indent=2, sort_keys=True))
    return 0


def cluster_suite(findings_path: str, localizations_path: str | None, output: str | None) -> int:
    findings = load_cluster_jsonl(Path(findings_path))
    localizations = load_cluster_jsonl(Path(localizations_path)) if localizations_path else None
    clusters = cluster_findings(findings, localizations)
    if output:
        write_clusters(Path(output), clusters)
    print(json.dumps(cluster_summary(clusters), indent=2, sort_keys=True))
    return 0


def regression_memory_suite() -> int:
    memory = load_memory()
    validate_memory(memory)
    print(json.dumps(memory_summary(memory), indent=2, sort_keys=True))
    return 0


def trend_suite() -> int:
    history = load_history()
    validate_history(history)
    print(json.dumps(history_summary(history), indent=2, sort_keys=True))
    return 0


def dashboard_suite(json_output: str | None, markdown_output: str | None) -> int:
    qualification = run_stress_qualification(limit=2500)
    view = build_dashboard(
        qualification=qualification,
        regression_memory=memory_summary(load_memory()),
        trend_history=history_summary(load_history()),
    )
    if json_output:
        write_dashboard_json(Path(json_output), view)
    if markdown_output:
        write_dashboard_markdown(Path(markdown_output), view)
    print(json.dumps(view, indent=2, sort_keys=True))
    return 0


def proposal_suite(clusters_path: str, confirmed: list[str], output: str | None) -> int:
    clusters = load_proposal_jsonl(Path(clusters_path))
    proposals = build_issue_proposals(
        clusters,
        confirmed_cluster_ids=set(confirmed),
    )
    if output:
        write_proposals(Path(output), proposals)
    print(json.dumps(proposal_summary(proposals), indent=2, sort_keys=True))
    return 0


def release_qualification_suite(scope: str, output: str | None) -> int:
    report = qualify_release(
        requested_scope=scope,
        qualification_report=run_stress_qualification(limit=2500),
    )
    if output:
        write_qualification(Path(output), report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["release_qualified"] or report["status"] == "EVIDENCE_REQUIRED" else 1


def scale_suite(limit: int, output: str | None) -> int:
    report = run_scale_qualification(limit=limit)
    if output:
        write_scale_report(Path(output), report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["accepted"] else 1


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
    run_parser.add_argument("--selection", choices=("sequential", "balanced"), default="sequential")
    live_plan_parser = subparsers.add_parser("live-plan", help="materialize balanced real-subject live evaluation cases")
    live_plan_parser.add_argument("--limit", type=int, default=20)
    live_plan_parser.add_argument("--write", dest="output", default=None)
    live_run_parser = subparsers.add_parser("live-run", help="execute balanced live-evidence cases through ROBERTA HTTP")
    live_run_parser.add_argument("--limit", type=int, default=20)
    live_run_parser.add_argument("--output", default=None)
    live_run_parser.add_argument("--target", default=None)
    live_run_parser.add_argument("--run-id", default="live-manual-run")
    live_grade_parser = subparsers.add_parser("live-grade", help="grade live ROBERTA run records against captured evidence telemetry")
    live_grade_parser.add_argument("--input", required=True)
    live_grade_parser.add_argument("--output", default=None)
    grade_parser = subparsers.add_parser("grade", help="grade normalized run records")
    grade_parser.add_argument("--input", default=None)
    grade_parser.add_argument("--output", default=None)
    grade_parser.add_argument("--limit", type=int, default=20)
    generate_parser = subparsers.add_parser("generate", help="materialize generated question suite")
    generate_parser.add_argument("--write", dest="output", default=None)
    stress_parser = subparsers.add_parser("stress", help="run fixture pipeline stress qualification")
    stress_parser.add_argument("--limit", type=int, default=2500)
    stress_parser.add_argument("--json", dest="json_output", default=None)
    stress_parser.add_argument("--markdown", dest="markdown_output", default=None)
    quality_parser = subparsers.add_parser("quality", help="advisory human-response quality grading")
    quality_parser.add_argument("--input", required=True)
    quality_parser.add_argument("--output", default=None)
    adversarial_parser = subparsers.add_parser("adversarial", help="materialize adversarial suite")
    adversarial_parser.add_argument("--write", dest="output", default=None)
    conversation_parser = subparsers.add_parser("conversations", help="run fixture multi-turn consistency suite")
    conversation_parser.add_argument("--write", dest="output", default=None)
    classify_parser = subparsers.add_parser("classify", help="classify deterministic grader findings")
    classify_parser.add_argument("--input", required=True)
    classify_parser.add_argument("--output", default=None)
    localize_parser = subparsers.add_parser("localize", help="conservatively localize classified findings")
    localize_parser.add_argument("--input", required=True)
    localize_parser.add_argument("--output", default=None)
    cluster_parser = subparsers.add_parser("cluster", help="cluster recurring classified failures")
    cluster_parser.add_argument("--findings", required=True)
    cluster_parser.add_argument("--localizations", default=None)
    cluster_parser.add_argument("--output", default=None)
    subparsers.add_parser("regressions", help="validate and summarize permanent regression memory")
    subparsers.add_parser("trends", help="validate and summarize longitudinal trend history")
    dashboard_parser = subparsers.add_parser("dashboard", help="render current Laboratory dashboard")
    dashboard_parser.add_argument("--json", dest="json_output", default=None)
    dashboard_parser.add_argument("--markdown", dest="markdown_output", default=None)
    proposal_parser = subparsers.add_parser("defect-proposals", help="build reviewable GitHub issue proposals")
    proposal_parser.add_argument("--clusters", required=True)
    proposal_parser.add_argument("--confirm", action="append", default=[])
    proposal_parser.add_argument("--output", default=None)
    release_parser = subparsers.add_parser("release-qualify", help="evaluate release qualification gates")
    release_parser.add_argument("--scope", choices=("fixture_pipeline", "live_roberta"), default="fixture_pipeline")
    release_parser.add_argument("--output", default=None)
    scale_parser = subparsers.add_parser("scale", help="run large fixture pipeline qualification")
    scale_parser.add_argument("--limit", type=int, choices=(10000, 25000), required=True)
    scale_parser.add_argument("--output", default=None)
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
        return run_suite(args.mode, args.limit, args.output, args.target, args.run_id, args.selection)
    if args.command == "live-plan":
        return live_plan_suite(args.limit, args.output)
    if args.command == "live-run":
        return live_run_suite(args.limit, args.output, args.target, args.run_id)
    if args.command == "live-grade":
        return live_grade_suite(args.input, args.output)
    if args.command == "grade":
        return grade_suite(args.input, args.output, args.limit)
    if args.command == "generate":
        return generate_suite(args.output)
    if args.command == "stress":
        return stress_suite(args.limit, args.json_output, args.markdown_output)
    if args.command == "quality":
        return quality_suite(args.input, args.output)
    if args.command == "adversarial":
        return adversarial_suite(args.output)
    if args.command == "conversations":
        return conversation_suite(args.output)
    if args.command == "classify":
        return classify_suite(args.input, args.output)
    if args.command == "localize":
        return localize_suite(args.input, args.output)
    if args.command == "cluster":
        return cluster_suite(args.findings, args.localizations, args.output)
    if args.command == "regressions":
        return regression_memory_suite()
    if args.command == "trends":
        return trend_suite()
    if args.command == "dashboard":
        return dashboard_suite(args.json_output, args.markdown_output)
    if args.command == "defect-proposals":
        return proposal_suite(args.clusters, args.confirm, args.output)
    if args.command == "release-qualify":
        return release_qualification_suite(args.scope, args.output)
    if args.command == "scale":
        return scale_suite(args.limit, args.output)

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
