from __future__ import annotations

import argparse
import json

from . import __version__
from .config import default_config_path, load_config, validate_config
from .registry import load_registry, registry_summary, validate_registry
from .taxonomy import load_taxonomy, taxonomy_summary, validate_taxonomy


def doctor() -> int:
    config = load_config()
    validate_config(config)
    registry = load_registry()
    validate_registry(registry)
    taxonomy = load_taxonomy()
    validate_taxonomy(taxonomy, registry)
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
    }
    print(json.dumps(result, sort_keys=True))
    return 0


def capabilities() -> int:
    print(json.dumps(registry_summary(load_registry()), indent=2, sort_keys=True))
    return 0


def taxonomy() -> int:
    print(json.dumps(taxonomy_summary(load_taxonomy()), indent=2, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="roberta-eval")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("doctor", help="validate Laboratory configuration, registry, and taxonomy")
    subparsers.add_parser("capabilities", help="validate and summarize the capability registry")
    subparsers.add_parser("taxonomy", help="validate and summarize the question taxonomy")
    args = parser.parse_args()

    if args.command == "doctor":
        return doctor()
    if args.command == "capabilities":
        return capabilities()
    if args.command == "taxonomy":
        return taxonomy()

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
