from __future__ import annotations

import argparse
import json

from . import __version__
from .config import default_config_path, load_config, validate_config


def doctor() -> int:
    config = load_config()
    validate_config(config)
    result = {
        "service": "roberta-eval",
        "version": __version__,
        "status": "ok",
        "config": str(default_config_path()),
        "target": config["lab"]["default_target"],
        "production_mutation_allowed": config["lab"]["production_mutation_allowed"],
    }
    print(json.dumps(result, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="roberta-eval")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("doctor", help="validate Laboratory configuration")
    args = parser.parse_args()

    if args.command == "doctor":
        return doctor()

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
