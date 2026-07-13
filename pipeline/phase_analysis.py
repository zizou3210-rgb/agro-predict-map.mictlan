from __future__ import annotations

import csv
import json
import os
import pickle
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pandas as pd
import psutil

from config_env import (
    get_featurehero_job_timeout_seconds,
    get_featurehero_params,
    load_app_env,
)
from pipeline.common import GEO_COLUMNS, GERMPLASM_COLUMNS
from pipeline.model_registry import get_model_dir
from pipeline.resource_paths import (
    ROOT_DIR,
    get_featurehero_python,
    get_featurehero_repo,
    get_macos_runtime_env,
    get_phen_transform_dataset_repo,
)


TARGET_COLUMN = "Grain Yield (T/Ha)"
JOBS_FILE = Path.home() / ".featurehero" / "jobs.pids"
OTHER_TARGET_COLUMNS = [
    "Rank",
    "Plant_Aspect_1_5_1_h_high_ear_placement_header",
    "Ear_aspect_1_5_1_n_undesirable_texture_header",
]
WORKSPACE_FILES_TO_COPY = [
    "best_model_sort_original.pkl",
    "best_features_sort_original.pkl",
    "optimization_sort_original.csv",
    "optimization_overlap_sort_original.csv",
    "optimization_graph_optimization_sort_original.png",
    "optimization_overlap_graph_optimization_sort_original.png",
    "original.csv",
    "sort_original.csv",
]
MODEL_MACHINE_NAME = "Extreme Gradient Boosting"
ProgressCallback = Callable[[int, str, str], None]


@dataclass
class PhaseAnalysisOutputs:
    model_id: str
    model_dir: Path
    best_model_file: Path
    best_features_file: Path
    metadata_file: Path
    description: str
    metadata: dict[str, object]


def read_jobs() -> dict[str, dict[str, str]]:
    if not JOBS_FILE.exists():
        return {}
    return json.loads(JOBS_FILE.read_text(encoding="utf-8"))


def get_featurehero_params_json() -> str:
    params = get_featurehero_params()
    return json.dumps(params, ensure_ascii=False)


def is_pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        return psutil.pid_exists(pid)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def wait_for_pid(pid: int, timeout_seconds: float | None = None) -> None:
    if timeout_seconds is None:
        timeout_seconds = float(get_featurehero_job_timeout_seconds())
    started_at = time.time()
    while True:
        if not is_pid_running(pid):
            return

        if time.time() - started_at > timeout_seconds:
            raise TimeoutError(f"Timed out while waiting for FeatureHero job {pid}.")
        time.sleep(5.0)


def read_status_progress(status_file: Path | None) -> tuple[int, int] | None:
    if status_file is None or not status_file.exists():
        return None
    try:
        raw_value = status_file.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if "/" not in raw_value:
        return None
    current_text, total_text = raw_value.split("/", 1)
    try:
        current_step = int(current_text.strip())
        total_steps = int(total_text.strip())
    except ValueError:
        return None
    if total_steps <= 0:
        return None
    return current_step, total_steps


def read_last_log_line(log_file: Path | None) -> str:
    if log_file is None or not log_file.exists():
        return ""
    try:
        lines = log_file.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return ""
    for line in reversed(lines):
        cleaned = line.strip()
        if cleaned:
            return cleaned
    return ""


def read_last_non_progress_log_line(log_file: Path | None) -> str:
    if log_file is None or not log_file.exists():
        return ""
    try:
        lines = log_file.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return ""
    for line in reversed(lines):
        cleaned = line.strip()
        if not cleaned:
            continue
        if "Progress:" in cleaned:
            continue
        return cleaned
    return ""


def snapshot_workspace_dirs(workspace_root: Path) -> set[str]:
    if not workspace_root.exists():
        return set()
    return {path.name for path in workspace_root.iterdir() if path.is_dir()}


def find_launched_job(
    before: dict[str, dict[str, str]],
    after: dict[str, dict[str, str]],
    data_file: Path,
    target_column: str,
) -> tuple[int, dict[str, str]]:
    expected_file = str(data_file)
    for pid, info in after.items():
        if pid in before:
            continue
        if info.get("file_path") == expected_file and info.get("target_column") == target_column:
            return int(pid), info
    raise RuntimeError(f"Could not find the launched FeatureHero job for target column {target_column!r}.")


def read_first_metric_value(optimization_csv: Path, metric_name: str) -> float | None:
    if not optimization_csv.exists():
        return None
    with optimization_csv.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        first_row = next(reader, None)
    if not first_row:
        return None
    value = first_row.get(metric_name, "")
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def select_feature_names(sort_original_csv: Path, best_features_file: Path) -> list[str]:
    with sort_original_csv.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        header = next(reader)

    with best_features_file.open("rb") as handle:
        feature_mask = pickle.load(handle)

    if not isinstance(feature_mask, list) or len(feature_mask) != len(header):
        return header
    return [column for column, enabled in zip(header, feature_mask) if bool(enabled)]


def read_model_feature_names(best_model_file: Path) -> list[str]:
    featurehero_python = get_featurehero_python()
    featurehero_repo = get_featurehero_repo()
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        str(featurehero_repo)
        if not existing_pythonpath
        else f"{featurehero_repo}:{existing_pythonpath}"
    )
    command = [
        str(featurehero_python),
        "-c",
        (
            "import json,pickle,sys; "
            "model=pickle.load(open(sys.argv[1],'rb')); "
            "machine=getattr(model,'_machine',None); "
            "raw_names=getattr(machine,'feature_names_in_',[]) if machine is not None else []; "
            "names=list(raw_names) if raw_names is not None else []; "
            "booster=None if machine is None else machine.get_booster(); "
            "raw_booster_names=[] if booster is None else booster.feature_names; "
            "booster_names=list(raw_booster_names) if raw_booster_names is not None else []; "
            "print(json.dumps([str(x) for x in (names if len(names) > 0 else booster_names)], ensure_ascii=False))"
        ),
        str(best_model_file),
    ]
    result = subprocess.run(
        command,
        cwd=str(ROOT_DIR),
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    try:
        return [str(column) for column in json.loads(result.stdout.strip() or "[]")]
    except json.JSONDecodeError:
        return []


def resolve_model_feature_names(best_model_file: Path, sort_original_csv: Path, best_features_file: Path) -> list[str]:
    model_feature_names = read_model_feature_names(best_model_file)
    if model_feature_names:
        return model_feature_names
    return select_feature_names(sort_original_csv, best_features_file)


def build_description(
    target_column: str,
    selected_feature_count: int,
    metric_name: str,
    metric_value: float | None,
) -> str:
    if metric_value is None:
        return (
            f"{MODEL_MACHINE_NAME} trained for {target_column} with "
            f"{selected_feature_count} selected features."
        )
    return (
        f"{MODEL_MACHINE_NAME} trained for {target_column} with "
        f"{selected_feature_count} selected features and "
        f"{metric_name}={metric_value:.4f}."
    )


def build_target_names(target_column: str) -> tuple[str, str]:
    sanitized = re.sub(r"[^A-Za-z0-9]+", "_", str(target_column).strip()).strip("_")
    if not sanitized:
        sanitized = "target"
    folder_name = sanitized
    base_name = sanitized[:80]
    return folder_name, base_name


def prepare_analysis_dataframe(df: pd.DataFrame, target_column: str) -> pd.DataFrame:
    prepared_df = df.copy()
    if target_column not in prepared_df.columns:
        raise ValueError(f"No se encontro la columna objetivo {target_column!r}.")

    drop_columns = {
        "idPK",
        *OTHER_TARGET_COLUMNS,
        *GEO_COLUMNS,
        *GERMPLASM_COLUMNS,
        "Grain Yield predicted",
    }
    drop_columns.discard(target_column)
    prepared_df = prepared_df.drop(columns=[column for column in drop_columns if column in prepared_df.columns])

    for column in prepared_df.columns:
        prepared_df[column] = pd.to_numeric(prepared_df[column], errors="coerce")

    prepared_df[target_column] = pd.to_numeric(prepared_df[target_column], errors="coerce")
    prepared_df = prepared_df[prepared_df[target_column].notna() & (prepared_df[target_column] > 0)].copy()
    if prepared_df.empty:
        raise ValueError(
            "Phase analysis requires rows with numeric values greater than zero "
            f"in {target_column!r}."
        )

    non_numeric_columns = [
        column for column in prepared_df.columns
        if not pd.api.types.is_numeric_dtype(prepared_df[column])
    ]
    if non_numeric_columns:
        raise ValueError(
            "FeatureHero analysis requires numeric columns only after phase5. "
            "Found non-numeric columns:\n- " + "\n- ".join(non_numeric_columns)
        )

    return prepared_df


def write_phase_analysis_inputs(target_dir: Path, base_name: str, df: pd.DataFrame) -> tuple[Path, Path, Path, Path]:
    target_dir.mkdir(parents=True, exist_ok=True)
    grain_xlsx = target_dir / f"{base_name}.xlsx"
    grain_csv = target_dir / f"{base_name}.csv"
    analysis_csv = target_dir / f"{base_name}_for_analysis.csv"
    analysis_xlsx = target_dir / f"{base_name}_for_analysis.xlsx"

    df.to_excel(grain_xlsx, index=False)
    df.to_csv(grain_csv, index=False)
    df.to_csv(analysis_csv, index=False)
    df.to_excel(analysis_xlsx, index=False)
    return grain_xlsx, grain_csv, analysis_csv, analysis_xlsx


def resolve_workspace_dir(target_dir: Path, before_dirs: set[str]) -> Path:
    workspace_root = target_dir / "work_space_featurehero"
    if not workspace_root.exists():
        raise FileNotFoundError("FeatureHero did not create work_space_featurehero.")

    created_dirs = [
        path for path in workspace_root.iterdir()
        if path.is_dir() and path.name not in before_dirs
    ]
    if created_dirs:
        created_dirs.sort(key=lambda path: path.name, reverse=True)
        return created_dirs[0]

    existing_dirs = [path for path in workspace_root.iterdir() if path.is_dir()]
    if not existing_dirs:
        raise FileNotFoundError("FeatureHero workspace folder is empty.")
    existing_dirs.sort(key=lambda path: path.name, reverse=True)
    return existing_dirs[0]


def copy_if_exists(source: Path, destination: Path) -> None:
    if source.exists():
        shutil.copy2(source, destination)


def persist_model_artifacts(
    model_id: str,
    target_dir: Path,
    target_column: str,
    base_name: str,
    workspace_dir: Path,
    job_info: dict[str, str],
    source_phase5_csv: Path,
) -> PhaseAnalysisOutputs:
    model_dir = get_model_dir(model_id)
    model_dir.mkdir(parents=True, exist_ok=True)

    for file_name in WORKSPACE_FILES_TO_COPY:
        copy_if_exists(workspace_dir / file_name, model_dir / file_name)

    log_path_value = str(job_info.get("log_file", "")).strip()
    status_path_value = str(job_info.get("status_file", "")).strip()
    log_file = Path(log_path_value).expanduser() if log_path_value else None
    status_file = Path(status_path_value).expanduser() if status_path_value else None
    if log_file is not None:
        copy_if_exists(log_file, model_dir / log_file.name)
    if status_file is not None:
        copy_if_exists(status_file, model_dir / status_file.name)

    grain_csv = target_dir / f"{base_name}.csv"
    analysis_csv = target_dir / f"{base_name}_for_analysis.csv"
    copy_if_exists(grain_csv, model_dir / grain_csv.name)
    copy_if_exists(analysis_csv, model_dir / analysis_csv.name)

    best_model_file = model_dir / "best_model_sort_original.pkl"
    best_features_file = model_dir / "best_features_sort_original.pkl"
    sort_original_csv = model_dir / "sort_original.csv"
    optimization_csv = model_dir / "optimization_sort_original.csv"

    if not best_model_file.exists():
        raise FileNotFoundError("FeatureHero did not produce best_model_sort_original.pkl.")
    if not best_features_file.exists():
        raise FileNotFoundError("FeatureHero did not produce best_features_sort_original.pkl.")
    if not sort_original_csv.exists():
        raise FileNotFoundError("FeatureHero did not produce sort_original.csv.")

    selected_features = resolve_model_feature_names(best_model_file, sort_original_csv, best_features_file)
    featurehero_params = get_featurehero_params()
    metric_name = str(featurehero_params.get("metric") or "mean_absolute_error")
    metric_value = read_first_metric_value(optimization_csv, metric_name)
    description = build_description(target_column, len(selected_features), metric_name, metric_value)

    metadata = {
        "model_id": model_id,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "target_column": target_column,
        "machine_name": MODEL_MACHINE_NAME,
        "metric_name": metric_name,
        "metric_value": metric_value,
        "selected_features": selected_features,
        "selected_feature_count": len(selected_features),
        "description": description,
        "source_phase5_csv": str(source_phase5_csv),
        "analysis_input_csv": str(model_dir / analysis_csv.name),
        "best_model_file": str(best_model_file),
        "best_features_file": str(best_features_file),
        "optimization_csv": str(optimization_csv),
        "workspace_dir": str(workspace_dir),
        "featurehero_log_file": str(model_dir / log_file.name) if log_file is not None else "",
        "featurehero_status_file": str(model_dir / status_file.name) if status_file is not None else "",
        "phen_transform_dataset_repo": str(get_phen_transform_dataset_repo() or ""),
        "featurehero_params": featurehero_params,
    }
    metadata_file = model_dir / "metadata.json"
    metadata_file.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    return PhaseAnalysisOutputs(
        model_id=model_id,
        model_dir=model_dir,
        best_model_file=best_model_file,
        best_features_file=best_features_file,
        metadata_file=metadata_file,
        description=description,
        metadata=metadata,
    )


def launch_featurehero(
    data_file: Path,
    target_dir: Path,
    target_column: str,
    progress_callback: ProgressCallback | None = None,
) -> tuple[int, dict[str, str], Path]:
    load_app_env()
    featurehero_python = get_featurehero_python()
    featurehero_repo = get_featurehero_repo()
    workspace_root = target_dir / "work_space_featurehero"
    before_jobs = read_jobs()
    before_workspace_dirs = snapshot_workspace_dirs(workspace_root)

    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    featurehero_pythonpath = str(featurehero_repo)
    env["PYTHONPATH"] = (
        featurehero_pythonpath
        if not existing_pythonpath
        else f"{featurehero_pythonpath}:{existing_pythonpath}"
    )
    env.update(get_macos_runtime_env())

    command = [
        str(featurehero_python),
        "-m",
        "featurehero.main",
        "run",
        "--file",
        str(data_file),
        "--column",
        target_column,
        "--background",
        "--params",
        get_featurehero_params_json(),
    ]
    try:
        subprocess.run(
            command,
            check=True,
            cwd=str(featurehero_repo),
            env=env,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        stdout_text = (exc.stdout or "").strip()
        stderr_text = (exc.stderr or "").strip()
        details: list[str] = [
            "FeatureHero launch command failed.",
            f"Command: {exc.cmd}",
            f"Exit code: {exc.returncode}",
        ]
        if stdout_text:
            details.append("stdout:\n" + stdout_text)
        if stderr_text:
            details.append("stderr:\n" + stderr_text)
        raise RuntimeError("\n\n".join(details)) from exc

    after_jobs = read_jobs()
    pid, job_info = find_launched_job(before_jobs, after_jobs, data_file, target_column)
    status_path_value = str(job_info.get("status_file", "")).strip()
    log_path_value = str(job_info.get("log_file", "")).strip()
    status_file = Path(status_path_value).expanduser() if status_path_value else None
    log_file = Path(log_path_value).expanduser() if log_path_value else None
    timeout_seconds = float(get_featurehero_job_timeout_seconds())

    started_at = time.time()
    last_progress_snapshot: tuple[int, int] | None = None
    last_log_snapshot = ""
    last_message = ""
    while True:
        if not is_pid_running(pid):
            break

        progress = read_status_progress(status_file)
        if progress is not None and progress != last_progress_snapshot:
            started_at = time.time()
            last_progress_snapshot = progress
        last_log_line = (
            read_last_non_progress_log_line(log_file)
            if progress is not None
            else read_last_log_line(log_file)
        )
        if last_log_line and last_log_line != last_log_snapshot:
            started_at = time.time()
            last_log_snapshot = last_log_line

        if progress_callback:
            if progress is not None:
                current_step, total_steps = progress
                training_stage_percent = round((current_step / total_steps) * 100)
                phase_percent = training_stage_percent
                message = (
                    f"FeatureHero training progress {training_stage_percent}% ({current_step}/{total_steps})."
                    + (f" Last update: {last_log_line}" if last_log_line else "")
                )
            else:
                phase_percent = 0
                message = (
                    f"FeatureHero is training the model for {target_column}."
                    + (f" Last update: {last_log_line}" if last_log_line else "")
                )
            if message != last_message:
                progress_callback(phase_percent, "Running model analysis", message)
                last_message = message

        if time.time() - started_at > timeout_seconds:
            raise TimeoutError(
                "Timed out while waiting for FeatureHero job "
                f"{pid}. Last progress: {progress[0]}/{progress[1]}."
                if progress is not None
                else f"Timed out while waiting for FeatureHero job {pid}."
            )
        time.sleep(5.0)
    workspace_dir = resolve_workspace_dir(target_dir, before_workspace_dirs)
    return pid, job_info, workspace_dir


def run_phase_analysis(
    phase5_df: pd.DataFrame,
    phase_dir: Path,
    source_phase5_csv: Path,
    target_column: str = TARGET_COLUMN,
    progress_callback: ProgressCallback | None = None,
) -> PhaseAnalysisOutputs:
    phase_dir.mkdir(parents=True, exist_ok=True)
    phase6_csv = phase_dir / "phase6.csv"
    phase6_xlsx = phase_dir / "phase6.xlsx"

    phase5_df.to_csv(phase6_csv, index=False)
    phase5_df.to_excel(phase6_xlsx, index=False)

    target_folder_name, base_name = build_target_names(target_column)
    target_dir = phase_dir / target_folder_name
    prepared_df = prepare_analysis_dataframe(phase5_df, target_column)
    _, _, analysis_csv, _ = write_phase_analysis_inputs(target_dir, base_name, prepared_df)

    pid, job_info, workspace_dir = launch_featurehero(
        analysis_csv,
        target_dir,
        target_column,
        progress_callback=progress_callback,
    )
    model_id = time.strftime("%Y%m%d-%H%M%S")
    outputs = persist_model_artifacts(
        model_id=model_id,
        target_dir=target_dir,
        target_column=target_column,
        base_name=base_name,
        workspace_dir=workspace_dir,
        job_info=job_info,
        source_phase5_csv=source_phase5_csv,
    )

    analysis_summary = {
        "pid": pid,
        "workspace_dir": str(workspace_dir),
        "model_id": outputs.model_id,
        "description": outputs.description,
        "target_column": target_column,
    }
    (phase_dir / "summary.json").write_text(
        json.dumps(analysis_summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return outputs
