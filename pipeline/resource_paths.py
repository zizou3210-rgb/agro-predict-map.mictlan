from __future__ import annotations

import os
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
APP_DIR = ROOT_DIR
APP_RESOURCES_DIR = APP_DIR / "resources"


def _resolve_existing_path(candidates: list[Path]) -> Path | None:
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def get_featurehero_repo() -> Path:
    repo = _resolve_existing_path([APP_RESOURCES_DIR / "featurehero"])
    if repo is None:
        raise FileNotFoundError(
            "FeatureHero repository was not found in resources/featurehero."
        )
    return repo


def get_featurehero_python() -> Path:
    override = os.environ.get("APP_FEATUREHERO_PYTHON", "").strip()
    if override:
        candidate = Path(override).expanduser()
        if candidate.exists():
            return candidate

    repo_candidates = [APP_RESOURCES_DIR / "featurehero"]
    python_candidates: list[Path] = []
    for repo in repo_candidates:
        python_candidates.extend(
            [
                repo / ".venv" / "bin" / "python",
                repo / ".venv" / "bin" / "python3",
                repo / ".venv" / "bin" / "python3.12",
            ]
        )

    python_path = _resolve_existing_path(python_candidates)
    if python_path is None:
        raise FileNotFoundError(
            "FeatureHero Python interpreter was not found in "
            "resources/featurehero/.venv."
        )
    return python_path


def get_phen_transform_dataset_repo() -> Path | None:
    return _resolve_existing_path([APP_RESOURCES_DIR / "phen_transform_dataset"])
