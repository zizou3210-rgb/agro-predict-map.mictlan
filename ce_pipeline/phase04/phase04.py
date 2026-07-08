#!/usr/bin/env python3
from __future__ import annotations

if __package__ in {None, ""}:
    import sys
    from pathlib import Path

    APP_BOOT_DIR = Path(__file__).resolve().parents[2]
    PACKAGE_PARENT = APP_BOOT_DIR.parent
    if str(PACKAGE_PARENT) not in sys.path:
        sys.path.insert(0, str(PACKAGE_PARENT))

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Callable

import pandas as pd

from cimmyt_app.pipeline.phase3 import build_final_df
from cimmyt_app.pipeline.phase4 import normalize_dummy_source_value
from cimmyt_app.pipeline.phase5 import apply_log_transform, clean_numeric_series, should_apply_log
from cimmyt_app.preprocess.ea_pipeline import CLIMATE_HEADERS_WITH_UNITS

PHASE01_SCRIPT = Path(__file__).resolve().parents[1] / "phase01" / "phase1.py"
CANONICAL_TARGET_COLUMN = "Grain Yield (T/Ha)"
CANONICAL_LATITUDE_COLUMN = "_GPS coordinates_latitude"
CANONICAL_LONGITUDE_COLUMN = "_GPS coordinates_longitude"
CANONICAL_PLANTING_COLUMN = "Date of planting"
CANONICAL_HARVESTING_COLUMN = "Date_of_harvesting"
CANONICAL_SOIL_TEXTURE_COLUMN = "Soil type/texture"
CANONICAL_SOIL_DEPTH_COLUMN = "Soil Depth (cm)-How deep do you expect maize roots to grow in this soil?"
ProgressCallback = Callable[[int, str, str, dict[str, object] | None], None]


def load_phase01_module():
    spec = importlib.util.spec_from_file_location("ce_phase01", PHASE01_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"The ce_pipeline phase01 script could not be loaded: {PHASE01_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sort_columns(values: list[str]) -> list[str]:
    return sorted(
        [str(value or "").strip() for value in values if str(value or "").strip()],
        key=lambda value: value.lower(),
    )


def unique_columns(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        column = str(value or "").strip()
        if not column or column in seen:
            continue
        seen.add(column)
        ordered.append(column)
    return ordered


def build_traceability_columns(definition: dict[str, object]) -> list[str]:
    initial_settings = definition.get("initial_settings", {}) if isinstance(definition, dict) else {}
    divisions = definition.get("divisions", {}) if isinstance(definition, dict) else {}
    columns = [
        str(initial_settings.get("target_column", "")).strip(),
        str(initial_settings.get("longitude_column", "")).strip(),
        str(initial_settings.get("latitude_column", "")).strip(),
        str(initial_settings.get("planting_date_column", "")).strip(),
        str(initial_settings.get("harvesting_date_column", "")).strip(),
        str(initial_settings.get("soil_texture_column", "")).strip(),
        str(initial_settings.get("soil_depth_column", "")).strip(),
        CANONICAL_TARGET_COLUMN,
        CANONICAL_LATITUDE_COLUMN,
        CANONICAL_LONGITUDE_COLUMN,
        CANONICAL_PLANTING_COLUMN,
        CANONICAL_HARVESTING_COLUMN,
        CANONICAL_SOIL_TEXTURE_COLUMN,
        CANONICAL_SOIL_DEPTH_COLUMN,
    ]
    columns.extend(divisions.get("germplams_identifiers", []) if isinstance(divisions.get("germplams_identifiers"), list) else [])
    return unique_columns(columns)


def _sanitize_float(value: object) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(numeric):
        return None
    return numeric


def _normalize_saved_normalization_stats(
    saved_stats: dict[str, object] | None,
) -> dict[str, dict[str, object]]:
    normalized: dict[str, dict[str, object]] = {}
    if not isinstance(saved_stats, dict):
        return normalized
    for raw_column, raw_payload in saved_stats.items():
        column = str(raw_column or "").strip()
        if not column or not isinstance(raw_payload, dict):
            continue
        normalized[column] = {
            "apply_log": bool(raw_payload.get("apply_log", False)),
            "mean": _sanitize_float(raw_payload.get("mean")),
            "std": _sanitize_float(raw_payload.get("std")),
            "zero_std_fallback": bool(raw_payload.get("zero_std_fallback", False)),
        }
    return normalized


def create_phase04_workbook(
    phase03_workbook: Path,
    definition_file: Path,
    output_file: Path,
    log_file: Path,
    *,
    allow_missing_target: bool = False,
    stream_traceability_workbook: bool = False,
    progress_callback: ProgressCallback | None = None,
    normalization_stats_file: Path | None = None,
    normalization_overrides: dict[str, object] | None = None,
) -> dict[str, object]:
    phase01 = load_phase01_module()
    definition = phase01.read_definition(definition_file)
    initial_settings = definition.get("initial_settings", {})
    divisions = definition.get("divisions", {})

    headers, records = phase01.read_sheet_headers_and_rows(phase03_workbook)
    if not headers:
        raise ValueError("The phase03 workbook is empty.")

    df = pd.DataFrame(records)
    df.columns = [str(column).strip() for column in df.columns]

    if progress_callback:
        progress_callback(
            72,
            "Preparing phase04prediction",
            "Loading the climate and soil enriched workbook and validating the selected feature columns.",
            {"phase": "phase04", "input_rows": len(df.index), "input_columns": len(df.columns)},
        )

    target_column = str(initial_settings.get("target_column", "")).strip()
    if not target_column:
        raise ValueError("The selection definition must include a target column.")
    if target_column not in df.columns:
        if allow_missing_target:
            df[target_column] = ""
        else:
            raise KeyError(f"The phase03 workbook does not contain the selected target column: {target_column}")

    if CANONICAL_TARGET_COLUMN not in df.columns:
        df[CANONICAL_TARGET_COLUMN] = df[target_column] if target_column in df.columns else ""

    categorical_columns = sort_columns(divisions.get("categorical_data", []) if isinstance(divisions.get("categorical_data"), list) else [])
    quantitative_columns = sort_columns(divisions.get("cuantitative_data", []) if isinstance(divisions.get("cuantitative_data"), list) else [])
    identifier_columns = sort_columns(divisions.get("germplams_identifiers", []) if isinstance(divisions.get("germplams_identifiers"), list) else [])
    dg_columns = sort_columns(divisions.get("DG", []) if isinstance(divisions.get("DG"), list) else [])

    missing_categorical = [column for column in categorical_columns if column not in df.columns]
    missing_quantitative = [column for column in quantitative_columns if column not in df.columns]
    missing_dg = [column for column in dg_columns if column not in df.columns]
    if missing_categorical:
        raise KeyError("Missing categorical columns in phase03 workbook:\n- " + "\n- ".join(missing_categorical))
    if missing_quantitative:
        raise KeyError("Missing quantitative columns in phase03 workbook:\n- " + "\n- ".join(missing_quantitative))
    if missing_dg:
        raise KeyError("Missing DG columns in phase03 workbook:\n- " + "\n- ".join(missing_dg))

    traceability_columns = [column for column in build_traceability_columns(definition) if column in df.columns]
    initial_settings_columns_to_drop = unique_columns([
        str(initial_settings.get("longitude_column", "")).strip(),
        str(initial_settings.get("latitude_column", "")).strip(),
        str(initial_settings.get("planting_date_column", "")).strip(),
        str(initial_settings.get("harvesting_date_column", "")).strip(),
        CANONICAL_LATITUDE_COLUMN,
        CANONICAL_LONGITUDE_COLUMN,
        CANONICAL_PLANTING_COLUMN,
        CANONICAL_HARVESTING_COLUMN,
    ])

    if progress_callback:
        progress_callback(
            76,
            "Normalizing fields",
            "Cleaning numeric and categorical source values before model preparation.",
            {"phase": "phase04"},
        )
    normalized_training_df = build_final_df(df.copy())
    standardized_training_df = normalized_training_df.copy()

    backfilled_dg_columns: list[str] = []
    for column in dg_columns:
        if column not in standardized_training_df.columns and column in df.columns:
            standardized_training_df[column] = df[column]
            backfilled_dg_columns.append(column)

    soil_categorical_columns = [
        CANONICAL_SOIL_TEXTURE_COLUMN,
        CANONICAL_SOIL_DEPTH_COLUMN,
    ]
    effective_categorical_columns = unique_columns([
        *categorical_columns,
        *soil_categorical_columns,
    ])
    backfilled_categorical_columns: list[str] = []
    for column in effective_categorical_columns:
        if column not in standardized_training_df.columns and column in df.columns:
            standardized_training_df[column] = df[column]
            backfilled_categorical_columns.append(column)
    missing_effective_categorical = [
        column for column in effective_categorical_columns if column not in standardized_training_df.columns
    ]
    if missing_effective_categorical:
        raise KeyError("Missing categorical columns after categorical normalization:\n- " + "\n- ".join(missing_effective_categorical))

    quantitative_and_nasa_columns = unique_columns([
        *quantitative_columns,
        *[column for column in CLIMATE_HEADERS_WITH_UNITS if column in standardized_training_df.columns],
    ])
    backfilled_numeric_columns: list[str] = []
    for column in quantitative_columns:
        if column not in standardized_training_df.columns and column in df.columns:
            standardized_training_df[column] = df[column]
            backfilled_numeric_columns.append(column)

    missing_standardized = [
        column for column in quantitative_and_nasa_columns if column not in standardized_training_df.columns
    ]
    if missing_standardized:
        raise KeyError("Missing numeric columns for ce_pipeline training preparation:\n- " + "\n- ".join(missing_standardized))

    if progress_callback:
        progress_callback(
            80,
            "Standardizing metrics",
            "Applying log transforms when needed and standardizing the quantitative and climate variables.",
            {"phase": "phase04", "numeric_columns": len(quantitative_and_nasa_columns)},
        )
    quantitative_log_applied: list[str] = []
    standardized_numeric_columns: list[str] = []
    normalized_saved_stats = _normalize_saved_normalization_stats(normalization_overrides)
    normalization_stats: dict[str, dict[str, object]] = {}
    for column in quantitative_and_nasa_columns:
        numeric_series = clean_numeric_series(standardized_training_df[column].copy(), treat_dot_as_missing=True)
        saved_stats = normalized_saved_stats.get(column)
        apply_log = bool(saved_stats.get("apply_log")) if saved_stats is not None else should_apply_log(numeric_series)
        if apply_log:
            numeric_series = apply_log_transform(numeric_series)
            quantitative_log_applied.append(column)
        mean = (
            saved_stats.get("mean")
            if saved_stats is not None and saved_stats.get("mean") is not None
            else float(numeric_series.mean(skipna=True))
        )
        std = (
            saved_stats.get("std")
            if saved_stats is not None and saved_stats.get("std") is not None
            else float(numeric_series.std(skipna=True, ddof=1))
        )
        zero_std_fallback = bool(pd.isna(std) or std == 0)
        if pd.isna(std) or std == 0:
            standardized_series = numeric_series.where(numeric_series.isna(), 0.0)
        else:
            standardized_series = (numeric_series - mean) / std
        standardized_training_df[column] = standardized_series
        standardized_numeric_columns.append(column)
        normalization_stats[column] = {
            "apply_log": apply_log,
            "mean": None if pd.isna(mean) else float(mean),
            "std": None if pd.isna(std) else float(std),
            "zero_std_fallback": zero_std_fallback,
        }

    if progress_callback:
        progress_callback(
            84,
            "Encoding categories",
            "Building dummy variables for the categorical predictors selected in the saved model definition.",
            {
                "phase": "phase04",
                "categorical_columns": len(effective_categorical_columns),
                "backfilled_categorical_columns": backfilled_categorical_columns,
            },
        )
    dummy_frames: list[pd.DataFrame] = []
    generated_dummy_columns: list[str] = []
    for column in effective_categorical_columns:
        normalized = standardized_training_df[column].apply(normalize_dummy_source_value)
        dummies = pd.get_dummies(normalized, prefix=column, dtype="Int64")
        if not dummies.empty:
            dummies.columns = [str(name) for name in dummies.columns]
            missing_mask = normalized.isna()
            if missing_mask.any():
                dummies.loc[missing_mask, :] = pd.NA
            dummy_frames.append(dummies)
            generated_dummy_columns.extend([str(name) for name in dummies.columns])

    metadata_columns = [
        column for column in df.columns
        if column not in set(traceability_columns + effective_categorical_columns + quantitative_and_nasa_columns + dg_columns)
    ]

    output_df = pd.concat(
        [
            df[traceability_columns].copy(),
            standardized_training_df[[column for column in quantitative_and_nasa_columns if column in standardized_training_df.columns]].reset_index(drop=True),
            standardized_training_df[[column for column in dg_columns if column in standardized_training_df.columns]].reset_index(drop=True),
            *(frame.reset_index(drop=True) for frame in dummy_frames),
            df[metadata_columns].reset_index(drop=True),
        ],
        axis=1,
    )

    training_ready_df = standardized_training_df.drop(
        columns=[column for column in initial_settings_columns_to_drop if column in standardized_training_df.columns],
        errors="ignore",
    ).copy()
    training_ready_df = training_ready_df.drop(
        columns=[column for column in effective_categorical_columns if column in training_ready_df.columns],
        errors="ignore",
    )
    if progress_callback:
        progress_callback(
            88,
            "Writing phase04prediction",
            "Saving the traceability workbook and the model-ready normalized prediction input files.",
            {"phase": "phase04"},
        )
    if dummy_frames:
        training_ready_df = pd.concat([training_ready_df.reset_index(drop=True), *(frame.reset_index(drop=True) for frame in dummy_frames)], axis=1)

    output_headers = [str(column) for column in output_df.columns]
    serializable_output_df = output_df.astype(object).where(pd.notna(output_df), "")
    if stream_traceability_workbook:
        phase01.write_xlsx_rows(
            output_file,
            output_headers,
            serializable_output_df.itertuples(index=False, name=None),
            int(serializable_output_df.shape[0]),
        )
    else:
        output_records = serializable_output_df.to_dict(orient="records")
        phase01.write_xlsx(output_file, output_headers, output_records)
    stem = output_file.stem
    selected_fields_csv = output_file.parent / f"{stem}_selected_fields.csv"
    output_df.to_csv(selected_fields_csv, index=False)

    training_csv = output_file.parent / f"{stem}_training_input.csv"
    training_xlsx = output_file.parent / f"{stem}_training_input.xlsx"
    training_ready_df.to_csv(training_csv, index=False)
    training_ready_df.to_excel(training_xlsx, index=False)
    resolved_normalization_stats_file = normalization_stats_file or output_file.parent / f"{stem}_normalization_stats.json"
    resolved_normalization_stats_file.parent.mkdir(parents=True, exist_ok=True)
    resolved_normalization_stats_file.write_text(
        json.dumps(normalization_stats, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    log_payload = {
        "phase": "phase04",
        "source_workbook": str(phase03_workbook),
        "output_workbook": str(output_file),
        "selected_fields_csv": str(selected_fields_csv),
        "training_input_csv": str(training_csv),
        "training_input_xlsx": str(training_xlsx),
        "normalization_stats_file": str(resolved_normalization_stats_file),
        "target_column": target_column,
        "canonical_target_column": CANONICAL_TARGET_COLUMN,
        "identifier_columns": identifier_columns,
        "dg_columns": dg_columns,
        "backfilled_dg_columns": backfilled_dg_columns,
        "categorical_columns": categorical_columns,
        "effective_categorical_columns": effective_categorical_columns,
        "quantitative_columns": quantitative_columns,
        "standardized_numeric_columns": standardized_numeric_columns,
        "backfilled_numeric_columns": backfilled_numeric_columns,
        "quantitative_log_applied": quantitative_log_applied,
        "normalization_stats": normalization_stats,
        "normalization_stats_source": "saved_model" if normalized_saved_stats else "workspace_training",
        "generated_dummy_columns": generated_dummy_columns,
        "dummy_column_count": int(sum(frame.shape[1] for frame in dummy_frames)),
        "traceability_columns": traceability_columns,
        "metadata_columns": metadata_columns,
        "dropped_initial_settings_columns_for_training": initial_settings_columns_to_drop,
        "input_row_count": int(df.shape[0]),
        "output_row_count": int(output_df.shape[0]),
        "output_column_count": int(output_df.shape[1]),
        "training_input_column_count": int(training_ready_df.shape[1]),
    }
    log_file.parent.mkdir(parents=True, exist_ok=True)
    log_file.write_text(json.dumps(log_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return log_payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create ce_pipeline phase04 workbook for training.")
    parser.add_argument("--phase03-workbook", required=True, help="Path to the generated phase03 workbook.")
    parser.add_argument("--definition-file", required=True, help="Path to the selection summary JSON definition.")
    parser.add_argument("--output-file", required=True, help="Path to the generated phase04 workbook.")
    parser.add_argument("--log-file", required=True, help="Path to the generated phase04 log JSON file.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    result = create_phase04_workbook(
        phase03_workbook=Path(args.phase03_workbook).expanduser().resolve(),
        definition_file=Path(args.definition_file).expanduser().resolve(),
        output_file=Path(args.output_file).expanduser().resolve(),
        log_file=Path(args.log_file).expanduser().resolve(),
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
