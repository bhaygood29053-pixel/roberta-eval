from roberta_eval import __version__
from roberta_eval.config import load_config, validate_config


def test_package_version() -> None:
    assert __version__ == "0.1.0"


def test_default_lab_config_is_safe() -> None:
    config = load_config()
    validate_config(config)
    assert config["lab"]["production_mutation_allowed"] is False
    assert config["evaluation"]["prefer_deterministic_ground_truth"] is True
    assert config["evaluation"]["allow_ai_judge_as_deterministic_authority"] is False
