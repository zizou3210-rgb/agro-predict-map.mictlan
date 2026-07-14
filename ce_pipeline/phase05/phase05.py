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
from pathlib import Path
from typing import Callable

import pandas as pd

from ce_pipeline.phase04.phase04 import CANONICAL_TARGET_COLUMN
from pipeline.common import GEO_COLUMNS, GERMPLASM_COLUMNS, dataframe_to_geojson
from pipeline.model.grain_yield_model import run_grain_yield_prediction
from pipeline.run_model_pipeline import (
    combine_geo_and_prediction_dataframes,
    normalize_prediction_output_values,
    write_combined_prediction_outputs,
)
from workbook_preview import _derive_country_from_coordinates, _parse_coordinate
from workbook_preview import (
    PREDICTION_GROUP_KEY_HEADER,
    PREDICTION_GROUP_LABEL_HEADER,
    PREDICTION_GROUP_REP_HEADER,
    PREDICTION_INTERNAL_ROW_ID_HEADER,
)


ProgressCallback = Callable[[int, str, str, dict[str, object] | None], None]


@dataclass
class CePhase05Outputs:
    summary: dict[str, object]
    geojson: dict[str, object]
    summary_file: Path
    geojson_file: Path


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


def ensure_country_column(df: pd.DataFrame) -> pd.DataFrame:
    if "Country" not in df.columns:
        df["Country"] = ""
    country_series = df["Country"].astype(str).str.strip()
    missing_mask = country_series.eq("")
    if not missing_mask.any():
        return df
    latitudes = df.get("_GPS coordinates_latitude")
    longitudes = df.get("_GPS coordinates_longitude")
    if latitudes is None or longitudes is None:
        return df
    for index in df.index[missing_mask]:
        latitude = _parse_coordinate(df.at[index, "_GPS coordinates_latitude"])
        longitude = _parse_coordinate(df.at[index, "_GPS coordinates_longitude"])
        if latitude is None or longitude is None:
            continue
        derived_country = _derive_country_from_coordinates(longitude, latitude)
        if derived_country:
            df.at[index, "Country"] = derived_country
    return df


def run_ce_phase05(
    phase04_workbook: Path,
    training_input_csv: Path,
    run_dir: Path,
    *,
    source_name: str,
    target_column: str,
    selected_id_header: str = "",
    selected_model_id: str | None = None,
    progress_file: Path | None = None,
    progress_callback: ProgressCallback | None = None,
) -> CePhase05Outputs:
    run_dir.mkdir(parents=True, exist_ok=True)

    phase04_df = pd.read_excel(phase04_workbook, dtype=object)
    phase04_df.columns = [str(column).strip() for column in phase04_df.columns]
    phase04_df = ensure_country_column(phase04_df)
    if CANONICAL_TARGET_COLUMN not in phase04_df.columns:
        raise KeyError(f"Missing canonical target column in phase04 workbook: {CANONICAL_TARGET_COLUMN}")

    if progress_callback:
        progress_callback(
            90,
            "Preparing saved model prediction",
            "Loading phase04prediction.xlsx and the selected Grain Yield model for inference.",
            {"phase": "phase05", "input_rows": len(phase04_df.index)},
        )

    write_progress(
        progress_file,
        percent=96,
        stage="Running ce_pipeline phase05 prediction",
        message="Using the ce_pipeline training input to generate the prediction dataset and map output.",
        details={"phase": "phase05", "target_column": target_column, "selected_model_id": selected_model_id or ""},
    )
    if progress_callback:
        progress_callback(
            96,
            "Running saved model prediction",
            "Executing the selected Grain Yield model with the normalized prediction input.",
            {"phase": "phase05", "target_column": target_column, "selected_model_id": selected_model_id or ""},
        )

    prediction = run_grain_yield_prediction(
        training_input_csv,
        run_dir / "model",
        selected_model_id=selected_model_id,
    )

    selected_id_header = str(selected_id_header or "").strip()
    preserved_geo_columns = [column for column in GEO_COLUMNS if column in phase04_df.columns]
    preserved_germplasm_columns = [column for column in GERMPLASM_COLUMNS if column in phase04_df.columns]
    preserved_selected_id_columns = [
        column
        for column in [selected_id_header]
        if column and column in phase04_df.columns and column not in preserved_geo_columns and column not in preserved_germplasm_columns
    ]
    target_and_metadata_columns = [
        column
        for column in phase04_df.columns
        if column
        in {
            CANONICAL_TARGET_COLUMN,
            target_column,
            "Country",
            "Date of planting",
            "Date_of_harvesting",
            "Soil type/texture",
            "Soil Depth (cm)-How deep do you expect maize roots to grow in this soil?",
            "Prediction Profile Key",
            "Prediction Profile",
            "Prediction Profile Columns",
            "Prediction Target Mean Threshold",
            "Prediction Profile Target Mean",
            PREDICTION_INTERNAL_ROW_ID_HEADER,
            PREDICTION_GROUP_KEY_HEADER,
            PREDICTION_GROUP_LABEL_HEADER,
            PREDICTION_GROUP_REP_HEADER,
        }
        and column not in preserved_geo_columns
        and column not in preserved_germplasm_columns
        and column not in preserved_selected_id_columns
    ]
    geo_df = phase04_df[
        [
            *preserved_geo_columns,
            *preserved_germplasm_columns,
            *preserved_selected_id_columns,
            *target_and_metadata_columns,
        ]
    ].copy()

    if progress_callback:
        progress_callback(
            98,
            "Merging prediction results",
            "Joining the model predictions with geospatial and germplasm traceability columns.",
            {"phase": "phase05"},
        )
    prediction_with_geo = combine_geo_and_prediction_dataframes(geo_df, prediction.dataframe)
    prediction_with_geo = normalize_prediction_output_values(prediction_with_geo)
    combined_prediction_csv, combined_prediction_xlsx = write_combined_prediction_outputs(
        prediction_with_geo,
        run_dir / "model",
    )
    geojson_file = run_dir / "model" / "ce_phase05_with_predictions.geojson"
    geojson = dataframe_to_geojson(prediction_with_geo, geojson_file)

    write_progress(
        progress_file,
        percent=99,
        stage="Preparing ce_pipeline prediction map output",
        message="Building the ce_pipeline Prediction geojson with countries and predicted values.",
        details={"phase": "phase05", "target_column": target_column, "selected_model_id": selected_model_id or ""},
    )
    if progress_callback:
        progress_callback(
            99,
            "Preparing map output",
            "Building the colored prediction map dataset and final GeoJSON output.",
            {"phase": "phase05", "target_column": target_column, "selected_model_id": selected_model_id or ""},
        )

    summary = {
        "workflow": "ce_pipeline_prediction",
        "source_name": source_name,
        "target_column": target_column,
        "canonical_target_column": CANONICAL_TARGET_COLUMN,
        "phase04_xlsx": str(phase04_workbook),
        "phase04_training_csv": str(training_input_csv),
        "phase04_training_xlsx": str(training_input_csv.with_suffix(".xlsx")),
        "model_input_csv": str(prediction.model_input_csv),
        "prediction_csv": str(combined_prediction_csv),
        "prediction_xlsx": str(combined_prediction_xlsx),
        "prediction_model_raw_csv": str(prediction.output_csv),
        "prediction_model_raw_xlsx": str(prediction.output_xlsx),
        "prediction_model_name": prediction.model_name,
        "prediction_feature_count": len(prediction.feature_names),
        "prediction_model_id": prediction.model_metadata.get("model_id", ""),
        "prediction_model_created_at": prediction.model_metadata.get("created_at", ""),
        "prediction_model_display_name": prediction.model_metadata.get("display_name", ""),
        "prediction_model_description": prediction.model_metadata.get("description", ""),
        "prediction_model_metric_name": prediction.model_metadata.get("metric_name", ""),
        "prediction_model_metric_value": prediction.model_metadata.get("metric_value"),
        "selected_model_id": selected_model_id or "",
        "selected_id_header": selected_id_header,
        "geojson_file": str(geojson_file),
        "total_features": geojson["metadata"]["total_features"],
        "task_report": [
            {
                "phase": "phase05",
                "title": f"Running {prediction.model_name} prediction",
                "output_file": str(prediction.output_xlsx),
            }
        ],
    }
    summary_file = run_dir / "summary.json"
    summary_file.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return CePhase05Outputs(summary=summary, geojson=geojson, summary_file=summary_file, geojson_file=geojson_file)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run ce_pipeline phase05 prediction using the phase04 training dataset.")
    parser.add_argument("--phase04-workbook", required=True, help="Path to the generated phase04 workbook.")
    parser.add_argument("--training-input-csv", required=True, help="Path to the generated phase04 training CSV.")
    parser.add_argument("--run-dir", required=True, help="Directory where phase05 artifacts will be created.")
    parser.add_argument("--source-name", default="phase04.xlsx", help="Source workbook name for metadata.")
    parser.add_argument("--target-column", required=True, help="Original target column selected in Initial Settings.")
    parser.add_argument("--selected-id-header", default="", help="Optional workbook column selected as the germplasm Id.")
    parser.add_argument("--selected-model-id", default="", help="Optional saved model id to reuse for prediction.")
    parser.add_argument("--progress-file", default="", help="Optional JSON progress file updated while phase05 runs.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    progress_file = Path(args.progress_file).expanduser().resolve() if str(args.progress_file).strip() else None
    outputs = run_ce_phase05(
        phase04_workbook=Path(args.phase04_workbook).expanduser().resolve(),
        training_input_csv=Path(args.training_input_csv).expanduser().resolve(),
        run_dir=Path(args.run_dir).expanduser().resolve(),
        source_name=str(args.source_name or "phase04.xlsx"),
        target_column=str(args.target_column or "").strip(),
        selected_id_header=str(args.selected_id_header or "").strip(),
        selected_model_id=str(args.selected_model_id or "").strip() or None,
        progress_file=progress_file,
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
