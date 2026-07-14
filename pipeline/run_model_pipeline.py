from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pandas as pd

from pipeline.common import dataframe_to_geojson
from pipeline.model.grain_yield_model import run_grain_yield_prediction
from pipeline.phase_analysis import run_phase_analysis
from pipeline.phase2 import run_phase2
from pipeline.phase3 import run_phase3
from pipeline.phase4 import run_phase4
from pipeline.phase5 import run_phase5


ProgressCallback = Callable[[int, str, str], None]
PREDICTED_COLUMN = "Grain Yield predicted"


@dataclass
class ModelPipelineOutputs:
    summary: dict[str, object]
    summary_file: Path
    geojson: dict[str, object]
    geojson_file: Path


def combine_geo_and_prediction_dataframes(geo_df, prediction_df):
    geo_ready = geo_df.reset_index(drop=True)
    prediction_ready = prediction_df.reset_index(drop=True)
    overlapping_columns = [
        column for column in prediction_ready.columns if column in geo_ready.columns
    ]
    if overlapping_columns:
        prediction_ready = prediction_ready.drop(columns=overlapping_columns, errors="ignore")
    return geo_ready.join(prediction_ready)


def coerce_numeric_like_columns(df: pd.DataFrame) -> pd.DataFrame:
    normalized = df.copy()
    for column in normalized.columns:
        series = normalized[column]
        if not pd.api.types.is_object_dtype(series) and not pd.api.types.is_string_dtype(series):
            continue
        non_empty_mask = series.notna() & series.astype(str).str.strip().ne("")
        if not non_empty_mask.any():
            continue
        parsed = pd.to_numeric(series.where(non_empty_mask), errors="coerce")
        if parsed[non_empty_mask].notna().all():
            normalized[column] = parsed
    return normalized


def normalize_prediction_output_values(df: pd.DataFrame) -> pd.DataFrame:
    normalized = coerce_numeric_like_columns(df)
    if PREDICTED_COLUMN in normalized.columns:
        predicted_series = pd.to_numeric(normalized[PREDICTED_COLUMN], errors="coerce")
        normalized[PREDICTED_COLUMN] = predicted_series.round(6).where(predicted_series.notna(), normalized[PREDICTED_COLUMN])
    return normalized


def write_combined_prediction_outputs(prediction_with_geo, model_dir: Path) -> tuple[Path, Path]:
    combined_csv = model_dir / "prediction_with_context.csv"
    combined_xlsx = model_dir / "prediction_with_context.xlsx"
    normalized_prediction = normalize_prediction_output_values(prediction_with_geo)
    normalized_prediction.to_csv(combined_csv, index=False)
    normalized_prediction.to_excel(combined_xlsx, index=False)
    return combined_csv, combined_xlsx


def run_model_pipeline(
    phase06_xlsx: Path,
    run_dir: Path,
    progress_callback: ProgressCallback | None = None,
    selected_model_id: str | None = None,
) -> ModelPipelineOutputs:
    run_dir.mkdir(parents=True, exist_ok=True)

    if progress_callback:
        progress_callback(
            56,
            "Filtering records",
            "Checking dates, yield values, and keeping geoinformation columns available for mapping.",
        )
    phase2 = run_phase2(
        phase06_xlsx,
        run_dir / "phase2",
        allow_zero_grain_yield=bool(selected_model_id),
    )
    if progress_callback:
        progress_callback(
            64,
            "Normalizing fields",
            "Cleaning date formats, harmonizing categories, and preparing the analytical table.",
        )
    phase3 = run_phase3(phase2.csv_file, run_dir / "phase3")
    if progress_callback:
        progress_callback(
            72,
            "Engineering features",
            "Applying derived transformations for land area and agronomic consistency checks.",
        )
        progress_callback(
            80,
            "Encoding categories",
            "Transforming categorical values into model-ready columns while preserving map context.",
        )
    phase4 = run_phase4(phase3.csv_file, run_dir / "phase4")
    if progress_callback:
        progress_callback(
            86,
            "Standardizing metrics",
            "Scaling climate and agronomic variables before generating the final geospatial dataset.",
        )
    phase5 = run_phase5(phase4.csv_file, run_dir / "phase5")
    phase_analysis = None
    if not selected_model_id:
        if progress_callback:
            progress_callback(
                90,
                "Running model analysis",
                "Launching FeatureHero to analyze Grain Yield, select features, and save the best model artifacts.",
            )
        phase_analysis = run_phase_analysis(
            phase5.dataframe,
            run_dir / "phase_analysis",
            phase5.csv_file,
            progress_callback=progress_callback,
        )
    if progress_callback:
        progress_callback(
            94,
            "Running model prediction",
            (
                "Loading the selected saved Grain Yield model and generating predictions."
                if selected_model_id
                else "Loading the newly saved Grain Yield model and generating predictions."
            ),
        )
    prediction = run_grain_yield_prediction(
        phase5.csv_file,
        run_dir / "model",
        selected_model_id=selected_model_id,
    )

    if progress_callback:
        progress_callback(
            97,
            "Preparing map output",
            "Building the final geospatial dataset and validating the processed Geocoordinates.",
        )
    geojson_file = run_dir / "model" / "phase5_with_predictions.geojson"
    prediction_with_geo = combine_geo_and_prediction_dataframes(
        phase5.geo_dataframe,
        prediction.dataframe,
    )
    prediction_with_geo = normalize_prediction_output_values(prediction_with_geo)
    combined_prediction_csv, combined_prediction_xlsx = write_combined_prediction_outputs(
        prediction_with_geo,
        run_dir / "model",
    )
    geojson = dataframe_to_geojson(prediction_with_geo, geojson_file)

    summary = {
        "phase06_xlsx": str(phase06_xlsx),
        "phase2_csv": str(phase2.csv_file),
        "phase3_csv": str(phase3.csv_file),
        "phase4_csv": str(phase4.csv_file),
        "phase5_csv": str(phase5.csv_file),
        "phase_analysis_dir": str(run_dir / "phase_analysis"),
        "phase_analysis_model_id": phase_analysis.model_id if phase_analysis else "",
        "phase_analysis_model_dir": str(phase_analysis.model_dir) if phase_analysis else "",
        "phase_analysis_created_at": (
            phase_analysis.metadata.get("created_at", "") if phase_analysis else ""
        ),
        "phase_analysis_description": (
            phase_analysis.description
            if phase_analysis
            else f"Skipped FeatureHero because saved model {prediction.model_metadata.get('model_id', '')} was selected."
        ),
        "phase_analysis_skipped": phase_analysis is None,
        "phase_analysis_metric_name": (
            phase_analysis.metadata.get("metric_name", "") if phase_analysis else ""
        ),
        "phase_analysis_metric_value": (
            phase_analysis.metadata.get("metric_value") if phase_analysis else None
        ),
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
        "geojson_file": str(geojson_file),
        "total_features": geojson["metadata"]["total_features"],
        "task_report": [
            {"phase": "phase2", "title": "Filtering records", "output_file": str(phase2.xlsx_file)},
            {"phase": "phase3", "title": "Normalizing fields", "output_file": str(phase3.xlsx_file)},
            {"phase": "phase4", "title": "Encoding categories", "output_file": str(phase4.xlsx_file)},
            {"phase": "phase5", "title": "Standardizing metrics", "output_file": str(phase5.xlsx_file)},
            *(
                [
                    {
                        "phase": "phase_analysis",
                        "title": "Running FeatureHero model analysis",
                        "output_file": str((run_dir / "phase_analysis") / "summary.json"),
                    }
                ]
                if phase_analysis
                else []
            ),
            {
                "phase": "model",
                "title": f"Running {prediction.model_name} prediction",
                "output_file": str(prediction.output_xlsx),
            },
        ],
    }
    summary_file = run_dir / "summary.json"
    summary_file.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return ModelPipelineOutputs(
        summary=summary,
        summary_file=summary_file,
        geojson=geojson,
        geojson_file=geojson_file,
    )
