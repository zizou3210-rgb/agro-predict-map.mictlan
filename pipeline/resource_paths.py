from __future__ import annotations

import os
import subprocess
import sys
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
    python_candidates = [
        Path(value).expanduser()
        for name in ("APP_FEATUREHERO_PYTHON", "APP_PIPELINE_PYTHON")
        if (value := os.environ.get(name, "").strip())
    ]
    repo = APP_RESOURCES_DIR / "featurehero"
    python_candidates.extend([
        repo / ".venv" / "Scripts" / "python.exe",
        repo / ".venv" / "Scripts" / "python3.exe",
        repo / ".venv" / "bin" / "python",
        repo / ".venv" / "bin" / "python3",
        repo / ".venv" / "bin" / "python3.12",
        Path(sys.executable),
    ])
    # The pipeline may already run in a compatible environment even when the
    # vendored venv is absent or its system-interpreter symlink is broken.
    for candidate in dict.fromkeys(python_candidates):
        if not candidate.is_file():
            continue
        try:
            result = subprocess.run(
                [str(candidate), "-c", "import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) else 1)"],
                capture_output=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode == 0:
            return candidate
    raise FileNotFoundError(
        "No usable Python 3.12 interpreter was found for FeatureHero. "
        "Configure APP_FEATUREHERO_PYTHON or APP_PIPELINE_PYTHON, "
        "or install Python 3.12 in resources/featurehero/.venv."
    )


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
