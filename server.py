#!/usr/bin/env python3
from __future__ import annotations

if __package__ in {None, ""}:
    import sys
    from pathlib import Path

    APP_BOOT_DIR = Path(__file__).resolve().parent
    PACKAGE_PARENT = APP_BOOT_DIR
    if str(PACKAGE_PARENT) not in sys.path:
        sys.path.insert(0, str(PACKAGE_PARENT))

import argparse
import contextlib
import csv
import http.server
import io
import json
import math
import mimetypes
import os
import pickle
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
import zipfile
from functools import partial
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.parse import parse_qs
from xml.sax.saxutils import escape

from pipeline.africa_country_localities import (
    list_african_countries,
    sample_country_localities,
    sample_localities_within_bounds,
)
from config_env import (
    get_featurehero_settings,
    get_app_version,
    get_preprocess_validation_enabled,
    get_ce_pipeline_download_enabled,
    get_training_results_download_dev_enabled,
    load_app_env,
    update_featurehero_settings,
)
from pipeline.nasa_country_region import (
    build_country_bounds_payload,
    build_manual_bounds_payload,
    build_manual_grid_payload,
    list_supported_country_bounds,
)
from pipeline.model_registry import (
    build_download_url,
    delete_registered_model,
    get_registered_model,
    list_models_for_ui,
    rename_registered_model,
    write_model_metadata,
)
from pipeline.manual_grid_interpolation import (
    build_manual_grid_interpolated_surface,
)
from workbook_preview import (
    build_original_feature_collection_from_xlsx,
    describe_distinct_germplasm_names_from_xlsx,
    describe_workbook_columns,
    list_distinct_germplasm_names_from_xlsx,
    validate_required_workbook_headers,
)


APP_DIR = Path(__file__).resolve().parent
ROOT_DIR = APP_DIR.parent
APP_URL_PATH = "/app/"
PIPELINE_DIR = APP_DIR / "pipeline"
CE_PIPELINE_DIR = APP_DIR / "ce_pipeline"
CE_PHASE01_SCRIPT = CE_PIPELINE_DIR / "phase01" / "phase1.py"
CE_PHASE02_SCRIPT = CE_PIPELINE_DIR / "phase02" / "phase02.py"
CE_PHASE03_SCRIPT = CE_PIPELINE_DIR / "phase03" / "script03.py"
CE_PHASE04_SCRIPT = CE_PIPELINE_DIR / "phase04" / "phase04.py"
CE_TRAINING_SCRIPT = CE_PIPELINE_DIR / "training.py"
CE_PHASE06_SCRIPT = CE_PIPELINE_DIR / "phase06" / "phase06.py"
TOP_GERMPLASM_ENABLED = False
APP_RUNTIME_NAME = "MictlanAgriXGBoost"
def get_preferred_pipeline_pythons() -> list[Path | None]:
    return [
        Path(os.environ.get("APP_PIPELINE_PYTHON", "")).expanduser()
        if os.environ.get("APP_PIPELINE_PYTHON")
        else None,
        APP_DIR / "resources" / "featurehero" / ".venv" / "bin" / "python",
        Path(sys.executable).resolve(),
    ]


def resolve_runtime_root() -> Path:
    override = os.environ.get("APP_RUNTIME_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()

    home = Path.home()
    system = os.name
    if system == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
        if local_app_data:
            return Path(local_app_data) / APP_RUNTIME_NAME
        return home / "AppData" / "Local" / APP_RUNTIME_NAME

    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / APP_RUNTIME_NAME

    xdg_data_home = os.environ.get("XDG_DATA_HOME", "").strip()
    if xdg_data_home:
        return Path(xdg_data_home).expanduser() / APP_RUNTIME_NAME
    return home / ".local" / "share" / APP_RUNTIME_NAME


PIPELINE_RUNS_DIR = resolve_runtime_root() / "pipeline_runs"
PIPELINE_JOBS: dict[str, dict[str, object]] = {}
PIPELINE_JOBS_LOCK = threading.Lock()
CE_SUMMARY_JOBS: dict[str, dict[str, object]] = {}
CE_SUMMARY_JOBS_LOCK = threading.Lock()
FEATUREHERO_JOBS_FILE = Path.home() / ".featurehero" / "jobs.pids"
DG_HEADER_PATTERN = re.compile(r"^DG\d+$", re.IGNORECASE)
PIPELINE_FINISHED_JOB_RETENTION_SECONDS = 6 * 60 * 60
PIPELINE_FAILED_RUN_DIR_RETENTION_SECONDS = 12 * 60 * 60

load_app_env()


def _safe_close_handle(handle: object) -> None:
    close = getattr(handle, "close", None)
    if callable(close):
        with contextlib.suppress(Exception):
            close()


def _write_pipeline_progress_status(run_dir: Path, *, status: str, message: str) -> None:
    progress_file = run_dir / "progress.json"
    payload: dict[str, object] = {}
    if progress_file.exists():
        with contextlib.suppress(OSError, json.JSONDecodeError):
            payload = json.loads(progress_file.read_text(encoding="utf-8"))
    payload.update({
        "status": status,
        "message": message,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    })
    with contextlib.suppress(OSError):
        progress_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def reap_finished_pipeline_jobs(*, remove_expired: bool = True) -> None:
    now = time.time()
    expired_job_ids: list[str] = []
    with PIPELINE_JOBS_LOCK:
        for job_id, job in list(PIPELINE_JOBS.items()):
            process = job.get("process")
            return_code: int | None = None
            if process is not None:
                with contextlib.suppress(Exception):
                    return_code = process.poll()
                if return_code is not None:
                    _safe_close_handle(job.get("stdout_handle"))
                    _safe_close_handle(job.get("stderr_handle"))
                    job["process"] = None
                    job["stdout_handle"] = None
                    job["stderr_handle"] = None
                    job["finished_at"] = now
                    if return_code == 0:
                        progress_file = Path(job.get("run_dir", "")) / "progress.json"
                        progress_status = "completed"
                        if progress_file.exists():
                            with contextlib.suppress(OSError, json.JSONDecodeError):
                                progress_payload = json.loads(progress_file.read_text(encoding="utf-8"))
                                progress_status = str(progress_payload.get("status") or progress_status)
                        job["final_status"] = progress_status
                    else:
                        job["final_status"] = "error"
            if not remove_expired:
                continue
            finished_at = float(job.get("finished_at") or 0)
            final_status = str(job.get("final_status") or "").strip()
            if finished_at and final_status and final_status != "paused" and now - finished_at > PIPELINE_FINISHED_JOB_RETENTION_SECONDS:
                expired_job_ids.append(job_id)
        for job_id in expired_job_ids:
            PIPELINE_JOBS.pop(job_id, None)


def cleanup_stale_pipeline_run_dirs() -> None:
    if not PIPELINE_RUNS_DIR.exists():
        return
    now = time.time()
    with PIPELINE_JOBS_LOCK:
        active_run_dirs = {
            str(Path(job.get("run_dir", "")).resolve())
            for job in PIPELINE_JOBS.values()
            if str(job.get("run_dir", "")).strip()
        }
    for run_dir in PIPELINE_RUNS_DIR.iterdir():
        if not run_dir.is_dir():
            continue
        if str(run_dir.resolve()) in active_run_dirs:
            continue
        age_seconds = now - run_dir.stat().st_mtime
        if age_seconds < PIPELINE_FAILED_RUN_DIR_RETENTION_SECONDS:
            continue
        summary_path = run_dir / "summary.json"
        progress_path = run_dir / "progress.json"
        progress_status = ""
        if progress_path.exists():
            with contextlib.suppress(OSError, json.JSONDecodeError):
                progress_payload = json.loads(progress_path.read_text(encoding="utf-8"))
                progress_status = str(progress_payload.get("status") or "").strip()
        should_remove = progress_status in {"error", "cancelled"} or not summary_path.exists()
        if should_remove:
            with contextlib.suppress(OSError):
                shutil.rmtree(run_dir)


def get_active_pipeline_job_count() -> int:
    reap_finished_pipeline_jobs()
    with PIPELINE_JOBS_LOCK:
        jobs = list(PIPELINE_JOBS.values())
    active_total = 0
    for job in jobs:
        process = job.get("process")
        if process is None:
            continue
        try:
            if process.poll() is None:
                active_total += 1
        except Exception:
            continue
    return active_total


def get_active_featurehero_jobs() -> dict[str, object]:
    featurehero_jobs: dict[str, object] = {}
    if FEATUREHERO_JOBS_FILE.exists():
        try:
            featurehero_jobs = json.loads(FEATUREHERO_JOBS_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            featurehero_jobs = {}

    active_featurehero_jobs: dict[str, object] = {}
    for pid_text, info in featurehero_jobs.items():
        try:
            pid = int(pid_text)
        except (TypeError, ValueError):
            continue
        try:
            os.kill(pid, 0)
            active_featurehero_jobs[pid_text] = info
        except ProcessLookupError:
            continue
        except PermissionError:
            active_featurehero_jobs[pid_text] = info

    if active_featurehero_jobs != featurehero_jobs:
        try:
            FEATUREHERO_JOBS_FILE.parent.mkdir(parents=True, exist_ok=True)
            FEATUREHERO_JOBS_FILE.write_text(
                json.dumps(active_featurehero_jobs, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass
    return active_featurehero_jobs


def _read_saved_model_selection_summary(metadata: dict[str, object], model_dir: Path) -> dict[str, object]:
    inline_summary = metadata.get("selection_summary")
    if isinstance(inline_summary, dict):
        return inline_summary

    candidate_paths = [
        str(metadata.get("selection_summary_file") or "").strip(),
        str(model_dir / "selection_summary.json"),
    ]
    for candidate in candidate_paths:
        if not candidate:
            continue
        summary_path = Path(candidate)
        if summary_path.exists():
            return json.loads(summary_path.read_text(encoding="utf-8"))
    return {}


def _build_required_division_headers(selection_summary: dict[str, object]) -> list[str]:
    divisions = selection_summary.get("divisions", {}) if isinstance(selection_summary, dict) else {}
    ordered: list[str] = []
    seen: set[str] = set()
    for key in ("germplams_identifiers", "DG", "categorical_data", "cuantitative_data"):
        values = divisions.get(key, []) if isinstance(divisions.get(key), list) else []
        for value in values:
            header = str(value or "").strip()
            if not header or header in seen:
                continue
            seen.add(header)
            ordered.append(header)
    return ordered


def _normalize_header_name(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\u00a0", " ")).strip().casefold()


def _find_missing_headers(required_headers: list[str], actual_headers: list[str]) -> list[str]:
    actual_lookup = {_normalize_header_name(header) for header in actual_headers}
    return [header for header in required_headers if _normalize_header_name(header) not in actual_lookup]


def validate_saved_model_prediction_workbook_for_names(
    workbook_path: Path,
    *,
    selected_model_id: str,
    climate_scope: str = "regional_manual",
) -> None:
    del climate_scope
    registered_model = get_registered_model(selected_model_id)
    if registered_model is None:
        raise FileNotFoundError(f"The selected Grain Yield model was not found: {selected_model_id}")

    selection_summary = _read_saved_model_selection_summary(
        registered_model.metadata,
        registered_model.model_dir,
    )
    required_headers = _build_required_division_headers(selection_summary)
    if not required_headers:
        return

    workbook_description = describe_workbook_columns(workbook_path)
    actual_headers = [str(value or "").strip() for value in workbook_description.get("headers", [])]
    missing_headers = _find_missing_headers(required_headers, actual_headers)
    if missing_headers:
        raise ValueError(
            "The uploaded workbook does not match the saved-model stepper definition. Missing required columns:\n- "
            + "\n- ".join(missing_headers)
        )
    if _normalize_header_name("Name") not in {_normalize_header_name(header) for header in actual_headers}:
        raise ValueError("The uploaded workbook does not contain the required Name column.")


def sanitize_json_payload(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): sanitize_json_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_json_payload(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_json_payload(item) for item in value]
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return value


def write_json_file_atomic(target_path: Path, payload: object) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target_path.with_suffix(target_path.suffix + ".tmp")
    sanitized_payload = sanitize_json_payload(payload)
    temp_path.write_text(
        json.dumps(sanitized_payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(target_path)


def read_json_file_safe(target_path: Path) -> dict[str, object]:
    raw_text = target_path.read_text(encoding="utf-8").strip()
    if not raw_text:
        raise ValueError(f"The JSON file is empty: {target_path}")
    payload = json.loads(raw_text)
    if not isinstance(payload, dict):
        raise ValueError(f"The JSON file does not contain an object: {target_path}")
    return payload


def resolve_ce_training_results_download_path(run_dir: Path) -> Path:
    training_summary_file = run_dir / "ce_pipeline" / "training" / "summary.json"
    if training_summary_file.exists():
        training_summary = read_json_file_safe(training_summary_file)
        prediction_xlsx = Path(str(training_summary.get("prediction_xlsx", "")).strip())
        if prediction_xlsx.exists() and prediction_xlsx.is_file():
            return prediction_xlsx
    result_summary_file = run_dir / "ce_summary_result.json"
    if result_summary_file.exists():
        result_payload = read_json_file_safe(result_summary_file)
        training_summary = result_payload.get("training_summary", {}) if isinstance(result_payload, dict) else {}
        prediction_xlsx = Path(str((training_summary or {}).get("prediction_xlsx", "")).strip())
        if prediction_xlsx.exists() and prediction_xlsx.is_file():
            return prediction_xlsx
    raise FileNotFoundError("The training prediction workbook is not available for this run.")


def excel_column_name(column_index: int) -> str:
    result = ""
    current = max(1, int(column_index))
    while current > 0:
        current, remainder = divmod(current - 1, 26)
        result = chr(65 + remainder) + result
    return result


def build_xlsx_from_tabular_rows(headers: list[str], rows: list[list[object]], output_file: Path) -> Path:
    if not headers:
        raise FileNotFoundError("No headers were available for workbook export.")

    def build_cell_xml(cell_ref: str, value: object) -> str:
        if value is None:
            return f'<c r="{cell_ref}"/>'
        if isinstance(value, bool):
            return f'<c r="{cell_ref}" t="b"><v>{1 if value else 0}</v></c>'
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
                escaped = escape(str(value))
                return f'<c r="{cell_ref}" t="inlineStr"><is><t>{escaped}</t></is></c>'
            return f'<c r="{cell_ref}"><v>{value}</v></c>'
        escaped = escape(str(value))
        return f'<c r="{cell_ref}" t="inlineStr"><is><t>{escaped}</t></is></c>'

    all_rows = [headers, *rows]
    sheet_rows: list[str] = []
    for row_index, row_values in enumerate(all_rows, start=1):
        cells: list[str] = []
        for column_index, value in enumerate(row_values, start=1):
            cell_ref = f"{excel_column_name(column_index)}{row_index}"
            cells.append(build_cell_xml(cell_ref, value))
        sheet_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')

    worksheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(sheet_rows)}</sheetData>'
        '</worksheet>'
    )
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Training Results" sheetId="1" r:id="rId1"/></sheets>'
        '</workbook>'
    )
    workbook_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        '</Relationships>'
    )
    root_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '</Relationships>'
    )
    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        '</Types>'
    )
    styles_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>'
        '<fills count="1"><fill><patternFill patternType="none"/></fill></fills>'
        '<borders count="1"><border/></borders>'
        '<cellStyleXfs count="1"><xf/></cellStyleXfs>'
        '<cellXfs count="1"><xf xfId="0"/></cellXfs>'
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        '</styleSheet>'
    )

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_file, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', content_types_xml)
        archive.writestr('_rels/.rels', root_rels_xml)
        archive.writestr('xl/workbook.xml', workbook_xml)
        archive.writestr('xl/_rels/workbook.xml.rels', workbook_rels_xml)
        archive.writestr('xl/styles.xml', styles_xml)
        archive.writestr('xl/worksheets/sheet1.xml', worksheet_xml)
    return output_file


def build_workbook_from_feature_collection(feature_collection: object, output_file: Path) -> Path:
    if not isinstance(feature_collection, dict):
        raise FileNotFoundError("The training feature collection is not available for workbook export.")
    features = feature_collection.get("features", [])
    if not isinstance(features, list) or not features:
        raise FileNotFoundError("The training feature collection is empty for workbook export.")
    normalized_rows: list[dict[str, object]] = []
    headers_in_order: list[str] = []
    seen_headers: set[str] = set()
    for feature in features:
        if not isinstance(feature, dict):
            continue
        properties = feature.get("properties", {})
        row = dict(properties) if isinstance(properties, dict) else {}
        coordinates = feature.get("geometry", {}).get("coordinates", []) if isinstance(feature.get("geometry"), dict) else []
        if isinstance(coordinates, list) and len(coordinates) >= 2:
            row.setdefault("_GPS coordinates_longitude", coordinates[0])
            row.setdefault("_GPS coordinates_latitude", coordinates[1])
        normalized_rows.append(row)
        for key in row.keys():
            if key not in seen_headers:
                seen_headers.add(key)
                headers_in_order.append(str(key))
    if not normalized_rows or not headers_in_order:
        raise FileNotFoundError("The training feature collection did not contain exportable rows.")
    row_values = [[row.get(header) for header in headers_in_order] for row in normalized_rows]
    return build_xlsx_from_tabular_rows(headers_in_order, row_values, output_file)


def resolve_workspace_training_results_file(registered_model) -> tuple[Path, str]:
    metadata = registered_model.metadata
    model_id = registered_model.model_id
    copied_file = Path(
        str(metadata.get("workspace_training_results_file") or registered_model.model_dir / "workspace_training_results.xlsx")
    )
    if copied_file.exists() and copied_file.is_file():
        return copied_file, copied_file.name
    training_summary_file = Path(
        str(metadata.get("workspace_training_summary_file") or registered_model.model_dir / "workspace_training_summary.json")
    )
    training_summary = read_json_file_safe(training_summary_file) if training_summary_file.exists() else {}
    prediction_xlsx = Path(str(training_summary.get("prediction_xlsx", "")).strip())
    if prediction_xlsx.exists() and prediction_xlsx.is_file():
        target_file = registered_model.model_dir / prediction_xlsx.name
        if prediction_xlsx.resolve() != target_file.resolve():
            shutil.copy2(prediction_xlsx, target_file)
        return target_file, target_file.name
    training_geojson_file = Path(
        str(metadata.get("workspace_training_geojson_file") or registered_model.model_dir / "workspace_training_geojson.json")
    )
    if training_geojson_file.exists():
        feature_collection = read_json_file_safe(training_geojson_file)
        generated_file = registered_model.model_dir / "workspace_training_results.xlsx"
        build_workbook_from_feature_collection(feature_collection, generated_file)
        return generated_file, generated_file.name
    raise FileNotFoundError("The training results workbook was not found for this workspace.")


def write_ce_summary_progress(
    progress_file: Path,
    *,
    status: str,
    percent: int,
    stage: str,
    message: str,
    details: dict[str, object] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "status": status,
        "percent": max(0, min(100, int(percent))),
        "stage": stage,
        "message": message,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    if details:
        payload["details"] = details
    write_json_file_atomic(progress_file, payload)
    return payload


def format_called_process_error(error: subprocess.CalledProcessError) -> str:
    stderr_text = (error.stderr or "").strip()
    stdout_text = (error.stdout or "").strip()
    if stderr_text:
        return stderr_text.splitlines()[-1]
    if stdout_text:
        return stdout_text.splitlines()[-1]
    return str(error)


def is_thread_alive(thread: object) -> bool:
    return isinstance(thread, threading.Thread) and thread.is_alive()


def is_truthy_flag(raw_value: str) -> bool:
    return str(raw_value or "").strip().lower() in {"1", "true", "yes", "on"}


def build_ce_pipeline_summary(
    *,
    source_name: str,
    phase3_path: Path,
    phase1_payload: dict[str, object],
    phase2_payload: dict[str, object],
    phase3_payload: dict[str, object],
    selection_summary: dict[str, object],
) -> dict[str, object]:
    initial_settings = selection_summary.get("initial_settings", {})
    divisions = selection_summary.get("divisions", {})
    phase2_removed_by_reason = phase2_payload.get("removed_by_reason", {}) if isinstance(phase2_payload, dict) else {}
    phase3_nasa = phase3_payload.get("nasa", {}) if isinstance(phase3_payload, dict) else {}
    summary = {
        "workflow": "ce_pipeline",
        "source_name": source_name,
        "phase03_xlsx": str(phase3_path),
        "initial_settings": initial_settings,
        "divisions": divisions,
        "ce_pipeline_log": {
            "overview": {
                "input_rows": int(phase1_payload.get("row_count", 0) or 0),
                "phase02_kept_rows": int(phase2_payload.get("kept_row_count", 0) or 0),
                "phase03_output_rows": int(phase3_payload.get("output_row_count", 0) or 0),
                "nasa_unique_queries": int(phase3_nasa.get("nasa_unique_queries", 0) or 0),
            },
            "quality_filters": {
                "missing_required_initial_settings": int(phase2_removed_by_reason.get("missing_required_initial_settings", 0) or 0),
                "invalid_target_value": int(phase2_removed_by_reason.get("invalid_target_value", 0) or 0),
                "invalid_initial_setting_dates": int(phase2_removed_by_reason.get("invalid_initial_setting_dates", 0) or 0),
                "water_or_lake_point": int(phase2_removed_by_reason.get("water_or_lake_point", 0) or 0),
            },
            "climate": {
                "source_rows": int(phase2_payload.get("kept_row_count", 0) or 0),
                "climate_input_rows": int(phase3_nasa.get("total_rows", 0) or 0),
                "matched_rows": int(phase3_payload.get("output_row_count", 0) or 0),
                "nasa_cache_hits": int(phase3_nasa.get("nasa_cache_hits", 0) or 0),
                "nasa_fresh_queries_this_run": int(phase3_nasa.get("nasa_cache_fresh_queries_this_run", 0) or 0),
                "soil_skipped": bool((phase3_payload.get("soil", {}) if isinstance(phase3_payload, dict) else {}).get("soil_enrichment_skipped", False)),
            },
        },
    }
    return summary


def is_valid_feature_collection(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    if payload.get("type") != "FeatureCollection":
        return False
    features = payload.get("features")
    if not isinstance(features, list) or not features:
        return False
    for feature in features:
        if not isinstance(feature, dict):
            return False
        geometry = feature.get("geometry")
        if not isinstance(geometry, dict):
            return False
        coordinates = geometry.get("coordinates")
        if (
            not isinstance(coordinates, list)
            or len(coordinates) < 2
            or coordinates[0] in {None, ""}
            or coordinates[1] in {None, ""}
        ):
            return False
    return True


def rebuild_feature_collection_from_workbook(workbook_path: Path) -> dict[str, object] | None:
    if not workbook_path.exists():
        return None
    try:
        rebuilt = build_original_feature_collection_from_xlsx(workbook_path)
    except (OSError, ValueError):
        return None
    if is_valid_feature_collection(rebuilt):
        return rebuilt
    return None


def build_selection_workspace_state(selection_summary: dict[str, object]) -> dict[str, object]:
    initial_settings = selection_summary.get("initial_settings", {}) if isinstance(selection_summary, dict) else {}
    divisions = selection_summary.get("divisions", {}) if isinstance(selection_summary, dict) else {}
    headers = [
        str(header or "").strip()
        for header in (selection_summary.get("headers", []) if isinstance(selection_summary, dict) else [])
        if str(header or "").strip()
    ]
    identifier_columns = [
        str(value or "").strip()
        for value in (divisions.get("germplams_identifiers", []) if isinstance(divisions.get("germplams_identifiers"), list) else [])
        if str(value or "").strip()
    ]
    categorical_columns = [
        str(value or "").strip()
        for value in (divisions.get("categorical_data", []) if isinstance(divisions.get("categorical_data"), list) else [])
        if str(value or "").strip()
    ]
    quantitative_columns = [
        str(value or "").strip()
        for value in (divisions.get("cuantitative_data", []) if isinstance(divisions.get("cuantitative_data"), list) else [])
        if str(value or "").strip()
    ]
    no_defined_columns = [
        str(value or "").strip()
        for value in (divisions.get("no_defined_data", []) if isinstance(divisions.get("no_defined_data"), list) else [])
        if str(value or "").strip()
    ]
    dg_columns = {
        str(value or "").strip()
        for value in (divisions.get("DG", []) if isinstance(divisions.get("DG"), list) else [])
        if str(value or "").strip()
    }
    reserved_columns = {
        str(initial_settings.get("target_column", "")).strip(),
        str(initial_settings.get("longitude_column", "")).strip(),
        str(initial_settings.get("latitude_column", "")).strip(),
        str(initial_settings.get("planting_date_column", "")).strip(),
        str(initial_settings.get("harvesting_date_column", "")).strip(),
        str(initial_settings.get("soil_texture_column", "")).strip(),
        str(initial_settings.get("soil_depth_column", "")).strip(),
        *identifier_columns,
        *dg_columns,
    }
    available_classifier_columns = [header for header in headers if header not in reserved_columns]
    column_assignments: dict[str, str] = {}
    enabled_columns: list[str] = []
    enabled_set: set[str] = set()
    for column in categorical_columns:
        if column in available_classifier_columns:
            column_assignments[column] = "categorical"
            if column not in enabled_set:
                enabled_columns.append(column)
                enabled_set.add(column)
    for column in quantitative_columns:
        if column in available_classifier_columns:
            column_assignments[column] = "quantitative"
            if column not in enabled_set:
                enabled_columns.append(column)
                enabled_set.add(column)
    for column in no_defined_columns:
        if column in available_classifier_columns and column not in column_assignments:
            column_assignments[column] = "no_defined"
    return {
        "workspaceName": str(selection_summary.get("workspace_name", "")).strip(),
        "sourceName": str(selection_summary.get("source_name", "")).strip(),
        "headers": headers,
        "columnProfiles": selection_summary.get("column_profiles", {}) if isinstance(selection_summary.get("column_profiles"), dict) else {},
        "rowCount": int(selection_summary.get("row_count", 0) or 0),
        "attributeCount": int(selection_summary.get("attribute_count", 0) or len(headers) or 0),
        "targetColumn": str(initial_settings.get("target_column", "")).strip(),
        "longitudeColumn": str(initial_settings.get("longitude_column", "")).strip(),
        "latitudeColumn": str(initial_settings.get("latitude_column", "")).strip(),
        "plantingDateColumn": str(initial_settings.get("planting_date_column", "")).strip(),
        "harvestingDateColumn": str(initial_settings.get("harvesting_date_column", "")).strip(),
        "soilTextureColumn": str(initial_settings.get("soil_texture_column", "")).strip(),
        "soilDepthColumn": str(initial_settings.get("soil_depth_column", "")).strip(),
        "identifierColumns": identifier_columns,
        "identifierConfirmed": True,
        "categoricalColumns": categorical_columns,
        "quantitativeColumns": quantitative_columns,
        "noDefinedColumns": no_defined_columns,
        "columnAssignments": column_assignments,
        "enabledClassifierColumns": enabled_columns,
        "columnClassificationConfirmed": True,
        "summaryReady": True,
        "activeStep": "summary",
        "latestSummaryRun": None,
    }


def persist_workspace_artifacts(
    *,
    model_dir: Path,
    metadata: dict[str, object],
    selection_summary: dict[str, object],
    source_workbook_path: Path | None,
    original_geojson: dict[str, object],
    original_summary: dict[str, object],
    training_geojson: dict[str, object],
    training_summary: dict[str, object],
    prediction_geojson: dict[str, object],
    prediction_summary: dict[str, object],
    top_germplasm_geojson: dict[str, object] | None = None,
    top_germplasm_summary: dict[str, object] | None = None,
) -> dict[str, object]:
    updated_metadata = dict(metadata)
    workspace_name = str(selection_summary.get("workspace_name", "")).strip()
    if workspace_name:
        updated_metadata["display_name"] = workspace_name
        updated_metadata["workspace_name"] = workspace_name

    saved_source_workbook: Path | None = None
    if source_workbook_path is not None and source_workbook_path.exists():
        saved_source_workbook = model_dir / f"workspace_source{source_workbook_path.suffix or '.xlsx'}"
        shutil.copy2(source_workbook_path, saved_source_workbook)
        updated_metadata["workspace_source_workbook"] = str(saved_source_workbook)

    original_geojson_path = model_dir / "workspace_original_geojson.json"
    original_summary_path = model_dir / "workspace_original_summary.json"
    training_geojson_path = model_dir / "workspace_training_geojson.json"
    training_summary_path = model_dir / "workspace_training_summary.json"
    prediction_geojson_path = model_dir / "workspace_prediction_geojson.json"
    prediction_summary_path = model_dir / "workspace_prediction_summary.json"
    top_germplasm_geojson_path = model_dir / "workspace_top_germplasm_geojson.json"
    top_germplasm_summary_path = model_dir / "workspace_top_germplasm_summary.json"
    top_germplasm_download_path: Path | None = None
    training_results_download_path: Path | None = None
    workspace_payload_path = model_dir / "workspace_payload.json"

    model_id_for_download = str(updated_metadata.get("model_id") or model_dir.name).strip()
    training_results_source_value = str((training_summary or {}).get("prediction_xlsx", "")).strip()
    if training_results_source_value:
        training_results_source = Path(training_results_source_value)
        if training_results_source.exists() and training_results_source.is_file():
            training_results_download_path = model_dir / training_results_source.name
            if training_results_source.resolve() != training_results_download_path.resolve():
                shutil.copy2(training_results_source, training_results_download_path)
            updated_metadata["workspace_training_results_file"] = str(training_results_download_path)
            training_summary = dict(training_summary)
            training_summary["prediction_xlsx"] = str(training_results_download_path)
    normalized_training_summary = normalize_training_summary_download(training_summary, model_id=model_id_for_download)
    write_json_file_atomic(original_geojson_path, original_geojson)
    write_json_file_atomic(original_summary_path, original_summary)
    write_json_file_atomic(training_geojson_path, training_geojson)
    write_json_file_atomic(training_summary_path, normalized_training_summary)
    write_json_file_atomic(prediction_geojson_path, prediction_geojson)
    write_json_file_atomic(prediction_summary_path, prediction_summary)
    training_summary = normalized_training_summary
    if top_germplasm_geojson is not None:
        write_json_file_atomic(top_germplasm_geojson_path, top_germplasm_geojson)
        updated_metadata["workspace_top_germplasm_geojson_file"] = str(top_germplasm_geojson_path)
    if top_germplasm_summary is not None:
        normalized_top_summary = dict(top_germplasm_summary)
        top_download_source_value = str(normalized_top_summary.get("top_germplasm_xlsx", "")).strip()
        if top_download_source_value:
            top_download_source = Path(top_download_source_value)
            if top_download_source.exists() and top_download_source.is_file():
                top_germplasm_download_path = model_dir / top_download_source.name
                shutil.copy2(top_download_source, top_germplasm_download_path)
                normalized_top_summary["top_germplasm_xlsx"] = str(top_germplasm_download_path)
                model_id_for_download = str(updated_metadata.get("model_id") or model_dir.name).strip()
                normalized_top_summary["download_url"] = f"/api/models/{model_id_for_download}/top-germplasm.xlsx" if model_id_for_download else ""
                normalized_top_summary["download_file_name"] = top_germplasm_download_path.name
                updated_metadata["workspace_top_germplasm_download_file"] = str(top_germplasm_download_path)
        write_json_file_atomic(top_germplasm_summary_path, normalized_top_summary)
        top_germplasm_summary = normalized_top_summary
        updated_metadata["workspace_top_germplasm_summary_file"] = str(top_germplasm_summary_path)

    updated_metadata["workspace_original_geojson_file"] = str(original_geojson_path)
    updated_metadata["workspace_original_summary_file"] = str(original_summary_path)
    updated_metadata["workspace_training_geojson_file"] = str(training_geojson_path)
    updated_metadata["workspace_training_summary_file"] = str(training_summary_path)
    updated_metadata["workspace_prediction_geojson_file"] = str(prediction_geojson_path)
    updated_metadata["workspace_prediction_summary_file"] = str(prediction_summary_path)

    normalization_stats_file = Path(
        str(updated_metadata.get("phase04_normalization_stats_file") or model_dir / "phase04_normalization_stats.json")
    )
    normalization_stats_payload = read_json_file_safe(normalization_stats_file) if normalization_stats_file.exists() else {}

    workspace_payload = {
        "model_id": str(updated_metadata.get("model_id") or model_dir.name),
        "workspace_name": workspace_name or str(updated_metadata.get("display_name") or model_dir.name),
        "selection_summary": selection_summary,
        "selection_state": build_selection_workspace_state(selection_summary),
        "source_workbook": {
            "file": str(saved_source_workbook) if saved_source_workbook is not None else str(source_workbook_path or ""),
            "url": f"/api/models/{str(updated_metadata.get('model_id') or model_dir.name).strip()}/source-workbook.xlsx" if str(updated_metadata.get('model_id') or model_dir.name).strip() else "",
            "name": str(selection_summary.get("source_name", "")).strip(),
        },
        "normalization_stats": {
            "file": str(normalization_stats_file) if normalization_stats_file.exists() else "",
            "columns": normalization_stats_payload,
            "column_count": len(normalization_stats_payload),
            "source": "workspace_training",
        },
        "original_dataset": {
            "source_name": str(original_summary.get("phase03_xlsx", "")).strip() or str(selection_summary.get("source_name", "")).strip(),
            "geojson": original_geojson,
            "summary": original_summary,
            "geojson_file": str(original_geojson_path),
            "summary_file": str(original_summary_path),
        },
        "training_dataset": {
            "source_name": str(training_summary.get("phase04_xlsx", "")).strip() or str(selection_summary.get("source_name", "")).strip(),
            "geojson": training_geojson,
            "summary": training_summary,
            "geojson_file": str(training_geojson_path),
            "summary_file": str(training_summary_path),
            "download_file": str(training_results_download_path) if training_results_download_path is not None else str(training_summary.get("prediction_xlsx", "")).strip(),
        },
        "prediction_dataset": {
            "source_name": str(prediction_summary.get("prediction_xlsx", "")).strip() or str(selection_summary.get("source_name", "")).strip(),
            "geojson": prediction_geojson,
            "summary": prediction_summary,
            "geojson_file": str(prediction_geojson_path),
            "summary_file": str(prediction_summary_path),
        },
    }
    if top_germplasm_geojson is not None or top_germplasm_summary is not None:
        workspace_payload["top_germplasm_dataset"] = {
            "source_name": str((top_germplasm_summary or {}).get("download_file_name", "")).strip() or str((top_germplasm_summary or {}).get("top_germplasm_xlsx", "")).strip() or str(selection_summary.get("source_name", "")).strip(),
            "geojson": top_germplasm_geojson or {},
            "summary": top_germplasm_summary or {},
            "geojson_file": str(top_germplasm_geojson_path),
            "summary_file": str(top_germplasm_summary_path),
            "download_file": str(top_germplasm_download_path) if top_germplasm_download_path is not None else str((top_germplasm_summary or {}).get("top_germplasm_xlsx", "")),
        }
    write_json_file_atomic(workspace_payload_path, workspace_payload)
    updated_metadata["workspace_payload_file"] = str(workspace_payload_path)
    write_model_metadata(model_dir, updated_metadata)
    return updated_metadata


def read_saved_workspace_payload(registered_model) -> dict[str, object]:
    metadata = registered_model.metadata
    payload_path = Path(str(metadata.get("workspace_payload_file") or registered_model.model_dir / "workspace_payload.json"))
    if payload_path.exists():
        payload = read_json_file_safe(payload_path)
        if isinstance(payload, dict):
            return payload
    raise FileNotFoundError("The workspace payload was not found for this saved workspace.")


def build_workspace_payload_response(payload: dict[str, object]) -> dict[str, object]:
    response_payload = dict(payload)
    for dataset_key in ("original_dataset", "training_dataset", "prediction_dataset", "top_germplasm_dataset"):
        dataset = response_payload.get(dataset_key)
        if not isinstance(dataset, dict):
            continue
        dataset_payload = dict(dataset)
        geojson_file = Path(str(dataset_payload.get("geojson_file") or "").strip())
        summary_file = Path(str(dataset_payload.get("summary_file") or "").strip())
        dataset_payload["geojson_url"] = build_download_url(geojson_file) if geojson_file.exists() else ""
        dataset_payload["summary_url"] = build_download_url(summary_file) if summary_file.exists() else ""
        if dataset_key == "training_dataset":
            model_id = str(response_payload.get("model_id") or "").strip()
            dataset_payload["summary"] = normalize_training_summary_download(dataset_payload.get("summary"), model_id=model_id)
            download_file = Path(str(dataset_payload.get("download_file") or "").strip())
            dataset_payload["download_url"] = build_training_results_model_download_url(model_id) if model_id else ""
            dataset_payload["download_file_name"] = download_file.name if download_file.exists() else str((dataset_payload.get("summary") or {}).get("download_file_name", "")).strip()
        response_payload[dataset_key] = dataset_payload
    return response_payload


def build_top_germplasm_run_download_url(run_id: str) -> str:
    normalized_run_id = str(run_id or "").strip()
    return f"/api/process-xlsx/selecction-properties/download?run_id={normalized_run_id}&phase=top_germplasm" if normalized_run_id else ""


def build_top_germplasm_model_download_url(model_id: str) -> str:
    normalized_model_id = str(model_id or "").strip()
    return f"/api/models/{normalized_model_id}/top-germplasm.xlsx" if normalized_model_id else ""


def build_training_results_run_download_url(run_id: str) -> str:
    normalized_run_id = str(run_id or "").strip()
    return f"/api/process-xlsx/selecction-properties/download?run_id={normalized_run_id}&phase=training_results" if normalized_run_id else ""


def build_training_results_model_download_url(model_id: str) -> str:
    normalized_model_id = str(model_id or "").strip()
    return f"/api/models/{normalized_model_id}/training-results.xlsx" if normalized_model_id else ""


def normalize_training_summary_download(summary: object, *, run_id: str = "", model_id: str = "") -> object:
    if not isinstance(summary, dict):
        return summary
    normalized = dict(summary)
    prediction_xlsx = str(normalized.get("prediction_xlsx", "")).strip()
    download_file_name = str(normalized.get("download_file_name", "")).strip()
    if not download_file_name and prediction_xlsx:
        download_file_name = Path(prediction_xlsx).name
        normalized["download_file_name"] = download_file_name
    download_url = str(normalized.get("download_url", "")).strip()
    if not download_url:
        download_url = build_training_results_run_download_url(run_id) or build_training_results_model_download_url(model_id)
        normalized["download_url"] = download_url
    return normalized


def normalize_top_germplasm_summary_download(summary: object, *, run_id: str = "", model_id: str = "") -> object:
    if not isinstance(summary, dict):
        return summary
    normalized = dict(summary)
    download_file_name = str(normalized.get("download_file_name", "")).strip()
    top_germplasm_xlsx = str(normalized.get("top_germplasm_xlsx", "")).strip()
    if not download_file_name and top_germplasm_xlsx:
        download_file_name = Path(top_germplasm_xlsx).name
        normalized["download_file_name"] = download_file_name
    download_url = str(normalized.get("download_url", "")).strip()
    if not download_url:
        download_url = build_top_germplasm_run_download_url(run_id) or build_top_germplasm_model_download_url(model_id)
        normalized["download_url"] = download_url
    return normalized


def normalize_top_germplasm_payload(payload: dict[str, object], *, run_id: str = "", model_id: str = "") -> dict[str, object]:
    normalized = dict(payload)
    top_summary = normalize_top_germplasm_summary_download(normalized.get("top_germplasm_summary"), run_id=run_id, model_id=model_id)
    if isinstance(top_summary, dict):
        normalized["top_germplasm_summary"] = top_summary
    dataset = normalized.get("top_germplasm_dataset")
    if isinstance(dataset, dict):
        normalized_dataset = dict(dataset)
        dataset_summary = normalize_top_germplasm_summary_download(normalized_dataset.get("summary"), run_id=run_id, model_id=model_id)
        if isinstance(dataset_summary, dict):
            normalized_dataset["summary"] = dataset_summary
        normalized["top_germplasm_dataset"] = normalized_dataset
    return normalized


def _as_float(value: object) -> float | None:
    if value in {None, ""}:
        return None
    try:
        numeric = float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


def _build_manual_grid_categorical_label(
    properties: dict[str, object],
    *,
    selected_id_header: str,
    multi_profile_mode: bool,
    multi_germplasm_mode: bool,
) -> str:
    name = str(properties.get("Name") or "").strip()
    normalized_selected_id_header = str(selected_id_header or "").strip()
    selected_id_value = str(properties.get(normalized_selected_id_header) or "").strip() if normalized_selected_id_header else ""
    if normalized_selected_id_header and name and selected_id_value:
        return f"{name} - {selected_id_value}"
    if multi_germplasm_mode and name:
        return name
    if multi_profile_mode:
        profile_label = str(properties.get("Prediction Profile") or properties.get("Prediction Profile Label") or properties.get("Prediction profile label") or "").strip()
        if profile_label:
            return profile_label
    return name or str(properties.get("Prediction Profile") or properties.get("Prediction Profile Label") or properties.get("Prediction profile label") or "").strip()


def _find_prediction_grid_cell_id(
    feature: dict[str, object],
    grid_cells: list[dict[str, object]],
) -> str:
    properties = feature.get("properties", {}) if isinstance(feature, dict) else {}
    explicit_grid_cell_id = str(properties.get("Forecast grid cell id") or "").strip()
    if explicit_grid_cell_id:
        return explicit_grid_cell_id
    geometry = feature.get("geometry", {}) if isinstance(feature, dict) else {}
    coordinates = geometry.get("coordinates", []) if isinstance(geometry, dict) else []
    if not isinstance(coordinates, list) or len(coordinates) < 2:
        return ""
    longitude = _as_float(coordinates[0])
    latitude = _as_float(coordinates[1])
    if longitude is None or latitude is None:
        return ""
    for cell in grid_cells:
        lon_min = _as_float(cell.get("longitude_min"))
        lon_max = _as_float(cell.get("longitude_max"))
        lat_min = _as_float(cell.get("latitude_min"))
        lat_max = _as_float(cell.get("latitude_max"))
        if None in {lon_min, lon_max, lat_min, lat_max}:
            continue
        if lon_min <= longitude <= lon_max and lat_min <= latitude <= lat_max:
            return str(cell.get("grid_cell_id") or "").strip()
    return ""


def _build_manual_grid_prediction_payload(
    summary: dict[str, object],
    geojson: dict[str, object],
) -> tuple[dict[str, object], list[str]]:
    grid_payload = summary.get("manual_bbox_grid")
    grid_cells = grid_payload.get("cells", []) if isinstance(grid_payload, dict) else []
    features = geojson.get("features", []) if isinstance(geojson, dict) else []
    if not isinstance(grid_cells, list) or not grid_cells or not isinstance(features, list):
        return geojson, []

    grouped: dict[str, list[dict[str, object]]] = {}
    distinct_names: list[str] = []
    seen_names: set[str] = set()
    for feature in features:
        if not isinstance(feature, dict):
            continue
        properties = feature.get("properties", {}) if isinstance(feature.get("properties"), dict) else {}
        name = str(properties.get("Name") or "").strip()
        if name and name not in seen_names:
            seen_names.add(name)
            distinct_names.append(name)
        grid_cell_id = _find_prediction_grid_cell_id(feature, grid_cells)
        if not grid_cell_id:
            continue
        grouped.setdefault(grid_cell_id, []).append(feature)

    multi_profile_mode = bool(summary.get("multi_profile_mode"))
    multi_germplasm_mode = len(distinct_names) > 1
    categorical_mode = multi_profile_mode or multi_germplasm_mode
    selected_id_header = str(summary.get("selected_id_header") or "").strip()
    cell_lookup = {
        str(cell.get("grid_cell_id") or "").strip(): cell
        for cell in grid_cells
        if str(cell.get("grid_cell_id") or "").strip()
    }
    compact_features: list[dict[str, object]] = []

    for grid_cell_id, cell_features in grouped.items():
        if not cell_features:
            continue
        cell = cell_lookup.get(grid_cell_id, {})
        center_lon = _as_float(cell.get("center_longitude"))
        center_lat = _as_float(cell.get("center_latitude"))
        if categorical_mode:
            features_by_label: dict[str, list[dict[str, object]]] = {}
            for feature in cell_features:
                properties = feature.get("properties", {}) if isinstance(feature.get("properties"), dict) else {}
                label = _build_manual_grid_categorical_label(
                    properties,
                    selected_id_header=selected_id_header,
                    multi_profile_mode=multi_profile_mode,
                    multi_germplasm_mode=multi_germplasm_mode,
                )
                if not label:
                    continue
                features_by_label.setdefault(label, []).append(feature)
            for label_features in features_by_label.values():
                representative = max(
                    label_features,
                    key=lambda item: _as_float(((item.get("properties") or {}).get("Grain Yield predicted"))) or float("-inf"),
                )
                properties = dict(representative.get("properties", {}) if isinstance(representative.get("properties"), dict) else {})
                properties["Prediction cell row count"] = len(label_features)
                properties["Forecast grid cell id"] = grid_cell_id
                geometry = (
                    {"type": "Point", "coordinates": [center_lon, center_lat]}
                    if center_lon is not None and center_lat is not None
                    else representative.get("geometry", {"type": "Point", "coordinates": []})
                )
                compact_features.append({
                    "type": "Feature",
                    "geometry": geometry,
                    "properties": properties,
                })
        else:
            representative = cell_features[0]
            properties = dict(representative.get("properties", {}) if isinstance(representative.get("properties"), dict) else {})
            values = [
                numeric for numeric in (
                    _as_float(((feature.get("properties") or {}).get("Grain Yield predicted")))
                    for feature in cell_features
                )
                if numeric is not None
            ]
            if values:
                properties["Grain Yield predicted"] = round(sum(values) / len(values), 6)
            properties["Prediction cell replication count"] = len(cell_features)
            properties["Prediction cell row count"] = len(cell_features)
            properties["Forecast grid cell id"] = grid_cell_id
            geometry = (
                {"type": "Point", "coordinates": [center_lon, center_lat]}
                if center_lon is not None and center_lat is not None
                else representative.get("geometry", {"type": "Point", "coordinates": []})
            )
            compact_features.append({
                "type": "Feature",
                "geometry": geometry,
                "properties": properties,
            })

    compact_geojson = {
        "type": "FeatureCollection",
        "metadata": {
            **(geojson.get("metadata", {}) if isinstance(geojson.get("metadata"), dict) else {}),
            "total_features": len(compact_features),
            "source_total_features": len(features),
            "manual_grid_compacted": True,
        },
        "features": compact_features,
    }
    return compact_geojson, distinct_names


def _xlsx_column_name(index: int) -> str:
    name = ""
    current = index
    while current > 0:
        current, remainder = divmod(current - 1, 26)
        name = chr(65 + remainder) + name
    return name or "A"


def _build_simple_xlsx_bytes(headers: list[str], rows: list[list[object]]) -> bytes:
    content_types = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>
"""
    root_rels = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>
"""
    workbook = """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="PredictionCells" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>
"""
    workbook_rels = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>
"""
    styles = """<?xml version="1.0" encoding="UTF-8"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>
  <fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>
  <borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>
  <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>
"""
    core = """<?xml version="1.0" encoding="UTF-8"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>Prediction cells</dc:title>
  <dc:creator>OpenAI Codex</dc:creator>
</cp:coreProperties>
"""
    app = """<?xml version="1.0" encoding="UTF-8"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>OpenAI Codex</Application>
</Properties>
"""

    all_rows = [headers, *rows]
    sheet_rows: list[str] = []
    for row_index, row in enumerate(all_rows, start=1):
        cells: list[str] = []
        for col_index, value in enumerate(row, start=1):
            ref = f"{_xlsx_column_name(col_index)}{row_index}"
            if value is None:
                text_value = ""
                cells.append(f'<c r="{ref}" t="inlineStr"><is><t></t></is></c>')
                continue
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                cells.append(f'<c r="{ref}"><v>{value}</v></c>')
                continue
            text_value = escape(str(value))
            cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{text_value}</t></is></c>')
        sheet_rows.append(f'<row r="{row_index}">' + ''.join(cells) + '</row>')
    worksheet = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetData>' + ''.join(sheet_rows) + '</sheetData>'
        '</worksheet>'
    )

    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', content_types)
        archive.writestr('_rels/.rels', root_rels)
        archive.writestr('xl/workbook.xml', workbook)
        archive.writestr('xl/_rels/workbook.xml.rels', workbook_rels)
        archive.writestr('xl/worksheets/sheet1.xml', worksheet)
        archive.writestr('xl/styles.xml', styles)
        archive.writestr('docProps/core.xml', core)
        archive.writestr('docProps/app.xml', app)
    return output.getvalue()


def _build_manual_grid_prediction_workbook_bytes(summary: dict[str, object]) -> tuple[bytes, str] | None:
    if str(summary.get("climate_scope", "")).strip() != "regional_manual":
        return None
    geojson = resolve_prediction_feature_collection(summary)
    compact_geojson, _ = _build_manual_grid_prediction_payload(summary, geojson)
    source_features = compact_geojson.get("features", []) if isinstance(compact_geojson, dict) else []
    if not isinstance(source_features, list) or not source_features:
        return None

    winners_by_cell: dict[str, dict[str, object]] = {}
    for feature in source_features:
        if not isinstance(feature, dict):
            continue
        properties = feature.get("properties", {}) if isinstance(feature.get("properties"), dict) else {}
        grid_cell_id = str(properties.get("Forecast grid cell id") or "").strip()
        if not grid_cell_id:
            continue
        predicted_value = _as_float(properties.get("Grain Yield predicted"))
        current = winners_by_cell.get(grid_cell_id)
        current_predicted = _as_float(((current or {}).get("properties") or {}).get("Grain Yield predicted")) if current else None
        if current is None or (predicted_value is not None and (current_predicted is None or predicted_value > current_predicted)):
            winners_by_cell[grid_cell_id] = feature

    features = list(winners_by_cell.values()) if winners_by_cell else source_features

    property_keys: list[str] = []
    seen_keys: set[str] = set()
    for feature in features:
        properties = feature.get("properties", {}) if isinstance(feature.get("properties"), dict) else {}
        for key in properties.keys():
            normalized = str(key).strip()
            if normalized and normalized not in seen_keys:
                seen_keys.add(normalized)
                property_keys.append(normalized)

    headers = ["Longitude", "Latitude", *property_keys]
    rows: list[list[object]] = []
    for feature in features:
        geometry = feature.get("geometry", {}) if isinstance(feature.get("geometry"), dict) else {}
        coordinates = geometry.get("coordinates", []) if isinstance(geometry.get("coordinates"), list) else []
        longitude = coordinates[0] if len(coordinates) > 0 else ""
        latitude = coordinates[1] if len(coordinates) > 1 else ""
        properties = feature.get("properties", {}) if isinstance(feature.get("properties"), dict) else {}
        row = [longitude, latitude]
        for key in property_keys:
            row.append(properties.get(key, ""))
        rows.append(row)

    workbook_bytes = _build_simple_xlsx_bytes(headers, rows)
    source_name = Path(str(summary.get("source_name", "") or "prediction_output").strip() or "prediction_output").stem
    file_name = f"{source_name}_prediction_cells.xlsx"
    return workbook_bytes, file_name


def _build_manual_grid_special_surface(
    summary: dict[str, object],
    compact_geojson: dict[str, object],
    distinct_names: list[str],
) -> dict[str, object] | None:
    if bool(summary.get("multi_profile_mode")) or len([name for name in distinct_names if str(name).strip()]) > 1:
        return None
    grid_payload = summary.get("manual_bbox_grid")
    grid_cells = grid_payload.get("cells", []) if isinstance(grid_payload, dict) else []
    if not isinstance(grid_cells, list) or not grid_cells:
        return None
    features = compact_geojson.get("features", []) if isinstance(compact_geojson, dict) else []
    if not isinstance(features, list) or not features:
        return None
    predicted_lookup: dict[str, float] = {}
    for feature in features:
        properties = feature.get("properties", {}) if isinstance(feature, dict) else {}
        if not isinstance(properties, dict):
            continue
        grid_cell_id = str(properties.get("Forecast grid cell id") or "").strip()
        predicted_value = _as_float(properties.get("Grain Yield predicted"))
        if not grid_cell_id or predicted_value is None:
            continue
        predicted_lookup[grid_cell_id] = float(predicted_value)
    if not predicted_lookup:
        return None
    surface = build_manual_grid_interpolated_surface(
        grid_cells,
        predicted_lookup,
    )
    return surface if surface.get("method") in {"kriging", "idw"} and surface.get("samples") else surface


def _build_manual_grid_predicted_stats(predicted_lookup: dict[str, float]) -> dict[str, float] | None:
    values = [float(value) for value in predicted_lookup.values() if isinstance(value, (int, float))]
    if not values:
        return None
    min_value = min(values)
    max_value = max(values)
    step = 0.0 if max_value == min_value else (max_value - min_value) / 4.0
    return {
        "min": min_value,
        "max": max_value,
        "q1Max": min_value + step,
        "q2Max": min_value + step * 2.0,
        "q3Max": min_value + step * 3.0,
    }


def _build_manual_grid_overlay_base_payload(
    summary: dict[str, object],
    compact_geojson: dict[str, object],
    distinct_names: list[str],
) -> dict[str, object] | None:
    grid_payload = summary.get("manual_bbox_grid")
    grid_cells = grid_payload.get("cells", []) if isinstance(grid_payload, dict) else []
    if not isinstance(grid_cells, list) or not grid_cells:
        return None

    multi_profile_mode = bool(summary.get("multi_profile_mode"))
    multi_germplasm_mode = len([name for name in distinct_names if str(name).strip()]) > 1
    if multi_profile_mode or multi_germplasm_mode:
        overlay_payload = _build_manual_grid_profile_overlay_payload(summary)
        return {
            "mode": "categorical",
            "labels": overlay_payload.get("labels", []),
            "heat_samples": overlay_payload.get("heat_samples", []),
        }

    features = compact_geojson.get("features", []) if isinstance(compact_geojson, dict) else []
    if not isinstance(features, list) or not features:
        return None

    cell_lookup = {
        str(cell.get("grid_cell_id") or "").strip(): cell
        for cell in grid_cells
        if str(cell.get("grid_cell_id") or "").strip()
    }
    predicted_lookup: dict[str, float] = {}
    heat_samples: list[dict[str, object]] = []
    for feature in features:
        if not isinstance(feature, dict):
            continue
        properties = feature.get("properties", {}) if isinstance(feature.get("properties"), dict) else {}
        grid_cell_id = str(properties.get("Forecast grid cell id") or "").strip()
        predicted_value = _as_float(properties.get("Grain Yield predicted"))
        cell = cell_lookup.get(grid_cell_id)
        if not grid_cell_id or predicted_value is None or cell is None:
            continue
        predicted_lookup[grid_cell_id] = float(predicted_value)
        heat_samples.append(
            {
                "id": grid_cell_id,
                "gridCellId": grid_cell_id,
                "longitudeMin": _as_float(cell.get("longitude_min")),
                "longitudeMax": _as_float(cell.get("longitude_max")),
                "latitudeMin": _as_float(cell.get("latitude_min")),
                "latitudeMax": _as_float(cell.get("latitude_max")),
                "predictedValue": float(predicted_value),
            }
        )
    if not predicted_lookup:
        return None
    return {
        "mode": "numeric",
        "predicted_lookup": predicted_lookup,
        "predicted_stats": _build_manual_grid_predicted_stats(predicted_lookup),
        "heat_samples": heat_samples,
    }


def _build_manual_grid_profile_overlay_payload(
    summary: dict[str, object],
    selected_labels: list[str] | None = None,
) -> dict[str, object]:
    if str(summary.get("climate_scope", "")).strip() != "regional_manual":
        return {"labels": [], "heat_samples": []}
    geojson = resolve_prediction_feature_collection(summary)
    grid_payload = summary.get("manual_bbox_grid")
    grid_cells = grid_payload.get("cells", []) if isinstance(grid_payload, dict) else []
    if not isinstance(grid_cells, list) or not grid_cells:
        return {"labels": [], "heat_samples": []}

    source_features = geojson.get("features", []) if isinstance(geojson, dict) else []
    if not isinstance(source_features, list) or not source_features:
        return {"labels": [], "heat_samples": []}

    distinct_names: list[str] = []
    seen_names: set[str] = set()
    for feature in source_features:
        if not isinstance(feature, dict):
            continue
        properties = feature.get("properties", {}) if isinstance(feature.get("properties"), dict) else {}
        name = str(properties.get("Name") or "").strip()
        if name and name not in seen_names:
            seen_names.add(name)
            distinct_names.append(name)

    multi_profile_mode = bool(summary.get("multi_profile_mode"))
    multi_germplasm_mode = len([name for name in distinct_names if str(name).strip()]) > 1
    selected_id_header = str(summary.get("selected_id_header") or "").strip()
    selected_lookup = {
        str(label or "").strip()
        for label in (selected_labels or [])
        if str(label or "").strip()
    }
    cell_lookup = {
        str(cell.get("grid_cell_id") or "").strip(): cell
        for cell in grid_cells
        if str(cell.get("grid_cell_id") or "").strip()
    }

    winners_by_cell: dict[str, dict[str, object]] = {}
    matched_labels: list[str] = []
    seen_labels: set[str] = set()
    heat_samples: list[dict[str, object]] = []
    for feature in source_features:
        if not isinstance(feature, dict):
            continue
        properties = feature.get("properties", {}) if isinstance(feature.get("properties"), dict) else {}
        label = _build_manual_grid_categorical_label(
            properties,
            selected_id_header=selected_id_header,
            multi_profile_mode=multi_profile_mode,
            multi_germplasm_mode=multi_germplasm_mode,
        )
        normalized_label = str(label or "").strip()
        if not normalized_label:
            continue
        if selected_lookup and normalized_label not in selected_lookup:
            continue
        grid_cell_id = _find_prediction_grid_cell_id(feature, grid_cells)
        if not grid_cell_id or grid_cell_id not in cell_lookup:
            continue
        predicted_value = _as_float(properties.get("Grain Yield predicted"))
        current = winners_by_cell.get(grid_cell_id)
        current_value = _as_float((current or {}).get("predicted_value"))
        if current is None or (
            predicted_value is not None and (current_value is None or predicted_value > current_value)
        ):
            winners_by_cell[grid_cell_id] = {
                "label": normalized_label,
                "predicted_value": predicted_value,
            }

    for grid_cell_id, winner_payload in winners_by_cell.items():
        cell = cell_lookup.get(grid_cell_id)
        if cell is None:
            continue
        normalized_label = str(winner_payload.get("label") or "").strip()
        if not normalized_label:
            continue
        if normalized_label not in seen_labels:
            seen_labels.add(normalized_label)
            matched_labels.append(normalized_label)
        heat_samples.append(
            {
                "id": grid_cell_id,
                "gridCellId": grid_cell_id,
                "longitudeMin": _as_float(cell.get("longitude_min")),
                "longitudeMax": _as_float(cell.get("longitude_max")),
                "latitudeMin": _as_float(cell.get("latitude_min")),
                "latitudeMax": _as_float(cell.get("latitude_max")),
                "profileLabel": normalized_label,
            }
        )
    return {
        "labels": matched_labels,
        "heat_samples": heat_samples,
    }


def resolve_prediction_feature_collection(summary: dict[str, object]) -> dict[str, object]:
    geojson_path = Path(str(summary.get("geojson_file", "")).strip()) if summary.get("geojson_file") else None
    if geojson_path and geojson_path.exists():
        try:
            payload = json.loads(geojson_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = None
        if is_valid_feature_collection(payload):
            return payload

    fallback_workbooks: list[Path] = []
    for summary_key in ("prediction_xlsx", "phase06_xlsx"):
        raw_path = str(summary.get(summary_key, "")).strip()
        if not raw_path:
            continue
        workbook_path = Path(raw_path)
        if workbook_path not in fallback_workbooks:
            fallback_workbooks.append(workbook_path)

    for workbook_path in fallback_workbooks:
        rebuilt = rebuild_feature_collection_from_workbook(workbook_path)
        if rebuilt is None:
            continue
        if geojson_path:
            try:
                geojson_path.parent.mkdir(parents=True, exist_ok=True)
                geojson_path.write_text(
                    json.dumps(sanitize_json_payload(rebuilt), ensure_ascii=False, indent=2, allow_nan=False),
                    encoding="utf-8",
                )
            except OSError:
                pass
        return rebuilt

    raise FileNotFoundError("The pipeline did not produce a valid GeoJSON feature collection.")


def build_prediction_display_feature_collection(summary: dict[str, object]) -> dict[str, object]:
    display_geojson_path = Path(str(summary.get("display_geojson_file", "")).strip()) if summary.get("display_geojson_file") else None
    if display_geojson_path and display_geojson_path.exists():
        with contextlib.suppress(OSError, json.JSONDecodeError):
            payload = json.loads(display_geojson_path.read_text(encoding="utf-8"))
            if is_valid_feature_collection(payload):
                return payload
    geojson = resolve_prediction_feature_collection(summary)
    if str(summary.get("climate_scope", "")).strip() != "regional_manual":
        return geojson
    compact_geojson, _ = _build_manual_grid_prediction_payload(summary, geojson)
    if is_valid_feature_collection(compact_geojson):
        winners_by_cell: dict[str, dict[str, object]] = {}
        for feature in compact_geojson.get("features", []) if isinstance(compact_geojson, dict) else []:
            if not isinstance(feature, dict):
                continue
            properties = feature.get("properties", {}) if isinstance(feature.get("properties"), dict) else {}
            grid_cell_id = str(properties.get("Forecast grid cell id") or "").strip()
            if not grid_cell_id:
                continue
            predicted_value = _as_float(properties.get("Grain Yield predicted"))
            current = winners_by_cell.get(grid_cell_id)
            current_predicted = _as_float(((current or {}).get("properties") or {}).get("Grain Yield predicted")) if current else None
            if current is None or (predicted_value is not None and (current_predicted is None or predicted_value > current_predicted)):
                winners_by_cell[grid_cell_id] = feature
        winner_features = list(winners_by_cell.values())
        if winner_features:
            return {
                "type": "FeatureCollection",
                "metadata": {
                    **(compact_geojson.get("metadata", {}) if isinstance(compact_geojson.get("metadata"), dict) else {}),
                    "total_features": len(winner_features),
                    "manual_grid_display_winners": True,
                },
                "features": winner_features,
            }
    return compact_geojson if is_valid_feature_collection(compact_geojson) else geojson


def build_completed_summary_for_ui(summary: dict[str, object]) -> dict[str, object]:
    response_summary = dict(summary)
    response_summary.pop("preprocess_log", None)
    response_summary.pop("manual_bbox_grid", None)
    return response_summary


def should_skip_running_preprocess_geojson(job: dict[str, object] | None) -> bool:
    if not isinstance(job, dict):
        return False
    climate_scope = str(job.get("climate_scope", "") or "").strip()
    selected_id_header = str(job.get("selected_id_header", "") or "").strip()
    selected_model_id = str(job.get("selected_model_id", "") or "").strip()
    return (
        climate_scope == "regional_manual"
        and bool(selected_id_header)
        and bool(selected_model_id)
    )


def should_inline_completed_geojson(summary: dict[str, object]) -> bool:
    climate_scope = str(summary.get("climate_scope", "")).strip()
    feature_count = int(summary.get("prediction_feature_count", 0) or 0)
    if climate_scope == "regional_manual":
        return False
    return feature_count <= 500


def find_free_port() -> int:
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return int(sock.getsockname()[1])


def resolve_pipeline_python() -> Path:
    for candidate in get_preferred_pipeline_pythons():
        if candidate and candidate.exists():
            return candidate
    raise FileNotFoundError(
        "No local Python interpreter with the app pipeline dependencies was found."
    )


class AppRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, directory: str, **kwargs):
        self.pipeline_python = resolve_pipeline_python()
        super().__init__(*args, directory=directory, **kwargs)

    def translate_path(self, path: str) -> str:
        parsed = urlparse(path)
        normalized_path = parsed.path
        if normalized_path == APP_URL_PATH.removesuffix("/"):
            normalized_path = "/"
        elif normalized_path.startswith(APP_URL_PATH):
            normalized_path = normalized_path.removeprefix(APP_URL_PATH[:-1] or APP_URL_PATH)
        return super().translate_path(normalized_path)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def send_json(self, payload: dict[str, object], status_code: int = 200) -> None:
        body = json.dumps(sanitize_json_payload(payload), ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:  # pragma: no cover
            return

    def send_binary_file(self, file_path: Path, *, download_name: str | None = None, content_type: str | None = None) -> None:
        payload = file_path.read_bytes()
        resolved_name = download_name or file_path.name
        mime_type = content_type or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", mime_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Content-Disposition", f'attachment; filename="{resolved_name}"')
        self.end_headers()
        try:
            self.wfile.write(payload)
        except BrokenPipeError:  # pragma: no cover
            return

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/cimmyt-app-config":
            try:
                self.handle_update_cimmyt_app_config()
            except BrokenPipeError:  # pragma: no cover
                return
            except ValueError as error:
                self.send_json({"error": str(error)}, status_code=400)
            except Exception as error:  # pragma: no cover
                self.send_json({"error": str(error)}, status_code=500)
            return
        if parsed.path == "/api/process-xlsx/cancel-all":
            try:
                self.handle_cancel_all_processes()
            except BrokenPipeError:  # pragma: no cover
                return
            except Exception as error:  # pragma: no cover
                self.send_json({"error": str(error)}, status_code=500)
            return
        if parsed.path == "/api/process-xlsx/germplasm-options":
            try:
                self.handle_germplasm_options()
            except BrokenPipeError:  # pragma: no cover
                return
            except ValueError as error:
                self.send_json({"error": str(error)}, status_code=400)
            except Exception as error:  # pragma: no cover
                self.send_json({"error": str(error)}, status_code=500)
            return
        if parsed.path == "/api/process-xlsx/original-data":
            try:
                self.handle_original_data_preview()
            except BrokenPipeError:  # pragma: no cover
                return
            except ValueError as error:
                self.send_json({"error": str(error)}, status_code=400)
            except Exception as error:  # pragma: no cover
                self.send_json({"error": str(error)}, status_code=500)
            return
        if parsed.path == "/api/process-xlsx/selecction-properties":
            try:
                self.handle_selecction_properties_metadata()
            except BrokenPipeError:  # pragma: no cover
                return
            except ValueError as error:
                self.send_json({"error": str(error)}, status_code=400)
            except Exception as error:  # pragma: no cover
                self.send_json({"error": str(error)}, status_code=500)
            return
        if parsed.path == "/api/process-xlsx/selecction-properties/preview":
            try:
                self.handle_selecction_properties_preview()
            except BrokenPipeError:  # pragma: no cover
                return
            except ValueError as error:
                self.send_json({"error": str(error)}, status_code=400)
            except Exception as error:  # pragma: no cover
                self.send_json({"error": str(error)}, status_code=500)
            return
        if parsed.path == "/api/process-xlsx/selecction-properties/summary":
            try:
                self.handle_selecction_properties_summary()
            except BrokenPipeError:  # pragma: no cover
                return
            except ValueError as error:
                self.send_json({"error": str(error)}, status_code=400)
            except Exception as error:  # pragma: no cover
                self.send_json({"error": str(error)}, status_code=500)
            return
        if parsed.path == "/api/process-xlsx/start":
            try:
                self.handle_start_process_xlsx()
            except BrokenPipeError:  # pragma: no cover
                return
            except ValueError as error:
                self.send_json({"error": str(error)}, status_code=400)
            except Exception as error:  # pragma: no cover
                self.send_json({"error": str(error)}, status_code=500)
            return
        if parsed.path.startswith("/api/process-xlsx/continue/"):
            job_id = parsed.path.rsplit("/", 1)[-1].strip()
            try:
                self.handle_continue_process_xlsx(job_id)
            except BrokenPipeError:  # pragma: no cover
                return
            except FileNotFoundError as error:
                self.send_json({"error": str(error)}, status_code=404)
            except ValueError as error:
                self.send_json({"error": str(error)}, status_code=400)
            except Exception as error:  # pragma: no cover
                self.send_json({"error": str(error)}, status_code=500)
            return
        if parsed.path != "/api/process-xlsx":
            self.send_error(404, "Endpoint not found.")
            return

        try:
            self.handle_process_xlsx()
        except BrokenPipeError:  # pragma: no cover
            return
        except ValueError as error:
            self.send_json({"error": str(error)}, status_code=400)
        except Exception as error:  # pragma: no cover
            self.send_json({"error": str(error)}, status_code=500)

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/models/"):
            self.send_error(404, "Endpoint not found.")
            return
        try:
            self.handle_delete_model(unquote(parsed.path.removeprefix("/api/models/")))
        except BrokenPipeError:  # pragma: no cover
            return
        except FileNotFoundError as error:
            self.send_json({"error": str(error)}, status_code=404)
        except Exception as error:  # pragma: no cover
            self.send_json({"error": str(error)}, status_code=500)

    def do_PATCH(self) -> None:
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/models/") or not parsed.path.endswith("/name"):
            self.send_error(404, "Endpoint not found.")
            return
        model_id = parsed.path.removeprefix("/api/models/").removesuffix("/name").strip()
        try:
            self.handle_rename_model(model_id)
        except BrokenPipeError:  # pragma: no cover
            return
        except FileNotFoundError as error:
            self.send_json({"error": str(error)}, status_code=404)
        except ValueError as error:
            self.send_json({"error": str(error)}, status_code=400)
        except Exception as error:  # pragma: no cover
            self.send_json({"error": str(error)}, status_code=500)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/nasa-country-bounds":
            try:
                self.handle_nasa_country_bounds(parsed.query)
            except BrokenPipeError:  # pragma: no cover
                return
            except ValueError as error:
                self.send_json({"error": str(error)}, status_code=400)
            except Exception as error:  # pragma: no cover
                self.send_json({"error": str(error)}, status_code=500)
            return
        if parsed.path == "/api/african-countries":
            try:
                self.handle_african_countries()
            except BrokenPipeError:  # pragma: no cover
                return
            except Exception as error:  # pragma: no cover
                self.send_json({"error": str(error)}, status_code=500)
            return
        if parsed.path.startswith("/api/process-xlsx/selecction-properties/status/"):
            job_id = parsed.path.rsplit("/", 1)[-1].strip()
            try:
                self.handle_selecction_properties_summary_status(job_id)
            except BrokenPipeError:  # pragma: no cover
                return
            except FileNotFoundError as error:
                self.send_json({"error": str(error)}, status_code=404)
            except Exception as error:  # pragma: no cover
                self.send_json({"error": str(error)}, status_code=500)
            return
        if parsed.path.startswith("/api/process-xlsx/selecction-properties/result/"):
            job_id = parsed.path.rsplit("/", 1)[-1].strip()
            try:
                self.handle_selecction_properties_summary_result(job_id)
            except BrokenPipeError:  # pragma: no cover
                return
            except FileNotFoundError as error:
                self.send_json({"error": str(error)}, status_code=404)
            except Exception as error:  # pragma: no cover
                self.send_json({"error": str(error)}, status_code=500)
            return
        if parsed.path == "/api/process-xlsx/selecction-properties/download":
            try:
                self.handle_selecction_properties_download(parsed.query)
            except BrokenPipeError:  # pragma: no cover
                return
            except FileNotFoundError as error:
                self.send_json({"error": str(error)}, status_code=404)
            except ValueError as error:
                self.send_json({"error": str(error)}, status_code=400)
            except Exception as error:  # pragma: no cover
                self.send_json({"error": str(error)}, status_code=500)
            return
        if parsed.path == "/api/country-localities":
            try:
                self.handle_country_localities(parsed.query)
            except BrokenPipeError:  # pragma: no cover
                return
            except ValueError as error:
                self.send_json({"error": str(error)}, status_code=400)
            except Exception as error:  # pragma: no cover
                self.send_json({"error": str(error)}, status_code=500)
            return
        if parsed.path == "/api/bbox-localities":
            try:
                self.handle_bbox_localities(parsed.query)
            except BrokenPipeError:  # pragma: no cover
                return
            except ValueError as error:
                self.send_json({"error": str(error)}, status_code=400)
            except Exception as error:  # pragma: no cover
                self.send_json({"error": str(error)}, status_code=500)
            return
        if parsed.path == "/api/bbox-grid":
            try:
                self.handle_bbox_grid(parsed.query)
            except BrokenPipeError:  # pragma: no cover
                return
            except ValueError as error:
                self.send_json({"error": str(error)}, status_code=400)
            except Exception as error:  # pragma: no cover
                self.send_json({"error": str(error)}, status_code=500)
            return
        if parsed.path.startswith("/api/models/") and parsed.path.endswith("/best-model.pkl"):
            model_id = parsed.path.removeprefix("/api/models/").removesuffix("/best-model.pkl").strip("/")
            try:
                self.handle_model_best_model_pkl(unquote(model_id))
            except BrokenPipeError:  # pragma: no cover
                return
            except FileNotFoundError as error:
                self.send_json({"error": str(error)}, status_code=404)
            except ValueError as error:
                self.send_json({"error": str(error)}, status_code=400)
            except Exception as error:  # pragma: no cover
                self.send_json({"error": str(error)}, status_code=500)
            return
        if parsed.path.startswith("/api/models/") and parsed.path.endswith("/optimization.csv"):
            model_id = parsed.path.removeprefix("/api/models/").removesuffix("/optimization.csv").strip("/")
            try:
                self.handle_model_optimization_csv(unquote(model_id))
            except BrokenPipeError:  # pragma: no cover
                return
            except FileNotFoundError as error:
                self.send_json({"error": str(error)}, status_code=404)
            except ValueError as error:
                self.send_json({"error": str(error)}, status_code=400)
            except Exception as error:  # pragma: no cover
                self.send_json({"error": str(error)}, status_code=500)
            return
        if parsed.path.startswith("/api/models/") and parsed.path.endswith("/best-features.csv"):
            model_id = parsed.path.removeprefix("/api/models/").removesuffix("/best-features.csv").strip("/")
            try:
                self.handle_model_best_features_csv(unquote(model_id))
            except BrokenPipeError:  # pragma: no cover
                return
            except FileNotFoundError as error:
                self.send_json({"error": str(error)}, status_code=404)
            except ValueError as error:
                self.send_json({"error": str(error)}, status_code=400)
            except Exception as error:  # pragma: no cover
                self.send_json({"error": str(error)}, status_code=500)
            return
        if parsed.path.startswith("/api/models/") and parsed.path.endswith("/selection-summary.json"):
            model_id = parsed.path.removeprefix("/api/models/").removesuffix("/selection-summary.json").strip("/")
            try:
                self.handle_model_selection_summary_json(unquote(model_id))
            except BrokenPipeError:  # pragma: no cover
                return
            except FileNotFoundError as error:
                self.send_json({"error": str(error)}, status_code=404)
            except ValueError as error:
                self.send_json({"error": str(error)}, status_code=400)
            except Exception as error:  # pragma: no cover
                self.send_json({"error": str(error)}, status_code=500)
            return
        if parsed.path.startswith("/api/models/") and parsed.path.endswith("/selection-summary.csv"):
            model_id = parsed.path.removeprefix("/api/models/").removesuffix("/selection-summary.csv").strip("/")
            try:
                self.handle_model_selection_summary_csv(unquote(model_id))
            except BrokenPipeError:  # pragma: no cover
                return
            except FileNotFoundError as error:
                self.send_json({"error": str(error)}, status_code=404)
            except ValueError as error:
                self.send_json({"error": str(error)}, status_code=400)
            except Exception as error:  # pragma: no cover
                self.send_json({"error": str(error)}, status_code=500)
            return
        if parsed.path.startswith("/api/models/") and parsed.path.endswith("/workspace"):
            model_id = parsed.path.removeprefix("/api/models/").removesuffix("/workspace").strip("/")
            try:
                self.handle_model_workspace(unquote(model_id))
            except BrokenPipeError:  # pragma: no cover
                return
            except FileNotFoundError as error:
                self.send_json({"error": str(error)}, status_code=404)
            except ValueError as error:
                self.send_json({"error": str(error)}, status_code=400)
            except Exception as error:  # pragma: no cover
                self.send_json({"error": str(error)}, status_code=500)
            return
        if parsed.path.startswith("/api/models/") and parsed.path.endswith("/training-results.xlsx"):
            model_id = parsed.path.removeprefix("/api/models/").removesuffix("/training-results.xlsx").strip("/")
            try:
                self.handle_model_training_results_download(unquote(model_id))
            except BrokenPipeError:  # pragma: no cover
                return
            except FileNotFoundError as error:
                self.send_json({"error": str(error)}, status_code=404)
            except ValueError as error:
                self.send_json({"error": str(error)}, status_code=400)
            except Exception as error:  # pragma: no cover
                self.send_json({"error": str(error)}, status_code=500)
            return
        if parsed.path.startswith("/api/models/") and parsed.path.endswith("/top-germplasm.xlsx"):
            model_id = parsed.path.removeprefix("/api/models/").removesuffix("/top-germplasm.xlsx").strip("/")
            try:
                self.handle_model_top_germplasm_download(unquote(model_id))
            except BrokenPipeError:  # pragma: no cover
                return
            except FileNotFoundError as error:
                self.send_json({"error": str(error)}, status_code=404)
            except ValueError as error:
                self.send_json({"error": str(error)}, status_code=400)
            except Exception as error:  # pragma: no cover
                self.send_json({"error": str(error)}, status_code=500)
            return
        if parsed.path.startswith("/api/models/") and parsed.path.endswith("/source-workbook.xlsx"):
            model_id = parsed.path.removeprefix("/api/models/").removesuffix("/source-workbook.xlsx").strip("/")
            try:
                self.handle_model_source_workbook_download(unquote(model_id))
            except BrokenPipeError:  # pragma: no cover
                return
            except FileNotFoundError as error:
                self.send_json({"error": str(error)}, status_code=404)
            except ValueError as error:
                self.send_json({"error": str(error)}, status_code=400)
            except Exception as error:  # pragma: no cover
                self.send_json({"error": str(error)}, status_code=500)
            return
        if parsed.path == "/api/models":
            try:
                self.handle_models()
            except BrokenPipeError:  # pragma: no cover
                return
            except Exception as error:  # pragma: no cover
                self.send_json({"error": str(error)}, status_code=500)
            return
        if parsed.path == "/api/cimmyt-app-config":
            try:
                self.handle_cimmyt_app_config()
            except BrokenPipeError:  # pragma: no cover
                return
            except Exception as error:  # pragma: no cover
                self.send_json({"error": str(error)}, status_code=500)
            return
        if parsed.path == "/api/runtime-status":
            try:
                self.handle_runtime_status()
            except BrokenPipeError:  # pragma: no cover
                return
            except Exception as error:  # pragma: no cover
                self.send_json({"error": str(error)}, status_code=500)
            return
        if parsed.path.startswith("/api/process-xlsx/status/"):
            job_id = parsed.path.rsplit("/", 1)[-1].strip()
            try:
                self.handle_process_status(job_id)
            except BrokenPipeError:  # pragma: no cover
                return
            except FileNotFoundError as error:
                self.send_json({"error": str(error)}, status_code=404)
            except Exception as error:  # pragma: no cover
                self.send_json({"error": str(error)}, status_code=500)
            return
        if parsed.path.startswith("/api/process-xlsx/artifact/"):
            artifact_parts = parsed.path.removeprefix("/api/process-xlsx/artifact/").split("/", 1)
            if len(artifact_parts) != 2:
                self.send_error(404, "Artifact not found.")
                return
            job_id, artifact_name = artifact_parts
            try:
                self.handle_process_artifact(job_id.strip(), artifact_name.strip(), parsed.query)
            except BrokenPipeError:  # pragma: no cover
                return
            except FileNotFoundError as error:
                self.send_json({"error": str(error)}, status_code=404)
            except Exception as error:  # pragma: no cover
                self.send_json({"error": str(error)}, status_code=500)
            return
        super().do_GET()

    def read_upload_request(self) -> tuple[str, bytes]:
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0:
            raise ValueError("The request body is empty.")

        source_name = self.headers.get("X-File-Name", "uploaded.xlsx").strip() or "uploaded.xlsx"
        if not source_name.lower().endswith(".xlsx"):
            raise ValueError("Only .xlsx files are supported.")
        return source_name, self.rfile.read(content_length)

    def read_json_request(self) -> dict[str, object]:
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0:
            return {}
        raw_body = self.rfile.read(content_length)
        if not raw_body:
            return {}
        payload = json.loads(raw_body.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("The request JSON body must be an object.")
        return payload

    def parse_selected_germplasm_names_header(self) -> list[str]:
        raw_value = self.headers.get("X-Selected-Germplasm-Names", "").strip()
        if not raw_value:
            return []
        parsed = json.loads(raw_value)
        if not isinstance(parsed, list):
            raise ValueError("X-Selected-Germplasm-Names must be a JSON array of strings.")
        names = [str(item).strip() for item in parsed if str(item).strip()]
        return names

    def parse_json_list_header(self, header_name: str) -> list[str]:
        raw_value = self.headers.get(header_name, "").strip()
        if not raw_value:
            return []
        parsed = json.loads(raw_value)
        if not isinstance(parsed, list):
            raise ValueError(f"{header_name} must be a JSON array of strings.")
        return [str(item).strip() for item in parsed if str(item).strip()]


    def parse_selected_germplasm_selection_mode_header(self) -> str:
        value = self.headers.get("X-Selected-Germplasm-Selection-Mode", "").strip() or "all_matches"
        return "first_match_only" if value == "first_match_only" else "all_matches"

    def parse_use_source_row_dates_header(self) -> bool:
        value = self.headers.get("X-Use-Source-Row-Dates", "").strip().lower()
        if value in {"0", "false", "no"}:
            return False
        return True

    def launch_pipeline_process(
        self,
        *,
        run_dir: Path,
        source_name: str,
        selected_model_id: str = "",
        input_file: Path | None = None,
        phase06_input: Path | None = None,
        forecast_planting_date: str = "",
        forecast_harvesting_date: str = "",
        pause_after_preprocess: bool = False,
        climate_scope: str = "point",
        regional_country: str = "",
        selected_germplasm_names: list[str] | None = None,
        selected_germplasm_row_ids: list[str] | None = None,
        selected_germplasm_projection_mode: str = "",
        selected_germplasm_selection_mode: str = "all_matches",
        projection_template_workbook: str = "",
        regional_bounds_label: str = "",
        regional_bounds_latitude_min: str = "",
        regional_bounds_latitude_max: str = "",
        regional_bounds_longitude_min: str = "",
        regional_bounds_longitude_max: str = "",
        nasa_grid_resolution_km: str = "",
        use_source_row_dates: bool = True,
        selected_id_header: str = "",
    ) -> None:
        progress_file = run_dir / "progress.json"
        stdout_file = run_dir / "pipeline.stdout.log"
        stderr_file = run_dir / "pipeline.stderr.log"
        command = [
            str(self.pipeline_python),
            str(APP_DIR / "pipeline" / "run_pipeline.py"),
            "--run-dir",
            str(run_dir),
            "--progress-file",
            str(progress_file),
        ]
        if input_file is not None:
            command.extend(["--input", str(input_file)])
        if phase06_input is not None:
            command.extend(["--phase06-input", str(phase06_input)])
        if selected_model_id:
            command.extend(["--selected-model-id", selected_model_id])
        if forecast_planting_date:
            command.extend(["--forecast-planting-date", forecast_planting_date])
        if forecast_harvesting_date:
            command.extend(["--forecast-harvesting-date", forecast_harvesting_date])
        if pause_after_preprocess:
            command.append("--pause-after-preprocess")
        if climate_scope:
            command.extend(["--climate-scope", climate_scope])
        if regional_country:
            command.extend(["--regional-country", regional_country])
        if selected_germplasm_names:
            command.extend(
                ["--selected-germplasm-names-json", json.dumps(selected_germplasm_names, ensure_ascii=False)]
            )
        if selected_germplasm_row_ids:
            command.extend(
                ["--selected-germplasm-row-ids-json", json.dumps(selected_germplasm_row_ids, ensure_ascii=False)]
            )
        if selected_germplasm_projection_mode:
            command.extend(
                ["--selected-germplasm-projection-mode", selected_germplasm_projection_mode]
            )
        if selected_germplasm_selection_mode:
            command.extend(
                ["--selected-germplasm-selection-mode", selected_germplasm_selection_mode]
            )
        if projection_template_workbook:
            command.extend(["--projection-template-workbook", projection_template_workbook])
        if regional_bounds_label:
            command.extend(["--regional-bounds-label", regional_bounds_label])
        if regional_bounds_latitude_min:
            command.extend(["--regional-bounds-latitude-min", regional_bounds_latitude_min])
        if regional_bounds_latitude_max:
            command.extend(["--regional-bounds-latitude-max", regional_bounds_latitude_max])
        if regional_bounds_longitude_min:
            command.extend(["--regional-bounds-longitude-min", regional_bounds_longitude_min])
        if regional_bounds_longitude_max:
            command.extend(["--regional-bounds-longitude-max", regional_bounds_longitude_max])
        if nasa_grid_resolution_km:
            command.extend(["--nasa-grid-resolution-km", nasa_grid_resolution_km])
        if selected_id_header:
            command.extend(["--selected-id-header", selected_id_header])
        command.extend(["--use-source-row-dates", "1" if use_source_row_dates else "0"])
        stdout_handle = stdout_file.open("w", encoding="utf-8")
        stderr_handle = stderr_file.open("w", encoding="utf-8")
        process = subprocess.Popen(
            command,
            cwd=str(APP_DIR),
            stdout=stdout_handle,
            stderr=stderr_handle,
            text=True,
        )
        return process, stdout_handle, stderr_handle

    def create_pipeline_job(
        self,
        source_name: str,
        file_bytes: bytes,
        selected_model_id: str = "",
        forecast_planting_date: str = "",
        forecast_harvesting_date: str = "",
        pause_after_preprocess: bool = False,
        climate_scope: str = "point",
        regional_country: str = "",
        selected_germplasm_names: list[str] | None = None,
        selected_germplasm_row_ids: list[str] | None = None,
        selected_germplasm_projection_mode: str = "",
        selected_germplasm_selection_mode: str = "all_matches",
        projection_template_workbook: str = "",
        regional_bounds_label: str = "",
        regional_bounds_latitude_min: str = "",
        regional_bounds_latitude_max: str = "",
        regional_bounds_longitude_min: str = "",
        regional_bounds_longitude_max: str = "",
        nasa_grid_resolution_km: str = "",
        use_source_row_dates: bool = True,
        selected_id_header: str = "",
    ) -> tuple[str, Path]:
        reap_finished_pipeline_jobs()
        cleanup_stale_pipeline_run_dirs()
        PIPELINE_RUNS_DIR.mkdir(parents=True, exist_ok=True)
        run_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
        run_dir = PIPELINE_RUNS_DIR / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        input_file = run_dir / "input.xlsx"
        input_file.write_bytes(file_bytes)
        progress_file = run_dir / "progress.json"

        initial_progress = {
            "status": "running",
            "percent": 8,
            "stage": "Uploading file",
            "message": f"Receiving {source_name} and preparing the backend job.",
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        progress_file.write_text(json.dumps(initial_progress, ensure_ascii=False, indent=2), encoding="utf-8")
        process, stdout_handle, stderr_handle = self.launch_pipeline_process(
            run_dir=run_dir,
            source_name=source_name,
            selected_model_id=selected_model_id,
            input_file=input_file,
            forecast_planting_date=forecast_planting_date,
            forecast_harvesting_date=forecast_harvesting_date,
            pause_after_preprocess=pause_after_preprocess,
            climate_scope=climate_scope,
            regional_country=regional_country,
            selected_germplasm_names=selected_germplasm_names,
            selected_germplasm_row_ids=selected_germplasm_row_ids,
            selected_germplasm_projection_mode=selected_germplasm_projection_mode,
            selected_germplasm_selection_mode=selected_germplasm_selection_mode,
            projection_template_workbook=projection_template_workbook,
            regional_bounds_label=regional_bounds_label,
            regional_bounds_latitude_min=regional_bounds_latitude_min,
            regional_bounds_latitude_max=regional_bounds_latitude_max,
            regional_bounds_longitude_min=regional_bounds_longitude_min,
            regional_bounds_longitude_max=regional_bounds_longitude_max,
            nasa_grid_resolution_km=nasa_grid_resolution_km,
            use_source_row_dates=use_source_row_dates,
            selected_id_header=selected_id_header,
        )
        with PIPELINE_JOBS_LOCK:
            PIPELINE_JOBS[run_id] = {
                "process": process,
                "run_dir": run_dir,
                "source_name": source_name,
                "selected_model_id": selected_model_id,
                "forecast_planting_date": forecast_planting_date,
                "forecast_harvesting_date": forecast_harvesting_date,
                "climate_scope": climate_scope,
                "regional_country": regional_country,
                "selected_germplasm_names": selected_germplasm_names or [],
                "selected_germplasm_row_ids": selected_germplasm_row_ids or [],
                "selected_germplasm_projection_mode": selected_germplasm_projection_mode,
                "selected_germplasm_selection_mode": selected_germplasm_selection_mode,
                "projection_template_workbook": projection_template_workbook,
                "regional_bounds_label": regional_bounds_label,
                "regional_bounds_latitude_min": regional_bounds_latitude_min,
                "regional_bounds_latitude_max": regional_bounds_latitude_max,
                "regional_bounds_longitude_min": regional_bounds_longitude_min,
                "regional_bounds_longitude_max": regional_bounds_longitude_max,
                "nasa_grid_resolution_km": nasa_grid_resolution_km,
                "use_source_row_dates": use_source_row_dates,
                "selected_id_header": selected_id_header,
                "stdout_handle": stdout_handle,
                "stderr_handle": stderr_handle,
            }
        return run_id, run_dir

    def handle_start_process_xlsx(self) -> None:
        source_name, file_bytes = self.read_upload_request()
        selected_model_id = self.headers.get("X-Selected-Model-Id", "").strip()
        selected_germplasm_names = self.parse_selected_germplasm_names_header()
        selected_germplasm_row_ids = self.parse_json_list_header("X-Selected-Germplasm-Row-Ids")
        selected_germplasm_projection_mode = self.headers.get(
            "X-Selected-Germplasm-Projection-Mode", ""
        ).strip()
        selected_germplasm_selection_mode = self.parse_selected_germplasm_selection_mode_header()
        projection_template_workbook = self.headers.get("X-Projection-Template-Workbook", "").strip()
        forecast_planting_date = self.headers.get("X-Forecast-Planting-Date", "").strip()
        forecast_harvesting_date = self.headers.get("X-Forecast-Harvesting-Date", "").strip()
        pause_after_preprocess = self.headers.get("X-Pause-After-Preprocess", "").strip() == "1"
        climate_scope = self.headers.get("X-Climate-Scope", "point").strip() or "point"
        regional_country = self.headers.get("X-Regional-Country", "").strip()
        regional_bounds_label = self.headers.get("X-Regional-Bounds-Label", "").strip()
        regional_bounds_latitude_min = self.headers.get("X-Regional-Bounds-Latitude-Min", "").strip()
        regional_bounds_latitude_max = self.headers.get("X-Regional-Bounds-Latitude-Max", "").strip()
        regional_bounds_longitude_min = self.headers.get("X-Regional-Bounds-Longitude-Min", "").strip()
        regional_bounds_longitude_max = self.headers.get("X-Regional-Bounds-Longitude-Max", "").strip()
        nasa_grid_resolution_km = self.headers.get("X-Nasa-Grid-Resolution-Km", "").strip()
        selected_id_header = self.headers.get("X-Selected-Id-Header", "").strip()
        use_source_row_dates = self.parse_use_source_row_dates_header()
        run_id, run_dir = self.create_pipeline_job(
            source_name,
            file_bytes,
            selected_model_id,
            forecast_planting_date=forecast_planting_date,
            forecast_harvesting_date=forecast_harvesting_date,
            pause_after_preprocess=pause_after_preprocess,
            climate_scope=climate_scope,
            regional_country=regional_country,
            selected_germplasm_names=selected_germplasm_names,
            selected_germplasm_row_ids=selected_germplasm_row_ids,
            selected_germplasm_projection_mode=selected_germplasm_projection_mode,
            selected_germplasm_selection_mode=selected_germplasm_selection_mode,
            projection_template_workbook=projection_template_workbook,
            regional_bounds_label=regional_bounds_label,
            regional_bounds_latitude_min=regional_bounds_latitude_min,
            regional_bounds_latitude_max=regional_bounds_latitude_max,
            regional_bounds_longitude_min=regional_bounds_longitude_min,
            regional_bounds_longitude_max=regional_bounds_longitude_max,
            nasa_grid_resolution_km=nasa_grid_resolution_km,
            use_source_row_dates=use_source_row_dates,
            selected_id_header=selected_id_header,
        )
        self.send_json(
            {
                "job_id": run_id,
                "run_dir": str(run_dir),
                "status_url": f"/api/process-xlsx/status/{run_id}",
            }
        )

    def handle_continue_process_xlsx(self, job_id: str) -> None:
        with PIPELINE_JOBS_LOCK:
            job = PIPELINE_JOBS.get(job_id)
        if job is None:
            raise FileNotFoundError("Unknown pipeline job.")
        process = job["process"]
        if process.poll() is None:
            raise ValueError("The pipeline job is still running.")
        run_dir = Path(job["run_dir"])
        progress_file = run_dir / "progress.json"
        if not progress_file.exists():
            raise FileNotFoundError("The pipeline progress file was not found.")
        progress_payload = json.loads(progress_file.read_text(encoding="utf-8"))
        if progress_payload.get("status") != "paused":
            raise ValueError("The pipeline job is not waiting for preprocess validation.")
        phase06_input = run_dir / "preprocess" / "phase06_phase1_compatible" / "phase06_phase1_compatible.xlsx"
        if not phase06_input.exists():
            raise FileNotFoundError("The preprocess phase06 workbook is not available.")
        process, stdout_handle, stderr_handle = self.launch_pipeline_process(
            run_dir=run_dir,
            source_name=str(job["source_name"]),
            selected_model_id=str(job.get("selected_model_id", "")),
            phase06_input=phase06_input,
            climate_scope=str(job.get("climate_scope", "point")),
            regional_country=str(job.get("regional_country", "")),
            selected_germplasm_names=list(job.get("selected_germplasm_names", [])),
            selected_germplasm_row_ids=list(job.get("selected_germplasm_row_ids", [])),
            selected_germplasm_projection_mode=str(
                job.get("selected_germplasm_projection_mode", "")
            ),
            selected_germplasm_selection_mode=str(job.get("selected_germplasm_selection_mode", "all_matches")),
            projection_template_workbook=str(job.get("projection_template_workbook", "")),
            regional_bounds_label=str(job.get("regional_bounds_label", "")),
            regional_bounds_latitude_min=str(job.get("regional_bounds_latitude_min", "")),
            regional_bounds_latitude_max=str(job.get("regional_bounds_latitude_max", "")),
            regional_bounds_longitude_min=str(job.get("regional_bounds_longitude_min", "")),
            regional_bounds_longitude_max=str(job.get("regional_bounds_longitude_max", "")),
            nasa_grid_resolution_km=str(job.get("nasa_grid_resolution_km", "")),
            use_source_row_dates=bool(job.get("use_source_row_dates", True)),
            selected_id_header=str(job.get("selected_id_header", "")),
        )
        with PIPELINE_JOBS_LOCK:
            PIPELINE_JOBS[job_id].update(
                {
                    "process": process,
                    "stdout_handle": stdout_handle,
                    "stderr_handle": stderr_handle,
                }
            )
        self.send_json(
            {
                "job_id": job_id,
                "run_dir": str(run_dir),
                "status_url": f"/api/process-xlsx/status/{job_id}",
            }
        )

    def handle_selecction_properties_download(self, raw_query: str) -> None:
        query = parse_qs(raw_query, keep_blank_values=False)
        run_id = (query.get("run_id") or [""])[0].strip()
        phase = (query.get("phase") or ["phase02"])[0].strip() or "phase02"
        if not run_id:
            raise ValueError("A run_id is required to download ce_pipeline output.")
        run_dir = PIPELINE_RUNS_DIR / run_id
        if not run_dir.exists() or not run_dir.is_dir():
            raise FileNotFoundError("The requested ce_pipeline run was not found.")
        if phase == "phase01":
            target_path = run_dir / "ce_pipeline" / "phase01" / "phase1.xlsx"
        elif phase == "phase02":
            target_path = run_dir / "ce_pipeline" / "phase02" / "phase02.xlsx"
        elif phase == "phase03":
            target_path = run_dir / "ce_pipeline" / "phase03" / "phase03.xlsx"
        elif phase == "phase04":
            target_path = run_dir / "ce_pipeline" / "phase04" / "phase04.xlsx"
        elif phase == "phase04_training_input":
            target_path = run_dir / "ce_pipeline" / "phase04" / "phase04_training_input.xlsx"
        elif phase == "training_results":
            target_path = resolve_ce_training_results_download_path(run_dir)
        elif phase == "top_germplasm":
            summary_file = run_dir / "ce_pipeline" / "phase06" / "summary.json"
            if not summary_file.exists():
                raise FileNotFoundError("The Top Germplasm summary is not available for this run.")
            top_summary = read_json_file_safe(summary_file)
            target_path = Path(str(top_summary.get("top_germplasm_xlsx", "")).strip())
        else:
            raise ValueError("Unsupported ce_pipeline phase download.")
        if not target_path.exists():
            raise FileNotFoundError("The requested ce_pipeline workbook is not available.")
        self.send_binary_file(
            target_path,
            download_name=target_path.name,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    def handle_cimmyt_app_config(self) -> None:
        self.send_json(
            {
                "app_version": get_app_version(),
                "preprocess_validation_enabled": get_preprocess_validation_enabled(),
                "ce_pipeline_download_enabled": get_ce_pipeline_download_enabled(),
                "featurehero_settings": get_featurehero_settings(),
            }
        )

    def handle_update_cimmyt_app_config(self) -> None:
        payload = self.read_json_request()
        featurehero_settings = payload.get("featurehero_settings")
        if not isinstance(featurehero_settings, dict):
            raise ValueError("featurehero_settings must be an object.")
        updated_settings = update_featurehero_settings(featurehero_settings)
        self.send_json(
            {
                "app_version": get_app_version(),
                "preprocess_validation_enabled": get_preprocess_validation_enabled(),
                "ce_pipeline_download_enabled": get_ce_pipeline_download_enabled(),
                "featurehero_settings": updated_settings,
                "saved": True,
            }
        )

    def handle_cancel_all_processes(self) -> None:
        cancelled_pipeline_jobs = 0
        reap_finished_pipeline_jobs(remove_expired=False)
        with PIPELINE_JOBS_LOCK:
            jobs = list(PIPELINE_JOBS.items())
        for job_id, job in jobs:
            process = job.get("process")
            if process is None:
                continue
            try:
                if process.poll() is None:
                    process.terminate()
                    run_dir = Path(job.get("run_dir", "")) if str(job.get("run_dir", "")).strip() else None
                    if run_dir is not None:
                        _write_pipeline_progress_status(
                            run_dir,
                            status="cancelled",
                            message="The pipeline job was cancelled before completion.",
                        )
                    with PIPELINE_JOBS_LOCK:
                        active_job = PIPELINE_JOBS.get(job_id)
                        if active_job is not None:
                            active_job["final_status"] = "cancelled"
                            active_job["finished_at"] = time.time()
                    cancelled_pipeline_jobs += 1
            except Exception:
                continue
        cancelled_featurehero_jobs = 0
        featurehero_jobs = get_active_featurehero_jobs()
        active_featurehero_jobs: dict[str, object] = {}
        for pid_text, info in featurehero_jobs.items():
            try:
                pid = int(pid_text)
            except (TypeError, ValueError):
                continue
            try:
                os.kill(pid, 15)
                cancelled_featurehero_jobs += 1
            except ProcessLookupError:
                continue
            except PermissionError:
                active_featurehero_jobs[pid_text] = info
        try:
            FEATUREHERO_JOBS_FILE.parent.mkdir(parents=True, exist_ok=True)
            FEATUREHERO_JOBS_FILE.write_text(
                json.dumps(active_featurehero_jobs, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass
        self.send_json(
            {
                "cancelled_pipeline_jobs": cancelled_pipeline_jobs,
                "cancelled_featurehero_jobs": cancelled_featurehero_jobs,
                "cancelled_total": cancelled_pipeline_jobs + cancelled_featurehero_jobs,
            }
        )

    def handle_runtime_status(self) -> None:
        reap_finished_pipeline_jobs()
        cleanup_stale_pipeline_run_dirs()
        active_featurehero_jobs = get_active_featurehero_jobs()
        self.send_json(
            {
                "active_pipeline_jobs": get_active_pipeline_job_count(),
                "active_featurehero_jobs": len(active_featurehero_jobs),
                "has_active_runtime_jobs": bool(get_active_pipeline_job_count() or active_featurehero_jobs),
            }
        )

    def handle_african_countries(self) -> None:
        self.send_json({"countries": list_african_countries()})

    def handle_country_localities(self, raw_query: str) -> None:
        query = parse_qs(raw_query, keep_blank_values=False)
        selected_country = (query.get("country") or [""])[0].strip()
        if not selected_country:
            raise ValueError("A country selection is required.")
        self.send_json(sample_country_localities(selected_country))

    def handle_bbox_localities(self, raw_query: str) -> None:
        query = parse_qs(raw_query, keep_blank_values=False)
        latitude_min = float((query.get("latitude_min") or [""])[0].strip())
        latitude_max = float((query.get("latitude_max") or [""])[0].strip())
        longitude_min = float((query.get("longitude_min") or [""])[0].strip())
        longitude_max = float((query.get("longitude_max") or [""])[0].strip())
        self.send_json(
            sample_localities_within_bounds(
                latitude_min,
                latitude_max,
                longitude_min,
                longitude_max,
            )
        )

    def handle_bbox_grid(self, raw_query: str) -> None:
        query = parse_qs(raw_query, keep_blank_values=False)
        latitude_min = float((query.get("latitude_min") or [""])[0].strip())
        latitude_max = float((query.get("latitude_max") or [""])[0].strip())
        longitude_min = float((query.get("longitude_min") or [""])[0].strip())
        longitude_max = float((query.get("longitude_max") or [""])[0].strip())
        label = (query.get("label") or ["Manual bounds"])[0].strip() or "Manual bounds"
        resolution_raw = (query.get("resolution_km") or [""])[0].strip()
        resolution_km = int(resolution_raw) if resolution_raw else int(get_featurehero_settings().get("nasa_power_resolution_km", 10))
        self.send_json(
            build_manual_grid_payload(
                latitude_min,
                latitude_max,
                longitude_min,
                longitude_max,
                label=label,
                cell_size_km=resolution_km,
            )
        )

    def handle_nasa_country_bounds(self, raw_query: str) -> None:
        query = parse_qs(raw_query, keep_blank_values=False)
        selected_country = (query.get("country") or [""])[0].strip()
        if selected_country:
            self.send_json(build_country_bounds_payload(selected_country))
            return
        latitude_min = (query.get("latitude_min") or [""])[0].strip()
        latitude_max = (query.get("latitude_max") or [""])[0].strip()
        longitude_min = (query.get("longitude_min") or [""])[0].strip()
        longitude_max = (query.get("longitude_max") or [""])[0].strip()
        if latitude_min and latitude_max and longitude_min and longitude_max:
            label = (query.get("label") or ["Manual bounds"])[0].strip() or "Manual bounds"
            self.send_json(
                build_manual_bounds_payload(
                    float(latitude_min),
                    float(latitude_max),
                    float(longitude_min),
                    float(longitude_max),
                    label=label,
                )
            )
            return
        self.send_json({"countries": list_supported_country_bounds()})

    def build_completed_payload(self, job_id: str, run_dir: Path, source_name: str) -> dict[str, object]:
        summary_path = run_dir / "summary.json"
        if not summary_path.exists():
            raise FileNotFoundError("The pipeline did not produce summary.json.")

        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        geojson: dict[str, object] | None = None
        response_summary = build_completed_summary_for_ui(summary)
        if str(summary.get("climate_scope", "")).strip() == "regional_manual":
            compact_geojson = build_prediction_display_feature_collection(summary)
            _, distinct_names = _build_manual_grid_prediction_payload(summary, compact_geojson)
            overlay_base = _build_manual_grid_overlay_base_payload(summary, compact_geojson, distinct_names)
            if overlay_base:
                response_summary["manual_grid_overlay_base"] = overlay_base
            special_surface = _build_manual_grid_special_surface(summary, compact_geojson, distinct_names)
            if special_surface:
                response_summary["manual_grid_interpolated_surface"] = special_surface
        if should_inline_completed_geojson(summary):
            geojson = build_prediction_display_feature_collection(summary)
        response_summary["job_id"] = job_id
        return {
            "source_name": source_name,
            "geojson": geojson,
            "summary": response_summary,
            "prediction_model_name": summary.get("prediction_model_name", ""),
            "geojson_download_url": f"/api/process-xlsx/artifact/{job_id}/display_geojson",
            "raw_geojson_download_url": f"/api/process-xlsx/artifact/{job_id}/geojson",
            "prediction_output_download_url": f"/api/process-xlsx/artifact/{job_id}/prediction_output",
        }

    def build_paused_payload(self, job_id: str, run_dir: Path, source_name: str) -> dict[str, object]:
        summary_path = run_dir / "summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
        if not summary.get("preprocess_log"):
            preprocess_summary_file = str(summary.get("preprocess_summary_file", "")).strip()
            if preprocess_summary_file:
                preprocess_summary_path = Path(preprocess_summary_file)
                if preprocess_summary_path.exists():
                    preprocess_summary = json.loads(
                        preprocess_summary_path.read_text(encoding="utf-8")
                    )
                    summary["preprocess_log"] = preprocess_summary.get("preprocess_log", {})
                    if not summary.get("manual_bbox_grid"):
                        summary["manual_bbox_grid"] = preprocess_summary.get("manual_bbox_grid")
        phase06_xlsx = str(summary.get("phase06_xlsx", ""))
        preprocess_geojson: dict[str, object] | None = None
        phase06_path = Path(phase06_xlsx) if phase06_xlsx else None
        if phase06_path and phase06_path.exists():
            preprocess_geojson = build_original_feature_collection_from_xlsx(phase06_path)
        return {
            "job_id": job_id,
            "source_name": source_name,
            "summary": summary,
            "preprocess_geojson": preprocess_geojson,
            "paused_after_preprocess": True,
            "phase06_download_url": f"/api/process-xlsx/artifact/{job_id}/phase06",
            "continue_url": f"/api/process-xlsx/continue/{job_id}",
            "phase06_xlsx": phase06_xlsx,
        }

    def finalize_job(self, job_id: str) -> tuple[int | None, dict[str, object], dict[str, object]]:
        reap_finished_pipeline_jobs(remove_expired=False)
        with PIPELINE_JOBS_LOCK:
            job = PIPELINE_JOBS.get(job_id)
        if job is None:
            raise FileNotFoundError("Unknown pipeline job.")

        process = job["process"]
        run_dir = Path(job["run_dir"])
        source_name = str(job["source_name"])
        progress_file = run_dir / "progress.json"
        progress_payload: dict[str, object] = {}
        if progress_file.exists():
            progress_payload = json.loads(progress_file.read_text(encoding="utf-8"))

        return_code = process.poll() if process is not None else 0
        if return_code is not None and process is not None:
            _safe_close_handle(job.get("stdout_handle"))
            _safe_close_handle(job.get("stderr_handle"))
            with PIPELINE_JOBS_LOCK:
                active_job = PIPELINE_JOBS.get(job_id)
                if active_job is not None:
                    active_job["process"] = None
                    active_job["stdout_handle"] = None
                    active_job["stderr_handle"] = None
                    active_job["finished_at"] = time.time()
                    if not active_job.get("final_status"):
                        active_job["final_status"] = "completed" if return_code == 0 else "error"
        return return_code, progress_payload, {
            "run_dir": str(run_dir),
            "source_name": source_name,
        }

    def handle_process_status(self, job_id: str) -> None:
        return_code, progress_payload, job_info = self.finalize_job(job_id)
        run_dir = Path(job_info["run_dir"])
        source_name = str(job_info["source_name"])
        with PIPELINE_JOBS_LOCK:
            job = PIPELINE_JOBS.get(job_id)
        if return_code is None:
            running_payload: dict[str, object] = {
                "job_id": job_id,
                "status": progress_payload.get("status", "running"),
                "progress": progress_payload,
            }
            if should_skip_running_preprocess_geojson(job):
                self.send_json(running_payload)
                return
            progress_details = progress_payload.get("details")
            phase06_xlsx = ""
            preprocess_summary_file = ""
            if isinstance(progress_details, dict):
                phase06_xlsx = str(progress_details.get("phase06_xlsx", "")).strip()
                preprocess_summary_file = str(progress_details.get("preprocess_summary_file", "")).strip()
            if not phase06_xlsx:
                phase06_candidate = run_dir / "preprocess" / "phase06_phase1_compatible" / "phase06_phase1_compatible.xlsx"
                if phase06_candidate.exists():
                    phase06_xlsx = str(phase06_candidate)
            if not preprocess_summary_file:
                preprocess_summary_candidate = run_dir / "preprocess" / "summary.json"
                if preprocess_summary_candidate.exists():
                    preprocess_summary_file = str(preprocess_summary_candidate)

            summary: dict[str, object] = {}
            if preprocess_summary_file:
                preprocess_summary_path = Path(preprocess_summary_file)
                if preprocess_summary_path.exists():
                    try:
                        summary = json.loads(preprocess_summary_path.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        summary = {}
            if phase06_xlsx:
                summary.setdefault("phase06_xlsx", phase06_xlsx)
                phase06_path = Path(phase06_xlsx)
                if phase06_path.exists():
                    try:
                        running_payload["preprocess_geojson"] = build_original_feature_collection_from_xlsx(phase06_path)
                        running_payload["summary"] = summary
                        running_payload["source_name"] = source_name
                        running_payload["phase06_xlsx"] = phase06_xlsx
                        running_payload["phase06_download_url"] = f"/api/process-xlsx/artifact/{job_id}/phase06"
                    except (OSError, ValueError):
                        pass
            self.send_json(running_payload)
            return

        if return_code != 0:
            stderr_path = run_dir / "pipeline.stderr.log"
            error_message = "Pipeline execution failed."
            if stderr_path.exists():
                error_text = stderr_path.read_text(encoding="utf-8").strip()
                if error_text:
                    error_message = error_text
            self.send_json(
                {
                    "job_id": job_id,
                    "status": "error",
                    "progress": progress_payload,
                    "error": error_message,
                },
                status_code=500,
            )
            return

        if progress_payload.get("status") == "paused":
            payload = self.build_paused_payload(job_id, run_dir, source_name)
            self.send_json(
                {
                    "job_id": job_id,
                    "status": "paused",
                    "progress": progress_payload,
                    **payload,
                }
            )
            return

        payload = self.build_completed_payload(job_id, run_dir, source_name)
        self.send_json(
            {
                "job_id": job_id,
                "status": "completed",
                "progress": progress_payload,
                **payload,
            }
        )

    def handle_process_xlsx(self) -> None:
        source_name, file_bytes = self.read_upload_request()
        selected_model_id = self.headers.get("X-Selected-Model-Id", "").strip()
        selected_germplasm_names = self.parse_selected_germplasm_names_header()
        forecast_planting_date = self.headers.get("X-Forecast-Planting-Date", "").strip()
        forecast_harvesting_date = self.headers.get("X-Forecast-Harvesting-Date", "").strip()
        pause_after_preprocess = self.headers.get("X-Pause-After-Preprocess", "").strip() == "1"
        climate_scope = self.headers.get("X-Climate-Scope", "point").strip() or "point"
        regional_country = self.headers.get("X-Regional-Country", "").strip()
        regional_bounds_label = self.headers.get("X-Regional-Bounds-Label", "").strip()
        regional_bounds_latitude_min = self.headers.get("X-Regional-Bounds-Latitude-Min", "").strip()
        regional_bounds_latitude_max = self.headers.get("X-Regional-Bounds-Latitude-Max", "").strip()
        regional_bounds_longitude_min = self.headers.get("X-Regional-Bounds-Longitude-Min", "").strip()
        regional_bounds_longitude_max = self.headers.get("X-Regional-Bounds-Longitude-Max", "").strip()
        run_id, run_dir = self.create_pipeline_job(
            source_name,
            file_bytes,
            selected_model_id,
            forecast_planting_date=forecast_planting_date,
            forecast_harvesting_date=forecast_harvesting_date,
            pause_after_preprocess=pause_after_preprocess,
            climate_scope=climate_scope,
            regional_country=regional_country,
            selected_germplasm_names=selected_germplasm_names,
            regional_bounds_label=regional_bounds_label,
            regional_bounds_latitude_min=regional_bounds_latitude_min,
            regional_bounds_latitude_max=regional_bounds_latitude_max,
            regional_bounds_longitude_min=regional_bounds_longitude_min,
            regional_bounds_longitude_max=regional_bounds_longitude_max,
        )
        while True:
            return_code, _, _ = self.finalize_job(run_id)
            if return_code is None:
                time.sleep(0.25)
                continue
            if return_code != 0:
                stderr_path = run_dir / "pipeline.stderr.log"
                error_message = "Pipeline execution failed."
                if stderr_path.exists():
                    error_text = stderr_path.read_text(encoding="utf-8").strip()
                    if error_text:
                        error_message = error_text
                raise RuntimeError(error_message)
            progress_file = run_dir / "progress.json"
            progress_payload = json.loads(progress_file.read_text(encoding="utf-8")) if progress_file.exists() else {}
            if progress_payload.get("status") == "paused":
                payload = self.build_paused_payload(run_id, run_dir, source_name)
                self.send_json(payload)
                return
            payload = self.build_completed_payload(run_id, run_dir, source_name)
            self.send_json(payload)
            return

    def handle_process_artifact(self, job_id: str, artifact_name: str, query: str = "") -> None:
        with PIPELINE_JOBS_LOCK:
            job = PIPELINE_JOBS.get(job_id)
        if job is None:
            raise FileNotFoundError("Unknown pipeline job.")
        run_dir = Path(job["run_dir"])
        filename = ""
        if artifact_name == "phase06":
            artifact_path = run_dir / "preprocess" / "phase06_phase1_compatible" / "phase06_phase1_compatible.xlsx"
            if not artifact_path.exists():
                raise FileNotFoundError("The requested preprocess artifact was not found.")
            filename = "phase06_phase1_compatible.xlsx"
        elif artifact_name == "prediction_output":
            summary_path = run_dir / "summary.json"
            if not summary_path.exists():
                raise FileNotFoundError("The pipeline summary file was not found.")
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            cell_level_workbook = _build_manual_grid_prediction_workbook_bytes(summary)
            if cell_level_workbook is not None:
                workbook_bytes, filename = cell_level_workbook
                self.send_response(200)
                self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                self.send_header(
                    "Content-Disposition",
                    f'attachment; filename="{filename}"',
                )
                self.send_header("Content-Length", str(len(workbook_bytes)))
                self.end_headers()
                self.wfile.write(workbook_bytes)
                return
            artifact_path = Path(summary.get("prediction_xlsx", ""))
            if not artifact_path.exists():
                raise FileNotFoundError("The requested prediction output artifact was not found.")
            filename = artifact_path.name
        elif artifact_name == "geojson":
            summary_path = run_dir / "summary.json"
            if not summary_path.exists():
                raise FileNotFoundError("The pipeline summary file was not found.")
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            geojson = resolve_prediction_feature_collection(summary)
            filename = "pipeline_output.geojson"
            body = json.dumps(geojson, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/geo+json")
            self.send_header(
                "Content-Disposition",
                f'attachment; filename="{filename}"',
            )
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        elif artifact_name == "display_geojson":
            summary_path = run_dir / "summary.json"
            if not summary_path.exists():
                raise FileNotFoundError("The pipeline summary file was not found.")
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            geojson = build_prediction_display_feature_collection(summary)
            filename = "pipeline_display_output.geojson"
            body = json.dumps(geojson, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/geo+json")
            self.send_header(
                "Content-Disposition",
                f'attachment; filename="{filename}"',
            )
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        elif artifact_name == "profile_overlay":
            summary_path = run_dir / "summary.json"
            if not summary_path.exists():
                raise FileNotFoundError("The pipeline summary file was not found.")
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            parsed_query = parse_qs(query or "")
            selected_labels = parsed_query.get("labels", [])
            payload = _build_manual_grid_profile_overlay_payload(summary, selected_labels)
            self.send_json(payload)
            return
        else:
            raise FileNotFoundError("Unknown artifact.")
        content_type = mimetypes.guess_type(str(artifact_path))[0] or "application/octet-stream"
        body = artifact_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header(
            "Content-Disposition",
            f'attachment; filename="{filename}"',
        )
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def handle_models(self) -> None:
        self.send_json({"models": list_models_for_ui()})

    def handle_model_best_model_pkl(self, model_id: str) -> None:
        normalized_model_id = model_id.strip()
        if not normalized_model_id:
            raise ValueError("The model id is empty.")
        registered_model = get_registered_model(normalized_model_id)
        if registered_model is None:
            raise FileNotFoundError(f"The model was not found: {normalized_model_id}")

        metadata = registered_model.metadata
        best_model_file = Path(
            str(metadata.get("best_model_file") or registered_model.model_dir / "best_model_sort_original.pkl")
        )
        if not best_model_file.exists() or not best_model_file.is_file():
            raise FileNotFoundError("The best_model_sort_original.pkl artifact was not found.")
        self.send_binary_file(
            best_model_file,
            download_name=best_model_file.name,
            content_type="application/octet-stream",
        )

    def handle_model_best_features_csv(self, model_id: str) -> None:
        normalized_model_id = model_id.strip()
        if not normalized_model_id:
            raise ValueError("The model id is empty.")
        registered_model = get_registered_model(normalized_model_id)
        if registered_model is None:
            raise FileNotFoundError(f"The model was not found: {normalized_model_id}")

        metadata = registered_model.metadata
        training_input_csv = Path(
            str(metadata.get("phase04_training_input_csv") or registered_model.model_dir / "phase04_training_input.csv")
        )
        sort_original_csv = Path(
            str(metadata.get("sort_original_csv") or registered_model.model_dir / "sort_original.csv")
        )

        header: list[str] = []
        if training_input_csv.exists():
            with training_input_csv.open("r", newline="", encoding="utf-8") as handle:
                reader = csv.reader(handle)
                header = [str(column).strip() for column in next(reader, []) if str(column).strip()]
            header = [column for column in header if column != "Grain Yield (T/Ha)"]
        elif sort_original_csv.exists():
            with sort_original_csv.open("r", newline="", encoding="utf-8") as handle:
                reader = csv.reader(handle)
                header = [str(column).strip() for column in next(reader, []) if str(column).strip()]
        else:
            raise FileNotFoundError("The phase04 training input or sort_original.csv artifact was not found.")

        selected_features = {
            str(value).strip() for value in (metadata.get("selected_features") or []) if str(value).strip()
        }
        feature_rows = [
            (column, "Included" if column in selected_features else "Excluded")
            for column in header
        ]

        workspace_name = str(
            metadata.get("workspace_name")
            or metadata.get("display_name")
            or normalized_model_id
        ).strip() or normalized_model_id
        safe_workspace_name = re.sub(r"[^A-Za-z0-9._-]+", "_", workspace_name).strip("_") or normalized_model_id

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["feature seleccition", "In the Model"])
        for feature_name, inclusion_status in feature_rows:
            writer.writerow([feature_name, inclusion_status])
        body = output.getvalue().encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header(
            "Content-Disposition",
            f'attachment; filename="Feature_Selection_{safe_workspace_name}.csv"',
        )
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def handle_model_optimization_csv(self, model_id: str) -> None:
        normalized_model_id = model_id.strip()
        if not normalized_model_id:
            raise ValueError("The model id is empty.")
        registered_model = get_registered_model(normalized_model_id)
        if registered_model is None:
            raise FileNotFoundError(f"The model was not found: {normalized_model_id}")

        metadata = registered_model.metadata
        optimization_csv = Path(
            str(metadata.get("optimization_csv") or registered_model.model_dir / "optimization_sort_original.csv")
        )
        if not optimization_csv.exists() or not optimization_csv.is_file():
            raise FileNotFoundError("The optimization_sort_original.csv artifact was not found.")
        self.send_binary_file(
            optimization_csv,
            download_name=optimization_csv.name,
            content_type="text/csv; charset=utf-8",
        )

    def handle_model_selection_summary_json(self, model_id: str) -> None:
        normalized_model_id = model_id.strip()
        if not normalized_model_id:
            raise ValueError("The model id is empty.")
        registered_model = get_registered_model(normalized_model_id)
        if registered_model is None:
            raise FileNotFoundError(f"The model was not found: {normalized_model_id}")

        metadata = registered_model.metadata
        selection_summary_file = Path(
            str(metadata.get("selection_summary_file") or registered_model.model_dir / "selection_summary.json")
        )
        if not selection_summary_file.exists():
            raise FileNotFoundError("The selection_summary.json artifact was not found for this model.")

        body = selection_summary_file.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header(
            "Content-Disposition",
            f'attachment; filename="{selection_summary_file.name}"',
        )
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def handle_model_selection_summary_csv(self, model_id: str) -> None:
        normalized_model_id = model_id.strip()
        if not normalized_model_id:
            raise ValueError("The model id is empty.")
        registered_model = get_registered_model(normalized_model_id)
        if registered_model is None:
            raise FileNotFoundError(f"The model was not found: {normalized_model_id}")

        metadata = registered_model.metadata
        selection_summary_file = Path(
            str(metadata.get("selection_summary_file") or registered_model.model_dir / "selection_summary.json")
        )
        if not selection_summary_file.exists():
            raise FileNotFoundError("The selection_summary.json artifact was not found for this model.")

        payload = read_json_file_safe(selection_summary_file)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["section", "field", "value"])
        initial_settings = payload.get("initial_settings", {}) if isinstance(payload, dict) else {}
        divisions = payload.get("divisions", {}) if isinstance(payload, dict) else {}
        for key, value in initial_settings.items():
            writer.writerow(["initial_settings", key, json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value])
        for key, value in divisions.items():
            if isinstance(value, list):
                for item in value:
                    writer.writerow(["divisions", key, item])
            else:
                writer.writerow(["divisions", key, json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value])

        body = output.getvalue().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header(
            "Content-Disposition",
            'attachment; filename="selection_summary.csv"',
        )
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def handle_model_workspace(self, model_id: str) -> None:
        normalized_model_id = model_id.strip()
        if not normalized_model_id:
            raise ValueError("The model id is empty.")
        registered_model = get_registered_model(normalized_model_id)
        if registered_model is None:
            raise FileNotFoundError(f"The model was not found: {normalized_model_id}")
        workspace_payload = build_workspace_payload_response(
            normalize_top_germplasm_payload(
                read_saved_workspace_payload(registered_model),
                model_id=normalized_model_id,
            )
        )
        source_workbook = workspace_payload.get("source_workbook")
        if isinstance(source_workbook, dict):
            normalized_source_workbook = dict(source_workbook)
            normalized_source_workbook["url"] = f"/api/models/{normalized_model_id}/source-workbook.xlsx"
            workspace_payload["source_workbook"] = normalized_source_workbook
        self.send_json(workspace_payload)

    def handle_model_training_results_download(self, model_id: str) -> None:
        normalized_model_id = model_id.strip()
        if not normalized_model_id:
            raise ValueError("The model id is empty.")
        registered_model = get_registered_model(normalized_model_id)
        if registered_model is None:
            raise FileNotFoundError(f"The model was not found: {normalized_model_id}")
        metadata = registered_model.metadata
        training_summary_file = Path(
            str(metadata.get("workspace_training_summary_file") or registered_model.model_dir / "workspace_training_summary.json")
        )
        if not training_summary_file.exists():
            raise FileNotFoundError("The training summary was not found for this workspace.")
        training_results_file, download_name = resolve_workspace_training_results_file(registered_model)
        self.send_binary_file(
            training_results_file,
            download_name=download_name,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    def handle_model_top_germplasm_download(self, model_id: str) -> None:
        normalized_model_id = model_id.strip()
        if not normalized_model_id:
            raise ValueError("The model id is empty.")
        registered_model = get_registered_model(normalized_model_id)
        if registered_model is None:
            raise FileNotFoundError(f"The model was not found: {normalized_model_id}")
        metadata = registered_model.metadata
        top_download_file = Path(
            str(metadata.get("workspace_top_germplasm_download_file") or registered_model.model_dir / "workspace_top_germplasm.xlsx")
        )
        if not top_download_file.exists():
            raise FileNotFoundError("The Top Germplasm download file was not found for this workspace.")
        self.send_binary_file(
            top_download_file,
            download_name=top_download_file.name,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    def handle_model_source_workbook_download(self, model_id: str) -> None:
        normalized_model_id = model_id.strip()
        if not normalized_model_id:
            raise ValueError("The model id is empty.")
        registered_model = get_registered_model(normalized_model_id)
        if registered_model is None:
            raise FileNotFoundError(f"The model was not found: {normalized_model_id}")
        metadata = registered_model.metadata
        source_workbook_file = Path(
            str(metadata.get("workspace_source_workbook") or registered_model.model_dir / "workspace_source.xlsx")
        )
        if not source_workbook_file.exists():
            raise FileNotFoundError("The workspace source workbook was not found for this workspace.")
        self.send_binary_file(
            source_workbook_file,
            download_name=source_workbook_file.name,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    def handle_germplasm_options(self) -> None:
        source_name, file_bytes = self.read_upload_request()
        selected_model_id = self.headers.get("X-Selected-Model-Id", "").strip()
        climate_scope = self.headers.get("X-Climate-Scope", "regional_manual").strip() or "regional_manual"
        selected_id_header = self.headers.get("X-Selected-Id-Header", "").strip()
        prediction_mode = self.headers.get("X-Prediction-Germplasm-Mode", "").strip().lower()
        PIPELINE_RUNS_DIR.mkdir(parents=True, exist_ok=True)
        preview_dir = PIPELINE_RUNS_DIR / f"preview-{uuid.uuid4().hex[:8]}"
        preview_dir.mkdir(parents=True, exist_ok=True)
        workbook_path = preview_dir / source_name
        workbook_path.write_bytes(file_bytes)
        if selected_model_id:
            validate_saved_model_prediction_workbook_for_names(
                workbook_path,
                selected_model_id=selected_model_id,
                climate_scope=climate_scope,
            )
        germplasm_description = describe_distinct_germplasm_names_from_xlsx(
            workbook_path,
            selected_id_header=selected_id_header,
            require_farm_column=prediction_mode == "uploaded",
        )
        names = list(germplasm_description.get("germplasm_names", []))
        self.send_json(
            {
                "source_name": source_name,
                "headers": germplasm_description.get("headers", []),
                "id_field_candidates": germplasm_description.get("id_field_candidates", []),
                "germplasm_names": names,
                "count": len(names),
                "germplasm_profiles_by_name": germplasm_description.get("germplasm_profiles_by_name", {}),
                "selected_id_header": germplasm_description.get("selected_id_header", ""),
                "germplasm_id_values_by_name": germplasm_description.get("germplasm_id_values_by_name", {}),
            }
        )

    def handle_original_data_preview(self) -> None:
        source_name, file_bytes = self.read_upload_request()
        PIPELINE_RUNS_DIR.mkdir(parents=True, exist_ok=True)
        preview_dir = PIPELINE_RUNS_DIR / f"preview-{uuid.uuid4().hex[:8]}"
        preview_dir.mkdir(parents=True, exist_ok=True)
        workbook_path = preview_dir / source_name
        workbook_path.write_bytes(file_bytes)
        geojson = build_original_feature_collection_from_xlsx(workbook_path)
        self.send_json(
            {
                "source_name": source_name,
                "geojson": geojson,
                "count": len(geojson.get("features", [])),
            }
        )

    def handle_selecction_properties_metadata(self) -> None:
        source_name, file_bytes = self.read_upload_request()
        PIPELINE_RUNS_DIR.mkdir(parents=True, exist_ok=True)
        preview_dir = PIPELINE_RUNS_DIR / f"preview-{uuid.uuid4().hex[:8]}"
        preview_dir.mkdir(parents=True, exist_ok=True)
        workbook_path = preview_dir / source_name
        workbook_path.write_bytes(file_bytes)
        validate_required_workbook_headers(workbook_path, ("Name", "Farm"))
        workbook_description = describe_workbook_columns(workbook_path)
        self.send_json(
            {
                "source_name": source_name,
                "headers": workbook_description.get("headers", []),
                "row_count": workbook_description.get("row_count", 0),
                "attribute_count": workbook_description.get("attribute_count", 0),
                "column_profiles": workbook_description.get("column_profiles", {}),
            }
        )

    def handle_selecction_properties_preview(self) -> None:
        source_name, file_bytes = self.read_upload_request()
        target_column = self.headers.get("X-Target-Column", "").strip()
        latitude_column = self.headers.get("X-Latitude-Column", "").strip()
        longitude_column = self.headers.get("X-Longitude-Column", "").strip()
        if not target_column:
            raise ValueError("Select a target variable before previewing the workbook.")
        if not latitude_column or not longitude_column:
            raise ValueError("Select both latitude and longitude columns before previewing the workbook.")
        if latitude_column == longitude_column:
            raise ValueError("Latitude and longitude columns must be different.")
        if target_column in {latitude_column, longitude_column}:
            raise ValueError("The target variable must be different from latitude and longitude columns.")
        PIPELINE_RUNS_DIR.mkdir(parents=True, exist_ok=True)
        preview_dir = PIPELINE_RUNS_DIR / f"preview-{uuid.uuid4().hex[:8]}"
        preview_dir.mkdir(parents=True, exist_ok=True)
        workbook_path = preview_dir / source_name
        workbook_path.write_bytes(file_bytes)
        validate_required_workbook_headers(workbook_path, ("Name", "Farm"))
        workbook_description = describe_workbook_columns(workbook_path)
        geojson = build_original_feature_collection_from_xlsx(
            workbook_path,
            latitude_header=latitude_column,
            longitude_header=longitude_column,
            target_header=target_column,
        )
        self.send_json(
            {
                "source_name": source_name,
                "headers": workbook_description.get("headers", []),
                "row_count": workbook_description.get("row_count", 0),
                "attribute_count": workbook_description.get("attribute_count", 0),
                "column_profiles": workbook_description.get("column_profiles", {}),
                "geojson": geojson,
                "count": len(geojson.get("features", [])),
                "selection": {
                    "target_column": target_column,
                    "latitude_column": latitude_column,
                    "longitude_column": longitude_column,
                },
            }
        )

    def handle_selecction_properties_summary(self) -> None:
        source_name, file_bytes = self.read_upload_request()
        target_column = self.headers.get("X-Target-Column", "").strip()
        latitude_column = self.headers.get("X-Latitude-Column", "").strip()
        longitude_column = self.headers.get("X-Longitude-Column", "").strip()
        planting_date_column = self.headers.get("X-Planting-Date-Column", "").strip()
        harvesting_date_column = self.headers.get("X-Harvesting-Date-Column", "").strip()
        soil_texture_column = self.headers.get("X-Soil-Texture-Column", "").strip()
        soil_depth_column = self.headers.get("X-Soil-Depth-Column", "").strip()
        identifier_columns = self.parse_json_list_header("X-Identifier-Columns")
        categorical_columns = self.parse_json_list_header("X-Categorical-Columns")
        quantitative_columns = self.parse_json_list_header("X-Quantitative-Columns")
        no_defined_columns = self.parse_json_list_header("X-No-Defined-Columns")
        workspace_name = self.headers.get("X-Workspace-Name", "").strip()
        if not all([target_column, latitude_column, longitude_column, planting_date_column, harvesting_date_column, soil_texture_column, soil_depth_column]):
            raise ValueError("Complete Initial Settings before executing Summary.")
        if not identifier_columns:
            raise ValueError("Select at least one Germplams Identifier before executing Summary.")
        if not categorical_columns and not quantitative_columns:
            raise ValueError("Select at least one column as Categorical Data or Quantitative Data before executing Summary.")

        PIPELINE_RUNS_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        run_dir = PIPELINE_RUNS_DIR / f"selection-summary-{timestamp}-{uuid.uuid4().hex[:6]}"
        run_dir.mkdir(parents=True, exist_ok=True)
        run_id = run_dir.name

        uploaded_workbook_path = run_dir / source_name
        uploaded_workbook_path.write_bytes(file_bytes)
        resolved_required_headers = validate_required_workbook_headers(
            uploaded_workbook_path,
            ("Name", "Farm"),
        )
        workbook_description = describe_workbook_columns(uploaded_workbook_path)
        workbook_headers = [
            str(header or "").strip()
            for header in workbook_description.get("headers", [])
            if str(header or "").strip()
        ]
        mandatory_identifier_columns = [
            resolved_required_headers["Name"],
            resolved_required_headers["Farm"],
        ]
        normalized_identifier_columns: list[str] = []
        for column in [*mandatory_identifier_columns, *identifier_columns]:
            normalized_column = str(column or "").strip()
            if not normalized_column or normalized_column in normalized_identifier_columns:
                continue
            normalized_identifier_columns.append(normalized_column)
        dg_columns = [header for header in workbook_headers if DG_HEADER_PATTERN.match(header)]
        summary_payload = {
            "workflow": "selecctionProperties",
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "workspace_name": workspace_name,
            "source_name": source_name,
            "source_workbook": str(uploaded_workbook_path),
            "column_profiles": workbook_description.get("column_profiles", {}),
            "initial_settings": {
                "target_column": target_column,
                "longitude_column": longitude_column,
                "latitude_column": latitude_column,
                "planting_date_column": planting_date_column,
                "harvesting_date_column": harvesting_date_column,
                "soil_texture_column": soil_texture_column,
                "soil_depth_column": soil_depth_column,
            },
            "divisions": {
                "germplams_identifiers": normalized_identifier_columns,
                "categorical_data": categorical_columns,
                "cuantitative_data": quantitative_columns,
                "no_defined_data": no_defined_columns,
                "DG": dg_columns,
            },
            "row_count": workbook_description.get("row_count", 0),
            "attribute_count": workbook_description.get("attribute_count", 0),
            "headers": workbook_headers,
            "preprocess_disabled": True,
            "training_disabled": True,
            "prediction_disabled": True,
        }
        summary_path = run_dir / "selection_summary.json"
        summary_path.write_text(json.dumps(summary_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        new_input_name = f"newInput{timestamp}.xlsx"
        new_input_path = run_dir / new_input_name
        new_input_path.write_bytes(file_bytes)

        ce_phase01_dir = run_dir / "ce_pipeline" / "phase01"
        ce_phase01_dir.mkdir(parents=True, exist_ok=True)
        phase1_path = ce_phase01_dir / "phase1.xlsx"
        ce_phase02_dir = run_dir / "ce_pipeline" / "phase02"
        ce_phase02_dir.mkdir(parents=True, exist_ok=True)
        phase2_path = ce_phase02_dir / "phase02.xlsx"
        phase2_log_path = ce_phase02_dir / "phase02_log.json"
        ce_phase03_dir = run_dir / "ce_pipeline" / "phase03"
        ce_phase03_dir.mkdir(parents=True, exist_ok=True)
        phase3_path = ce_phase03_dir / "phase03.xlsx"
        phase3_log_path = ce_phase03_dir / "phase03_log.json"
        ce_phase04_dir = run_dir / "ce_pipeline" / "phase04"
        ce_phase04_dir.mkdir(parents=True, exist_ok=True)
        phase4_path = ce_phase04_dir / "phase04.xlsx"
        phase4_log_path = ce_phase04_dir / "phase04_log.json"
        ce_training_dir = run_dir / "ce_pipeline" / "training"
        ce_training_dir.mkdir(parents=True, exist_ok=True)
        ce_phase06_dir = run_dir / "ce_pipeline" / "phase06"
        ce_phase06_dir.mkdir(parents=True, exist_ok=True)
        progress_file = run_dir / "ce_summary_progress.json"
        preview_file = run_dir / "ce_phase03_preview.json"
        result_file = run_dir / "ce_summary_result.json"
        download_enabled = get_ce_pipeline_download_enabled()
        training_results_download_enabled = get_training_results_download_dev_enabled()
        download_url = f"/api/process-xlsx/selecction-properties/download?run_id={run_id}&phase=phase04" if download_enabled else ""
        training_input_download_url = f"/api/process-xlsx/selecction-properties/download?run_id={run_id}&phase=phase04_training_input" if download_enabled else ""

        write_ce_summary_progress(
            progress_file,
            status="running",
            percent=3,
            stage="Preparing ce_pipeline",
            message=f"Preparing ce_pipeline files for {source_name}.",
            details={
                "run_id": run_id,
                "source_name": source_name,
                "input_row_count": workbook_description.get("row_count", 0),
            },
        )

        def run_summary_job() -> None:
            try:
                if not CE_PHASE01_SCRIPT.is_file():
                    raise FileNotFoundError(f"The ce_pipeline phase1 script was not found: {CE_PHASE01_SCRIPT}")
                if not CE_PHASE02_SCRIPT.is_file():
                    raise FileNotFoundError(f"The ce_pipeline phase02 script was not found: {CE_PHASE02_SCRIPT}")
                if not CE_PHASE03_SCRIPT.is_file():
                    raise FileNotFoundError(f"The ce_pipeline phase03 script was not found: {CE_PHASE03_SCRIPT}")
                if not CE_PHASE04_SCRIPT.is_file():
                    raise FileNotFoundError(f"The ce_pipeline phase04 script was not found: {CE_PHASE04_SCRIPT}")
                if not CE_TRAINING_SCRIPT.is_file():
                    raise FileNotFoundError(f"The ce_pipeline training script was not found: {CE_TRAINING_SCRIPT}")
                if not CE_PHASE06_SCRIPT.is_file():
                    raise FileNotFoundError(f"The ce_pipeline phase06 script was not found: {CE_PHASE06_SCRIPT}")

                write_ce_summary_progress(
                    progress_file,
                    status="running",
                    percent=8,
                    stage="Executing phase01",
                    message="Creating phase01 workbook from the uploaded workbook and the stepper definition.",
                    details={"phase": "phase01", "run_id": run_id},
                )
                completed_phase1 = subprocess.run(
                    [
                        str(self.pipeline_python),
                        str(CE_PHASE01_SCRIPT),
                        "--source-workbook",
                        str(uploaded_workbook_path),
                        "--definition-file",
                        str(summary_path),
                        "--output-file",
                        str(phase1_path),
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                    cwd=str(APP_DIR),
                )
                phase1_payload = json.loads(completed_phase1.stdout.strip() or "{}")
                write_ce_summary_progress(
                    progress_file,
                    status="running",
                    percent=15,
                    stage="Executing phase02",
                    message=(
                        f"phase01 complete. Validating {phase1_payload.get('row_count', 0)} rows against required Initial Settings fields."
                    ),
                    details={
                        "phase": "phase02",
                        "phase01_row_count": phase1_payload.get("row_count", 0),
                        "phase01_column_count": phase1_payload.get("column_count", 0),
                    },
                )
                completed_phase2 = subprocess.run(
                    [
                        str(self.pipeline_python),
                        str(CE_PHASE02_SCRIPT),
                        "--phase01-workbook",
                        str(phase1_path),
                        "--definition-file",
                        str(summary_path),
                        "--output-file",
                        str(phase2_path),
                        "--log-file",
                        str(phase2_log_path),
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                    cwd=str(APP_DIR),
                )
                phase2_payload = json.loads(completed_phase2.stdout.strip() or "{}")
                phase2_kept_rows = int(phase2_payload.get("kept_row_count", 0) or 0)
                phase2_removed_rows = int(phase2_payload.get("removed_row_count", 0) or 0)
                write_ce_summary_progress(
                    progress_file,
                    status="running",
                    percent=15,
                    stage="Executing phase03",
                    message=(
                        f"phase02 complete. Preparing climate enrichment for {phase2_kept_rows} records after removing {phase2_removed_rows} rows."
                    ),
                    details={
                        "phase": "phase03",
                        "phase02_kept_row_count": phase2_kept_rows,
                        "phase02_removed_row_count": phase2_removed_rows,
                        "nasa_processed_rows": 0,
                        "nasa_total_rows": phase2_kept_rows,
                        "nasa_cached_rows": 0,
                        "nasa_fresh_queries": 0,
                        "soil_skipped": True,
                    },
                )
                completed_phase3 = subprocess.run(
                    [
                        str(self.pipeline_python),
                        str(CE_PHASE03_SCRIPT),
                        "--phase02-workbook",
                        str(phase2_path),
                        "--definition-file",
                        str(summary_path),
                        "--output-file",
                        str(phase3_path),
                        "--log-file",
                        str(phase3_log_path),
                        "--progress-file",
                        str(progress_file),
                        "--skip-soil-enrichment",
                        "1",
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                    cwd=str(APP_DIR),
                )
                phase3_payload = json.loads(completed_phase3.stdout.strip() or "{}")
                phase3_geojson = build_original_feature_collection_from_xlsx(
                    phase3_path,
                    latitude_header=latitude_column,
                    longitude_header=longitude_column,
                    target_header=target_column,
                )
                ce_pipeline_summary = build_ce_pipeline_summary(
                    source_name=source_name,
                    phase3_path=phase3_path,
                    phase1_payload=phase1_payload,
                    phase2_payload=phase2_payload,
                    phase3_payload=phase3_payload,
                    selection_summary=summary_payload,
                )
                write_json_file_atomic(
                    preview_file,
                    {
                        "source_name": source_name,
                        "phase3_name": phase3_path.name,
                        "geojson": phase3_geojson,
                        "summary": ce_pipeline_summary,
                    },
                )
                write_ce_summary_progress(
                    progress_file,
                    status="running",
                    percent=50,
                    stage="Executing phase04",
                    message="phase03 complete. Preparing the ce_pipeline training dataset from the selected quantitative and categorical columns.",
                    details={"phase": "phase04", "run_id": run_id},
                )
                completed_phase4 = subprocess.run(
                    [
                        str(self.pipeline_python),
                        str(CE_PHASE04_SCRIPT),
                        "--phase03-workbook",
                        str(phase3_path),
                        "--definition-file",
                        str(summary_path),
                        "--output-file",
                        str(phase4_path),
                        "--log-file",
                        str(phase4_log_path),
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                    cwd=str(APP_DIR),
                )
                phase4_payload = json.loads(completed_phase4.stdout.strip() or "{}")
                write_ce_summary_progress(
                    progress_file,
                    status="running",
                    percent=50,
                    stage="Executing ce_pipeline training",
                    message="phase04 complete. Launching FeatureHero training with the target selected in Initial Settings.",
                    details={"phase": "training", "run_id": run_id},
                )
                completed_training = subprocess.run(
                    [
                        str(self.pipeline_python),
                        str(CE_TRAINING_SCRIPT),
                        "--phase04-workbook",
                        str(phase4_path),
                        "--training-input-csv",
                        str(ce_phase04_dir / "phase04_training_input.csv"),
                        "--run-dir",
                        str(ce_training_dir),
                        "--source-name",
                        source_name,
                        "--target-column",
                        target_column,
                        "--progress-file",
                        str(progress_file),
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                    cwd=str(APP_DIR),
                )
                training_payload = json.loads(completed_training.stdout.strip() or "{}")
                write_json_file_atomic(
                    preview_file,
                    {
                        "source_name": source_name,
                        "phase3_name": phase3_path.name,
                        "geojson": phase3_geojson,
                        "summary": ce_pipeline_summary,
                        "training_geojson": training_payload.get("geojson", {}) if isinstance(training_payload, dict) else {},
                        "training_summary": training_payload.get("summary", {}) if isinstance(training_payload, dict) else {},
                        "prediction_geojson": training_payload.get("prediction_geojson", training_payload.get("geojson", {})) if isinstance(training_payload, dict) else {},
                        "prediction_summary": training_payload.get("prediction_summary", training_payload.get("summary", {})) if isinstance(training_payload, dict) else {},
                    },
                )
                phase06_payload = None
                if TOP_GERMPLASM_ENABLED:
                    write_ce_summary_progress(
                        progress_file,
                        status="running",
                        percent=96,
                        stage="Executing phase06",
                        message="Training complete. Building the Top Germplasm dataset using the saved model and the original workbook.",
                        details={"phase": "phase06", "run_id": run_id},
                    )
                    completed_phase06 = subprocess.run(
                        [
                            str(self.pipeline_python),
                            str(CE_PHASE06_SCRIPT),
                            "--source-workbook",
                            str(uploaded_workbook_path),
                            "--definition-file",
                            str(summary_path),
                            "--run-dir",
                            str(ce_phase06_dir),
                            "--selected-model-id",
                            str((training_payload.get("summary", {}) if isinstance(training_payload, dict) else {}).get("phase_analysis_model_id", "")).strip(),
                            "--source-name",
                            source_name,
                            "--progress-file",
                            str(progress_file),
                        ],
                        check=True,
                        capture_output=True,
                        text=True,
                        cwd=str(APP_DIR),
                    )
                    phase06_payload = json.loads(completed_phase06.stdout.strip() or "{}")
                    if isinstance(phase06_payload.get("summary"), dict):
                        top_download_url = f"/api/process-xlsx/selecction-properties/download?run_id={run_id}&phase=top_germplasm"
                        phase06_payload["summary"]["download_url"] = top_download_url
                    write_json_file_atomic(
                        preview_file,
                        {
                            "source_name": source_name,
                            "phase3_name": phase3_path.name,
                            "geojson": phase3_geojson,
                            "summary": ce_pipeline_summary,
                            "training_geojson": training_payload.get("geojson", {}) if isinstance(training_payload, dict) else {},
                            "training_summary": training_payload.get("summary", {}) if isinstance(training_payload, dict) else {},
                            "prediction_geojson": training_payload.get("prediction_geojson", training_payload.get("geojson", {})) if isinstance(training_payload, dict) else {},
                            "prediction_summary": training_payload.get("prediction_summary", training_payload.get("summary", {})) if isinstance(training_payload, dict) else {},
                            "top_germplasm_geojson": phase06_payload.get("geojson", {}) if isinstance(phase06_payload, dict) else {},
                            "top_germplasm_summary": phase06_payload.get("summary", {}) if isinstance(phase06_payload, dict) else {},
                        },
                    )
                saved_model_id = str((training_payload.get("summary", {}) if isinstance(training_payload, dict) else {}).get("phase_analysis_model_id", "")).strip()
                if saved_model_id:
                    saved_model = get_registered_model(saved_model_id)
                    if saved_model is not None:
                        saved_model_metadata = persist_workspace_artifacts(
                            model_dir=saved_model.model_dir,
                            metadata=saved_model.metadata,
                            selection_summary=summary_payload,
                            source_workbook_path=uploaded_workbook_path,
                            original_geojson=phase3_geojson,
                            original_summary=ce_pipeline_summary,
                            training_geojson=training_payload.get("geojson", {}) if isinstance(training_payload, dict) else {},
                            training_summary=training_payload.get("summary", {}) if isinstance(training_payload, dict) else {},
                            prediction_geojson=training_payload.get("prediction_geojson", training_payload.get("geojson", {})) if isinstance(training_payload, dict) else {},
                            prediction_summary=training_payload.get("prediction_summary", training_payload.get("summary", {})) if isinstance(training_payload, dict) else {},
                            top_germplasm_geojson=phase06_payload.get("geojson", {}) if isinstance(phase06_payload, dict) else {},
                            top_germplasm_summary=phase06_payload.get("summary", {}) if isinstance(phase06_payload, dict) else {},
                        )
                        workspace_display_name = str(saved_model_metadata.get("display_name", "")).strip()
                        if workspace_display_name and isinstance(training_payload.get("summary"), dict):
                            training_payload["summary"]["prediction_model_display_name"] = workspace_display_name
                        if workspace_display_name and isinstance(training_payload.get("prediction_summary"), dict):
                            training_payload["prediction_summary"]["prediction_model_display_name"] = workspace_display_name
                training_results_download_url = ""
                training_results_download_name = ""
                training_summary_payload = training_payload.get("summary", {}) if isinstance(training_payload, dict) else {}
                training_prediction_xlsx = Path(str(training_summary_payload.get("prediction_xlsx", "")).strip())
                if training_results_download_enabled and training_prediction_xlsx.exists() and training_prediction_xlsx.is_file():
                    training_results_download_url = f"/api/process-xlsx/selecction-properties/download?run_id={run_id}&phase=training_results"
                    training_results_download_name = training_prediction_xlsx.name
                    if isinstance(training_summary_payload, dict):
                        training_summary_payload["download_url"] = training_results_download_url
                        training_summary_payload["download_file_name"] = training_results_download_name
                        training_payload["summary"] = training_summary_payload
                result_payload = {
                    "status": "ok",
                    "source_name": source_name,
                    "run_id": run_id,
                    "run_dir": str(run_dir),
                    "summary_file": str(summary_path),
                    "new_input_file": str(new_input_path),
                    "new_input_name": new_input_name,
                    "phase1_file": str(phase1_path),
                    "phase1_name": phase1_path.name,
                    "phase1": phase1_payload,
                    "phase2_file": str(phase2_path),
                    "phase2_name": phase2_path.name,
                    "phase2_log_file": str(phase2_log_path),
                    "phase2": phase2_payload,
                    "phase3_file": str(phase3_path),
                    "phase3_name": phase3_path.name,
                    "phase3_log_file": str(phase3_log_path),
                    "phase3": phase3_payload,
                    "phase4_file": str(phase4_path),
                    "phase4_name": phase4_path.name,
                    "phase4_log_file": str(phase4_log_path),
                    "phase4": phase4_payload,
                    "phase4_training_input_file": str(ce_phase04_dir / "phase04_training_input.xlsx"),
                    "phase4_training_input_name": "phase04_training_input.xlsx",
                    "geojson": phase3_geojson,
                    "summary": ce_pipeline_summary,
                    "training_geojson": training_payload.get("geojson", {}),
                    "training_summary": training_payload.get("summary", {}),
                    "prediction_geojson": training_payload.get("prediction_geojson", training_payload.get("geojson", {})),
                    "prediction_summary": training_payload.get("prediction_summary", training_payload.get("summary", {})),
                    "top_germplasm_geojson": phase06_payload.get("geojson", {}) if isinstance(phase06_payload, dict) else {},
                    "top_germplasm_summary": phase06_payload.get("summary", {}) if isinstance(phase06_payload, dict) else {},
                    "download_enabled": download_enabled,
                    "download_url": download_url,
                    "training_input_download_url": training_input_download_url,
                    "training_results_download_enabled": training_results_download_enabled,
                    "training_results_download_url": training_results_download_url,
                    "training_results_download_name": training_results_download_name,
                    "generated_at": summary_payload["generated_at"],
                }
                write_json_file_atomic(result_file, result_payload)
                nasa_metadata = phase3_payload.get("nasa", {}) if isinstance(phase3_payload, dict) else {}
                total_rows = int(nasa_metadata.get("total_rows", phase2_kept_rows) or phase2_kept_rows or 0)
                cached_rows = int(nasa_metadata.get("nasa_cache_hits", 0) or 0)
                fresh_queries = int(nasa_metadata.get("nasa_cache_fresh_queries_this_run", 0) or 0)
                write_ce_summary_progress(
                    progress_file,
                    status="completed",
                    percent=100,
                    stage="ce_pipeline complete",
                    message=(
                        f"ce_pipeline complete. Climate raster processing covered {total_rows}/{total_rows} records. "
                        f"New queries this run: {fresh_queries}. Cached records served: {cached_rows}."
                    ),
                    details={
                        "phase": "training",
                        "nasa_processed_rows": total_rows,
                        "nasa_total_rows": total_rows,
                        "nasa_cached_rows": cached_rows,
                        "nasa_fresh_queries": fresh_queries,
                        "soil_skipped": True,
                        "run_id": run_id,
                    },
                )
            except subprocess.CalledProcessError as error:
                write_ce_summary_progress(
                    progress_file,
                    status="error",
                    percent=100,
                    stage="ce_pipeline error",
                    message=format_called_process_error(error),
                    details={"run_id": run_id},
                )
            except Exception as error:
                write_ce_summary_progress(
                    progress_file,
                    status="error",
                    percent=100,
                    stage="ce_pipeline error",
                    message=str(error),
                    details={"run_id": run_id},
                )

        worker = threading.Thread(target=run_summary_job, daemon=True)
        with CE_SUMMARY_JOBS_LOCK:
            CE_SUMMARY_JOBS[run_id] = {
                "thread": worker,
                "run_dir": run_dir,
                "progress_file": progress_file,
                "result_file": result_file,
                "source_name": source_name,
            }
        worker.start()
        self.send_json(
            {
                "status": "running",
                "job_id": run_id,
                "run_id": run_id,
                "status_url": f"/api/process-xlsx/selecction-properties/status/{run_id}",
                "result_url": f"/api/process-xlsx/selecction-properties/result/{run_id}",
                "source_name": source_name,
                "generated_at": summary_payload["generated_at"],
            }
        )

    def load_ce_summary_job(self, job_id: str) -> dict[str, object]:
        with CE_SUMMARY_JOBS_LOCK:
            job = CE_SUMMARY_JOBS.get(job_id)
        if job is None:
            recovered_run_dir = PIPELINE_RUNS_DIR / job_id
            recovered_progress_file = recovered_run_dir / "ce_summary_progress.json"
            recovered_result_file = recovered_run_dir / "ce_summary_result.json"
            if recovered_run_dir.exists() and (recovered_progress_file.exists() or recovered_result_file.exists()):
                recovered_source_name = ""
                selection_summary_file = recovered_run_dir / "selection_summary.json"
                if selection_summary_file.exists():
                    recovered_summary_payload = read_json_file_safe(selection_summary_file)
                    recovered_source_name = str(recovered_summary_payload.get("source_name") or "")
                job = {
                    "run_dir": recovered_run_dir,
                    "progress_file": recovered_progress_file,
                    "result_file": recovered_result_file,
                    "source_name": recovered_source_name,
                }
            else:
                raise FileNotFoundError("Unknown ce_pipeline summary job.")
        return job

    def build_ce_summary_response_payload(self, job_id: str) -> tuple[dict[str, object], Path, Path, str]:
        job = self.load_ce_summary_job(job_id)
        progress_file = Path(job["progress_file"])
        result_file = Path(job["result_file"])
        if progress_file.exists():
            try:
                progress_payload = read_json_file_safe(progress_file)
            except (OSError, ValueError, json.JSONDecodeError):
                progress_payload = {
                    "status": "running",
                    "percent": 5,
                    "stage": "Preparing ce_pipeline",
                    "message": "Preparing ce_pipeline files.",
                }
        else:
            progress_payload = {
                "status": "running",
                "percent": 5,
                "stage": "Preparing ce_pipeline",
                "message": "Preparing ce_pipeline files.",
            }
        status = str(progress_payload.get("status") or "running")
        response_payload = {
            "job_id": job_id,
            "status": status,
            "progress": progress_payload,
            "source_name": str(job.get("source_name") or ""),
            "result_url": f"/api/process-xlsx/selecction-properties/result/{job_id}",
        }
        preview_file = Path(job.get("run_dir")) / "ce_phase03_preview.json"
        if status != "completed" and preview_file.exists():
            try:
                preview_payload = read_json_file_safe(preview_file)
            except (OSError, ValueError, json.JSONDecodeError):
                preview_payload = {}
            if preview_payload:
                response_payload.update(preview_payload)
        return response_payload, progress_file, result_file, status

    def handle_selecction_properties_summary_status(self, job_id: str) -> None:
        response_payload, _, result_file, status = self.build_ce_summary_response_payload(job_id)
        if status == "completed":
            if not result_file.exists():
                self.send_json({**response_payload, "status": "running"})
                return
            self.send_json({**response_payload, "status": "completed", "result_ready": True})
            return
        if status == "error":
            progress_payload = response_payload.get("progress", {})
            self.send_json(
                {
                    **response_payload,
                    "error": str(progress_payload.get("message") or "The ce_pipeline summary execution failed."),
                },
                status_code=500,
            )
            return
        self.send_json(response_payload)

    def handle_selecction_properties_summary_result(self, job_id: str) -> None:
        response_payload, _, result_file, status = self.build_ce_summary_response_payload(job_id)
        if status != "completed":
            self.send_json({**response_payload, "result_ready": False})
            return
        if not result_file.exists():
            self.send_json({**response_payload, "status": "running", "result_ready": False})
            return
        try:
            result_payload = read_json_file_safe(result_file)
        except (OSError, ValueError, json.JSONDecodeError):
            self.send_json({**response_payload, "status": "running", "result_ready": False})
            return
        normalized_result_payload = normalize_top_germplasm_payload(result_payload, run_id=job_id)
        self.send_json({**response_payload, **normalized_result_payload, "status": "completed", "result_ready": True})

    def handle_rename_model(self, model_id: str) -> None:
        normalized_model_id = model_id.strip()
        if not normalized_model_id:
            raise ValueError("The model id is empty.")
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0:
            raise ValueError("The request body is empty.")
        payload = json.loads(self.rfile.read(content_length))
        display_name = str(payload.get("display_name", "")).strip()
        if not display_name:
            raise ValueError("The model display name is required.")
        updated_model = rename_registered_model(normalized_model_id, display_name)
        if updated_model is None:
            raise FileNotFoundError(f"The model was not found: {normalized_model_id}")
        self.send_json(
            {
                "updated": True,
                "model_id": normalized_model_id,
                "display_name": updated_model.metadata.get("display_name", ""),
            }
        )

    def handle_delete_model(self, model_id: str) -> None:
        normalized_model_id = model_id.strip()
        if not normalized_model_id:
            raise FileNotFoundError("The model id is empty.")
        if not delete_registered_model(normalized_model_id):
            raise FileNotFoundError(f"The model was not found: {normalized_model_id}")
        self.send_json({"deleted": True, "model_id": normalized_model_id})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the app static server with pipeline API.")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind.")
    parser.add_argument("--open-browser", action="store_true", help="Open the app in a browser tab.")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    port = args.port if args.port > 0 else find_free_port()
    handler = partial(AppRequestHandler, directory=str(APP_DIR))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    server.daemon_threads = True

    if args.open_browser:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        time.sleep(0.35)
        webbrowser.open(f"http://127.0.0.1:{port}{APP_URL_PATH}", new=1)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            server.shutdown()
            server.server_close()
        return

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    os.chdir(ROOT_DIR)
    main()
