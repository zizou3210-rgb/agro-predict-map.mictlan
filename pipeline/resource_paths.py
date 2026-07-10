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
                repo / ".venv" / "Scripts" / "python.exe",
                repo / ".venv" / "Scripts" / "python3.exe",
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


def get_macos_runtime_env() -> dict[str, str]:
    if os.name != "posix" or os.sys.platform != "darwin":
        return {}

    candidates = [
        APP_DIR / "runtime-libs" / "libomp.dylib",
        APP_DIR / "runtime-libs" / "lib" / "libomp.dylib",
    ]
    libomp_path = _resolve_existing_path(candidates)
    if libomp_path is None:
        return {}

    lib_dir = str(libomp_path.parent)
    env_updates: dict[str, str] = {}
    current_dyld = os.environ.get("DYLD_LIBRARY_PATH", "").strip()
    current_fallback = os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "").strip()
    env_updates["DYLD_LIBRARY_PATH"] = lib_dir if not current_dyld else f"{lib_dir}:{current_dyld}"
    env_updates["DYLD_FALLBACK_LIBRARY_PATH"] = lib_dir if not current_fallback else f"{lib_dir}:{current_fallback}"
    return env_updates
