from __future__ import annotations

import json
import os
import pickle
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from pipeline.common import GERMPLASM_COLUMNS
from pipeline.model_registry import get_latest_registered_model, get_registered_model
from pipeline.resource_paths import ROOT_DIR, get_featurehero_python, get_featurehero_repo


RUNTIME_SCRIPT = Path(__file__).resolve().parent / "runtime_predict.py"
MODEL_NAME = "Extreme Gradient Boosting"
PREDICTED_COLUMN = "Grain Yield predicted"
TARGET_COLUMN = "Grain Yield (T/Ha)"
GEO_COLUMNS = [
    "Country",
    "GPS coordinates",
    "_GPS coordinates_latitude",
    "_GPS coordinates_longitude",
    "_GPS coordinates_altitude",
    "_GPS coordinates_precision",
]
FEATURE_NAMES = [
    "harvest_back_week_8_avg_t2m (C)",
    "Weed control practices_Hand",
    "Weed control practices_Chemical",
    "intermediate_period_total_prectotcorr (mm)",
    "harvest_back_week_8_total_prectotcorr (mm)",
    "Education/Training of the farmer_Post-secondary",
    "Stem Logding (%)",
    "Farmers total land area (acres)",
    "harvest_back_week_4_avg_t2m (C)",
    "harvest_back_week_6_avg_t2m (C)",
    "Root Lodging (%)",
    "harvest_back_week_7_total_prectotcorr (mm)",
    "harvest_back_week_1_avg_t2m (C)",
    "planting_week_1_total_prectotcorr (mm)",
    "Percentage_Plant_harvest_stand_t_harvesting_Plot_1",
    "Grey_Leaf_Spot_GLS_5_very_susceptible_header",
    "Age of the plot manager_Below 35 years",
    "Soil type/texture_Sandy Loam",
    "Education/Training of the farmer_Primary",
    "is_fertilizer_1.0",
    "Turcicum_leaf_blight_5_very_susceptible_header",
    "Soil type/texture_Loam",
    "Rotten Ears (%)",
    "Soil type/texture_Silty Loam",
    "Education/Training of the farmer_Partial or completed secondary",
    "Age of the plot manager_Between 35 and 50 years",
    "harvest_back_week_3_total_prectotcorr (mm)",
]


@dataclass
class ResolvedModel:
    model_file: Path
    best_features_file: Path
    sort_original_file: Path
    model_name: str
    metadata: dict[str, object]


@dataclass
class GrainYieldPredictionOutputs:
    dataframe: pd.DataFrame
    source_dataframe: pd.DataFrame
    model_input_csv: Path
    output_csv: Path
    output_xlsx: Path
    model_name: str
    feature_names: list[str]
    model_metadata: dict[str, object]


def read_model_feature_names(model_file: Path) -> list[str]:
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
        str(model_file),
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


def resolve_active_model(selected_model_id: str | None = None) -> ResolvedModel:
    registered_model = None
    if selected_model_id:
        registered_model = get_registered_model(selected_model_id)
        if registered_model is None:
            raise FileNotFoundError(f"The selected Grain Yield model was not found: {selected_model_id}")
    else:
        registered_model = get_latest_registered_model()
    if registered_model is not None:
        metadata = registered_model.metadata
        model_file = Path(str(metadata.get("best_model_file") or ""))
        best_features_file = Path(str(metadata.get("best_features_file") or ""))
        sort_original_file = registered_model.model_dir / "sort_original.csv"
        if not model_file.exists():
            raise FileNotFoundError(f"Missing saved Grain Yield model file: {model_file}")
        if not best_features_file.exists():
            raise FileNotFoundError(f"Missing saved Grain Yield feature selector file: {best_features_file}")
        if not sort_original_file.exists():
            raise FileNotFoundError(f"Missing saved Grain Yield sort_original.csv file: {sort_original_file}")
        return ResolvedModel(
            model_file=model_file,
            best_features_file=best_features_file,
            sort_original_file=sort_original_file,
            model_name=str(metadata.get("machine_name") or MODEL_NAME),
            metadata=metadata,
        )

    legacy_workspace_dir = (
        ROOT_DIR
        / "EA_merged"
        / "phases"
        / "phase_analysis"
        / "Grain_Yield_T_Ha"
        / "work_space_featurehero"
        / "20260408_190836"
    )
    model_file = legacy_workspace_dir / "best_model_sort_original.pkl"
    if not model_file.exists():
        raise FileNotFoundError(
            "No saved Grain Yield model was found in cimmyt_app/pipeline/model and "
            "the legacy EA_merged model is also missing."
        )
    best_features_file = legacy_workspace_dir / "best_features_sort_original.pkl"
    sort_original_file = legacy_workspace_dir / "sort_original.csv"
    return ResolvedModel(
        model_file=model_file,
        best_features_file=best_features_file,
        sort_original_file=sort_original_file,
        model_name=MODEL_NAME,
        metadata={
            "model_id": "legacy-ea-merged",
            "machine_name": MODEL_NAME,
            "description": "Legacy Grain Yield model loaded from EA_merged.",
            "selected_features": FEATURE_NAMES,
            "selected_feature_count": len(FEATURE_NAMES),
            "best_features_file": str(best_features_file),
            "best_model_file": str(model_file),
        },
    )


def read_selected_feature_names(best_features_file: Path, sort_original_file: Path) -> list[str]:
    sort_columns = list(pd.read_csv(sort_original_file, nrows=0).columns)
    if TARGET_COLUMN in sort_columns:
        target_dropped_columns = [column for column in sort_columns if column != TARGET_COLUMN]
    else:
        target_dropped_columns = sort_columns

    with best_features_file.open("rb") as handle:
        feature_mask = pickle.load(handle)

    candidate_columns = None
    if isinstance(feature_mask, list) and len(feature_mask) == len(sort_columns):
        candidate_columns = sort_columns
    elif isinstance(feature_mask, list) and len(feature_mask) == len(target_dropped_columns):
        candidate_columns = target_dropped_columns

    if candidate_columns is None:
        raise ValueError(
            "The saved best_features_sort_original.pkl does not match the columns in sort_original.csv."
        )
    return [column for column, enabled in zip(candidate_columns, feature_mask) if bool(enabled)]


def resolve_prediction_feature_names(
    model_file: Path,
    best_features_file: Path,
    sort_original_file: Path,
) -> list[str]:
    model_feature_names = read_model_feature_names(model_file)
    if model_feature_names:
        return model_feature_names
    return read_selected_feature_names(best_features_file, sort_original_file)


def build_model_input(df: pd.DataFrame, feature_names: list[str]) -> pd.DataFrame:
    base_df = df.drop(
        columns=[*GEO_COLUMNS, *GERMPLASM_COLUMNS, TARGET_COLUMN],
        errors="ignore",
    ).copy()
    for column in feature_names:
        if column not in base_df.columns:
            base_df[column] = 0.0
    model_df = base_df[feature_names].copy()
    for column in model_df.columns:
        model_df[column] = pd.to_numeric(model_df[column], errors="coerce").fillna(0.0)
    return model_df


def run_prediction_subprocess(
    resolved_model: ResolvedModel,
    model_input_csv: Path,
    predictions_json: Path,
) -> None:
    featurehero_python = get_featurehero_python()
    featurehero_repo = get_featurehero_repo()
    if not resolved_model.model_file.exists():
        raise FileNotFoundError(f"Missing Grain Yield model file: {resolved_model.model_file}")
    if not featurehero_python.exists():
        raise FileNotFoundError(f"Missing FeatureHero python: {featurehero_python}")

    env = os.environ.copy()
    featurehero_pythonpath = str(featurehero_repo)
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        featurehero_pythonpath
        if not existing_pythonpath
        else f"{featurehero_pythonpath}:{existing_pythonpath}"
    )

    command = [
        str(featurehero_python),
        str(RUNTIME_SCRIPT),
        "--model-file",
        str(resolved_model.model_file),
        "--input-csv",
        str(model_input_csv),
        "--output-json",
        str(predictions_json),
    ]
    result = subprocess.run(
        command,
        cwd=str(ROOT_DIR),
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip() or result.stdout.strip() or "The Grain Yield prediction subprocess failed."
        )


def run_grain_yield_prediction(
    phase5_csv: Path,
    model_dir: Path,
    selected_model_id: str | None = None,
) -> GrainYieldPredictionOutputs:
    model_dir.mkdir(parents=True, exist_ok=True)
    model_input_csv = model_dir / "grain_yield_model_input.csv"
    predictions_json = model_dir / "grain_yield_predictions.json"
    output_csv = model_dir / "phase5_with_predictions.csv"
    output_xlsx = model_dir / "phase5_with_predictions.xlsx"

    resolved_model = resolve_active_model(selected_model_id=selected_model_id)
    phase5_df = pd.read_csv(phase5_csv, dtype=object)
    feature_names = resolve_prediction_feature_names(
        resolved_model.model_file,
        resolved_model.best_features_file,
        resolved_model.sort_original_file,
    )
    model_input_df = build_model_input(phase5_df, feature_names)
    model_input_df.to_csv(model_input_csv, index=False)
    run_prediction_subprocess(resolved_model, model_input_csv, predictions_json)

    predictions_payload = json.loads(predictions_json.read_text(encoding="utf-8"))
    predictions = predictions_payload["predictions"]

    predicted_df = phase5_df.copy()
    insert_at = (
        predicted_df.columns.get_loc(TARGET_COLUMN) + 1
        if TARGET_COLUMN in predicted_df.columns
        else len(predicted_df.columns)
    )
    predicted_df.insert(insert_at, PREDICTED_COLUMN, predictions)
    predicted_df.to_csv(output_csv, index=False)
    predicted_df.to_excel(output_xlsx, index=False)

    return GrainYieldPredictionOutputs(
        dataframe=predicted_df,
        source_dataframe=phase5_df,
        model_input_csv=model_input_csv,
        output_csv=output_csv,
        output_xlsx=output_xlsx,
        model_name=resolved_model.model_name,
        feature_names=feature_names,
        model_metadata=resolved_model.metadata,
    )
