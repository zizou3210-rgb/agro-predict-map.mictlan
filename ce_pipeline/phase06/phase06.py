#!/usr/bin/env python3
from __future__ import annotations

if __package__ in {None, ""}:
    import sys
    from pathlib import Path

    APP_BOOT_DIR = Path(__file__).resolve().parents[2]
    PACKAGE_PARENT = APP_BOOT_DIR
    if str(PACKAGE_PARENT) not in sys.path:
        sys.path.insert(0, str(PACKAGE_PARENT))

import argparse
import json
from dataclasses import dataclass
from datetime import datetime
import re
from pathlib import Path
from typing import Callable

import pandas as pd

from ce_pipeline.phase01.phase1 import create_phase1_workbook
from ce_pipeline.phase02.phase02 import create_phase02_workbook
from ce_pipeline.phase03.script03 import create_phase03_workbook
from ce_pipeline.phase04.phase04 import create_phase04_workbook
from ce_pipeline.phase05.phase05 import run_ce_phase05
from pipeline.common import dataframe_to_geojson


PREDICTED_COLUMN = "Grain Yield predicted"
ProgressCallback = Callable[[int, str, str, dict[str, object] | None], None]


def slugify_workspace_name(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", str(value or "").strip())
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized or "workspace"


def write_progress(
    progress_file: Path | None,
    *,
    percent: int,
    stage: str,
    message: str,
    details: dict[str, object] | None = None,
) -> None:
    if progress_file is None:
        return
    payload: dict[str, object] = {
        "status": "running",
        "percent": max(0, min(100, int(percent))),
        "stage": stage,
        "message": message,
        "updated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
    }
    if details:
        payload["details"] = details
    progress_file.parent.mkdir(parents=True, exist_ok=True)
    progress_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


@dataclass
class CePhase06Outputs:
    summary: dict[str, object]
    geojson: dict[str, object]
    summary_file: Path
    geojson_file: Path


def run_ce_phase06(
    *,
    source_workbook: Path,
    definition_file: Path,
    run_dir: Path,
    selected_model_id: str,
    source_name: str,
    progress_file: Path | None = None,
) -> CePhase06Outputs:
    run_dir.mkdir(parents=True, exist_ok=True)

    phase01_dir = run_dir / "phase01"
    phase02_dir = run_dir / "phase02"
    phase03_dir = run_dir / "phase03"
    phase04_dir = run_dir / "phase04"
    phase05_dir = run_dir / "phase05"
    for directory in (phase01_dir, phase02_dir, phase03_dir, phase04_dir, phase05_dir):
        directory.mkdir(parents=True, exist_ok=True)

    phase01_path = phase01_dir / "phase01_top_germplasm.xlsx"
    phase02_path = phase02_dir / "phase02_top_germplasm.xlsx"
    phase02_log_path = phase02_dir / "phase02_top_germplasm_log.json"
    phase03_path = phase03_dir / "phase03_top_germplasm.xlsx"
    phase03_log_path = phase03_dir / "phase03_top_germplasm_log.json"
    phase04_path = phase04_dir / "phase04_top_germplasm.xlsx"
    phase04_log_path = phase04_dir / "phase04_top_germplasm_log.json"

    write_progress(progress_file, percent=96, stage="Top Germplasm phase01", message="Preparing the original workbook columns needed for Top Germplasm.", details={"phase": "phase06", "step": "phase01"})
    phase01_payload = create_phase1_workbook(source_workbook, definition_file, phase01_path)
    write_progress(progress_file, percent=97, stage="Top Germplasm phase02", message="Validating dates, coordinates, and required fields before downloading CHIRPS/CHIRTS-daily data for Top Germplasm.", details={"phase": "phase06", "step": "phase02"})
    phase02_payload = create_phase02_workbook(phase01_path, definition_file, phase02_path, phase02_log_path)
    def top_germplasm_phase03_progress(percent: int, stage: str, message: str, details: dict[str, object] | None) -> None:
        resolved_details = details or {}
        nasa_processed = int(resolved_details.get("nasa_processed_rows", 0) or 0)
        nasa_total = int(resolved_details.get("nasa_total_rows", 0) or 0)
        soil_processed = int(resolved_details.get("soil_processed_rows", 0) or 0)
        soil_total = int(resolved_details.get("soil_total_rows", 0) or 0)
        normalized_percent = max(0, min(100, int(percent)))

        if nasa_total:
            nasa_percent = round((nasa_processed / nasa_total) * 100)
            write_progress(
                progress_file,
                percent=97 + round((normalized_percent / 100) * 1),
                stage="Top Germplasm climate",
                message=f"Downloading CHIRPS/CHIRTS-daily data for Top Germplasm using the original planting and harvesting dates: {nasa_processed}/{nasa_total} rows processed ({nasa_percent}%).",
                details={"phase": "phase06", "step": "phase03_nasa", **resolved_details},
            )
            return

        if soil_total:
            soil_percent = round((soil_processed / soil_total) * 100) if soil_processed else normalized_percent
            write_progress(
                progress_file,
                percent=98 + round((normalized_percent / 100) * 1),
                stage="Top Germplasm soils",
                message=f"Resolving soil data for Top Germplasm: {soil_processed}/{soil_total} rows processed ({soil_percent}%).",
                details={"phase": "phase06", "step": "phase03_soil", **resolved_details},
            )
            return

        write_progress(
            progress_file,
            percent=97 + round((normalized_percent / 100) * 1),
            stage="Top Germplasm phase03",
            message=f"Top Germplasm phase03 in progress ({normalized_percent}%). Preparing climate and soil enrichment.",
            details={"phase": "phase06", "step": "phase03", **resolved_details},
        )

    phase03_payload = create_phase03_workbook(
        phase02_path,
        definition_file,
        phase03_path,
        phase03_log_path,
        progress_file=None,
        skip_soil_enrichment=False,
        climate_override=None,
        progress_callback=top_germplasm_phase03_progress,
    )
    write_progress(progress_file, percent=98, stage="Top Germplasm phase04", message="Normalizing numeric variables and encoding categorical variables for Top Germplasm.", details={"phase": "phase06", "step": "phase04"})
    phase04_payload = create_phase04_workbook(
        phase03_path,
        definition_file,
        phase04_path,
        phase04_log_path,
        allow_missing_target=True,
        progress_callback=None,
    )

    definition = json.loads(definition_file.read_text(encoding="utf-8"))
    initial_settings = definition.get("initial_settings", {}) if isinstance(definition, dict) else {}
    divisions = definition.get("divisions", {}) if isinstance(definition, dict) else {}
    target_column = str(initial_settings.get("target_column", "")).strip()
    workspace_name = str(definition.get("workspace_name", "")).strip() or selected_model_id
    identifier_columns = [
        str(value).strip()
        for value in (divisions.get("germplams_identifiers", []) if isinstance(divisions, dict) else [])
        if str(value).strip()
    ]
    phase04_training_csv = phase04_dir / "phase04_top_germplasm_training_input.csv"

    def top_germplasm_phase05_progress(percent: int, stage: str, message: str, details: dict[str, object] | None) -> None:
        write_progress(
            progress_file,
            percent=99,
            stage="Top Germplasm prediction",
            message="Running the saved model prediction for Top Germplasm.",
            details={"phase": "phase06", "step": "phase05", **((details or {}))},
        )

    phase05_outputs = run_ce_phase05(
        phase04_workbook=phase04_path,
        training_input_csv=phase04_training_csv,
        run_dir=phase05_dir,
        source_name=source_name,
        target_column=target_column,
        selected_model_id=selected_model_id,
        progress_file=None,
        progress_callback=top_germplasm_phase05_progress,
    )

    prediction_xlsx = Path(str(phase05_outputs.summary.get("prediction_xlsx", "")).strip())
    if not prediction_xlsx.exists():
        raise FileNotFoundError(f"The phase06 prediction workbook was not created: {prediction_xlsx}")

    prediction_df = pd.read_excel(prediction_xlsx, dtype=object)
    prediction_df.columns = [str(column).strip() for column in prediction_df.columns]
    if PREDICTED_COLUMN not in prediction_df.columns:
        raise KeyError(f"Missing predicted column in phase06 prediction output: {PREDICTED_COLUMN}")

    write_progress(progress_file, percent=99, stage="Top Germplasm ranking", message="Calculating the Top 10 germplasms with the highest prediction.", details={"phase": "phase06", "step": "ranking"})
    ranked_df = prediction_df.copy()
    ranked_df[PREDICTED_COLUMN] = pd.to_numeric(ranked_df[PREDICTED_COLUMN], errors="coerce")
    ranked_df = ranked_df.dropna(subset=[PREDICTED_COLUMN]).reset_index(drop=True)
    ranked_df = ranked_df.sort_values(by=PREDICTED_COLUMN, ascending=False, kind="mergesort").reset_index(drop=True)

    top_prediction_mean = float(ranked_df[PREDICTED_COLUMN].head(10).mean()) if not ranked_df.empty else None
    target_predicted_column = f"{target_column} predicted" if target_column else PREDICTED_COLUMN
    target_prediction_mean_column = f"{target_column} prediction mean" if target_column else "Target prediction mean"

    full_download_df = ranked_df.copy()
    if target_predicted_column not in full_download_df.columns:
        insert_at = full_download_df.columns.get_loc(target_column) + 1 if target_column in full_download_df.columns else len(full_download_df.columns)
        full_download_df.insert(insert_at, target_predicted_column, full_download_df[PREDICTED_COLUMN])
    else:
        full_download_df[target_predicted_column] = full_download_df[PREDICTED_COLUMN]
    mean_insert_at = full_download_df.columns.get_loc(target_predicted_column) + 1 if target_predicted_column in full_download_df.columns else len(full_download_df.columns)
    if target_prediction_mean_column not in full_download_df.columns:
        full_download_df.insert(mean_insert_at, target_prediction_mean_column, top_prediction_mean)
    else:
        full_download_df[target_prediction_mean_column] = top_prediction_mean

    top_map_df = full_download_df.head(10).reset_index(drop=True)
    file_date = datetime.now().strftime("%Y-%m-%d")
    file_prefix = f"{slugify_workspace_name(workspace_name)}_top_germplams_{file_date}"
    top_csv = run_dir / f"{file_prefix}.csv"
    top_xlsx = run_dir / f"{file_prefix}.xlsx"
    top_geojson_file = run_dir / "top_germplasm.geojson"
    full_download_df.to_csv(top_csv, index=False)
    full_download_df.to_excel(top_xlsx, index=False)
    top_geojson = dataframe_to_geojson(top_map_df, top_geojson_file)

    preview_rows: list[dict[str, object]] = []
    for _, row in top_map_df.iterrows():
        preview_record = {column: row.get(column, "") for column in identifier_columns if column in top_map_df.columns}
        if target_column and target_column in top_map_df.columns:
            preview_record[target_column] = row.get(target_column, "")
        preview_record[target_predicted_column] = row.get(target_predicted_column, row.get(PREDICTED_COLUMN, ""))
        preview_record[target_prediction_mean_column] = top_prediction_mean
        preview_rows.append(preview_record)

    summary = {
        "workflow": "ce_top_germplasm",
        "source_name": source_name,
        "workspace_name": workspace_name,
        "source_workbook": str(source_workbook),
        "selected_model_id": selected_model_id,
        "target_column": target_column,
        "phase01_xlsx": str(phase01_path),
        "phase02_xlsx": str(phase02_path),
        "phase03_xlsx": str(phase03_path),
        "phase04_xlsx": str(phase04_path),
        "phase04_training_csv": str(phase04_training_csv),
        "prediction_xlsx": str(prediction_xlsx),
        "top_germplasm_csv": str(top_csv),
        "top_germplasm_xlsx": str(top_xlsx),
        "geojson_file": str(top_geojson_file),
        "top_count": int(top_map_df.shape[0]),
        "prediction_row_count": int(full_download_df.shape[0]),
        "identifier_columns": identifier_columns,
        "target_predicted_column": target_predicted_column,
        "target_prediction_mean_column": target_prediction_mean_column,
        "target_prediction_mean_value": top_prediction_mean,
        "top_preview_rows": preview_rows,
        "prediction_model_id": phase05_outputs.summary.get("prediction_model_id", ""),
        "prediction_model_name": phase05_outputs.summary.get("prediction_model_name", ""),
        "prediction_model_display_name": phase05_outputs.summary.get("prediction_model_display_name", ""),
        "prediction_model_metric_name": phase05_outputs.summary.get("prediction_model_metric_name", ""),
        "prediction_model_metric_value": phase05_outputs.summary.get("prediction_model_metric_value"),
        "download_url": "",
        "download_file_name": top_xlsx.name,
        "task_report": [
            {"phase": "phase01", "title": "Building phase01 top germplasm workbook", "output_file": str(phase01_path)},
            {"phase": "phase02", "title": "Building phase02 top germplasm workbook", "output_file": str(phase02_path)},
            {"phase": "phase03", "title": "Building phase03 top germplasm workbook", "output_file": str(phase03_path)},
            {"phase": "phase04", "title": "Building phase04 top germplasm workbook", "output_file": str(phase04_path)},
            {"phase": "phase05", "title": "Running saved model prediction", "output_file": str(prediction_xlsx)},
            {"phase": "phase06", "title": "Selecting Top Germplasm rows for the map and building the full germplasm download", "output_file": str(top_xlsx)},
        ],
        "phase02_log": phase02_payload,
        "phase03_log": phase03_payload,
        "phase04_log": phase04_payload,
    }
    write_progress(progress_file, percent=100, stage="Top Germplasm complete", message="Top Germplasm finished. The map and downloadable file are ready.", details={"phase": "phase06", "step": "complete", "top_count": int(ranked_df.shape[0])})
    summary_file = run_dir / "summary.json"
    summary_file.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return CePhase06Outputs(
        summary=summary,
        geojson=top_geojson,
        summary_file=summary_file,
        geojson_file=top_geojson_file,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build the Top Germplasm dataset using the saved model and the original workbook.")
    parser.add_argument("--source-workbook", required=True, help="Path to the uploaded original workbook.")
    parser.add_argument("--definition-file", required=True, help="Path to the selection summary JSON definition.")
    parser.add_argument("--run-dir", required=True, help="Directory where the phase06 artifacts will be created.")
    parser.add_argument("--selected-model-id", required=True, help="Saved model id to reuse for inference.")
    parser.add_argument("--source-name", default="source.xlsx", help="Original workbook name for metadata.")
    parser.add_argument("--progress-file", default="", help="Optional JSON progress file updated while phase06 runs.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    outputs = run_ce_phase06(
        source_workbook=Path(args.source_workbook).expanduser().resolve(),
        definition_file=Path(args.definition_file).expanduser().resolve(),
        run_dir=Path(args.run_dir).expanduser().resolve(),
        selected_model_id=str(args.selected_model_id or "").strip(),
        source_name=str(args.source_name or "source.xlsx").strip(),
        progress_file=Path(args.progress_file).expanduser().resolve() if str(args.progress_file).strip() else None,
    )
    print(
        json.dumps(
            {
                "summary_file": str(outputs.summary_file),
                "geojson_file": str(outputs.geojson_file),
                "summary": outputs.summary,
                "geojson": outputs.geojson,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
