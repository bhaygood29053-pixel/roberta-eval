from __future__ import annotations

from pathlib import Path
import tomllib


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_config_path() -> Path:
    return repository_root() / "config" / "lab.toml"


def load_config(path: Path | None = None) -> dict:
    config_path = path or default_config_path()
    with config_path.open("rb") as handle:
        return tomllib.load(handle)


def validate_config(config: dict) -> None:
    lab = config.get("lab", {})
    evaluation = config.get("evaluation", {})

    if lab.get("production_mutation_allowed") is not False:
        raise ValueError("Laboratory production mutation must remain disabled")

    if evaluation.get("prefer_deterministic_ground_truth") is not True:
        raise ValueError("Deterministic ground truth must be preferred")

    if evaluation.get("allow_ai_judge_as_deterministic_authority") is not False:
        raise ValueError("AI judge cannot be deterministic authority")
