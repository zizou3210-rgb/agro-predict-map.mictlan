from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .common import FORECAST_METADATA_COLUMNS, GEO_COLUMNS, GERMPLASM_COLUMNS


STANDARDIZE_COLUMNS = [
    "Root Lodging (%)",
    "Stem Logding (%)",
    "Grey_Leaf_Spot_GLS_5_very_susceptible_header",
    "Turcicum_leaf_blight_5_very_susceptible_header",
    "Puccinia_sorghi_Com_5_very_susceptible_header",
    "Maize_Streak_Virus_S_5_very_susceptible_header",
    "Percentage_Plant_harvest_stand_t_harvesting_Plot_1",
    "Percentage_Number_of_plants_wit_root_lodging_Plot_1",
    "Percentage_Number_of_plants_wit_stem_lodging_Plot_1",
    "Percentage_Count_number_of_rotten_ears_Plot_1",
    "planting_week_1_total_prectotcorr (mm)",
    "planting_week_2_total_prectotcorr (mm)",
    "planting_week_2_avg_t2m (C)",
    "intermediate_period_total_prectotcorr (mm)",
    "intermediate_period_avg_t2m (C)",
    "harvest_back_week_1_total_prectotcorr (mm)",
    "harvest_back_week_1_avg_t2m (C)",
    "harvest_back_week_2_total_prectotcorr (mm)",
    "harvest_back_week_2_avg_t2m (C)",
    "harvest_back_week_3_total_prectotcorr (mm)",
    "harvest_back_week_3_avg_t2m (C)",
    "harvest_back_week_4_total_prectotcorr (mm)",
    "harvest_back_week_4_avg_t2m (C)",
    "harvest_back_week_5_total_prectotcorr (mm)",
    "harvest_back_week_5_avg_t2m (C)",
    "harvest_back_week_6_total_prectotcorr (mm)",
    "harvest_back_week_6_avg_t2m (C)",
    "harvest_back_week_7_total_prectotcorr (mm)",
    "harvest_back_week_7_avg_t2m (C)",
    "harvest_back_week_8_total_prectotcorr (mm)",
    "harvest_back_week_8_avg_t2m (C)",
    "Farmers total land area (acres)",
]

DOT_AS_MISSING_COLUMNS = set(STANDARDIZE_COLUMNS)

PRESERVE_NUMERIC_COLUMNS = [
    "Rank",
    "Rotten Ears (%)",
    "Grain Yield (T/Ha)",
    "Plant_Aspect_1_5_1_h_high_ear_placement_header",
    "Ear_aspect_1_5_1_n_undesirable_texture_header",
    "Education/Training of the farmer_Partial or completed secondary",
    "Education/Training of the farmer_Post-secondary",
    "Education/Training of the farmer_Primary",
    "Gender of the farmer (plot manager)_Female",
    "Gender of the farmer (plot manager)_Male",
    "Age of the plot manager_Above 50 years",
    "Age of the plot manager_Below 35 years",
    "Age of the plot manager_Between 35 and 50 years",
    "Soil type/texture_Clay Loam",
    "Soil type/texture_Loam",
    "Soil type/texture_Sandy Loam",
    "Soil type/texture_Silty Loam",
    "Soil Depth (cm)-How deep do you expect maize roots to grow in this soil?_100cm o mas",
    "Soil Depth (cm)-How deep do you expect maize roots to grow in this soil?_50cm",
    "Soil Depth (cm)-How deep do you expect maize roots to grow in this soil?_75cm",
    "Cropping practices_Intercrop",
    "Cropping practices_Maize monocrop",
    "Cropping practices_Rotation cropping",
    "is_fertilizer_1.0",
    "Weed control practices_Chemical",
    "Weed control practices_Hand",
    "is_Trial_management_by_action_herbicide_1.0",
    "is_Trial_management_by_action_Insecticide_1.0",
]


@dataclass
class Phase5Outputs:
    dataframe: pd.DataFrame
    geo_dataframe: pd.DataFrame
    csv_file: Path
    xlsx_file: Path


def clean_numeric_series(series: pd.Series, treat_dot_as_missing: bool) -> pd.Series:
    stripped = series.astype(str).str.strip()
    blank_mask = series.isna() | stripped.eq("")
    dot_mask = stripped.eq(".") if treat_dot_as_missing else pd.Series(False, index=series.index)
    cleaned = series.mask(blank_mask | dot_mask, pd.NA)
    return pd.to_numeric(cleaned, errors="coerce")


def should_apply_log(series: pd.Series) -> bool:
    valid = series.dropna()
    if len(valid) < 3 or (valid < 0).any():
        return False
    std_sample = float(valid.std(ddof=1))
    if std_sample == 0 or math.isnan(std_sample):
        return False
    mean_value = float(valid.mean())
    z_scores = (valid - mean_value) / std_sample
    return bool((z_scores > 3).any() and z_scores.min() > -3)


def apply_log_transform(series: pd.Series) -> pd.Series:
    valid = series.dropna()
    if valid.empty:
        return series
    if (valid == 0).any():
        return series.map(lambda value: math.log1p(value) if pd.notna(value) else pd.NA)
    return series.map(lambda value: math.log(value) if pd.notna(value) else pd.NA)


def preserve_numeric_columns(df: pd.DataFrame) -> None:
    for column in PRESERVE_NUMERIC_COLUMNS:
        if column in df.columns:
            df[column] = clean_numeric_series(df[column].copy(), treat_dot_as_missing=False)


def run_phase5(input_csv: Path, phase_dir: Path) -> Phase5Outputs:
    phase_dir.mkdir(parents=True, exist_ok=True)
    phase5_csv = phase_dir / "phase5.csv"
    phase5_xlsx = phase_dir / "phase5.xlsx"
    phase5_standardized_csv = phase_dir / "phase5_standardized.csv"
    phase5_standardized_xlsx = phase_dir / "phase5_standardized.xlsx"

    df = pd.read_csv(input_csv, dtype=object)
    df.to_csv(phase5_csv, index=False)
    df.to_excel(phase5_xlsx, index=False)

    preserved_geo_columns = [column for column in GEO_COLUMNS if column in df.columns]
    preserved_germplasm_columns = [column for column in GERMPLASM_COLUMNS if column in df.columns]
    preserved_metadata_columns = [column for column in FORECAST_METADATA_COLUMNS if column in df.columns]
    preserved_geo_df = df[
        [
            *preserved_geo_columns,
            *preserved_germplasm_columns,
            *preserved_metadata_columns,
        ]
    ].copy()
    analytical_df = df.drop(
        columns=[*preserved_geo_columns, *preserved_germplasm_columns],
        errors="ignore",
    ).copy()

    missing_columns = [column for column in STANDARDIZE_COLUMNS if column not in analytical_df.columns]
    if missing_columns:
        raise KeyError("Missing columns in phase5 input:\n- " + "\n- ".join(missing_columns))

    standardized_df = analytical_df.copy()
    for column in STANDARDIZE_COLUMNS:
        numeric_series = clean_numeric_series(
            standardized_df[column].copy(),
            treat_dot_as_missing=column in DOT_AS_MISSING_COLUMNS,
        )
        if should_apply_log(numeric_series):
            numeric_series = apply_log_transform(numeric_series)

        mean = float(numeric_series.mean(skipna=True))
        std = float(numeric_series.std(skipna=True, ddof=1))
        if std == 0 or math.isnan(std):
            standardized = numeric_series.where(numeric_series.isna(), 0.0)
        else:
            standardized = (numeric_series - mean) / std
        standardized_df[column] = standardized

    preserve_numeric_columns(standardized_df)
    output_df = pd.concat(
        [df[preserved_germplasm_columns].reset_index(drop=True), standardized_df.reset_index(drop=True)],
        axis=1,
    )
    output_df.to_csv(phase5_standardized_csv, index=False)
    output_df.to_excel(phase5_standardized_xlsx, index=False)

    return Phase5Outputs(
        dataframe=output_df,
        geo_dataframe=preserved_geo_df,
        csv_file=phase5_standardized_csv,
        xlsx_file=phase5_standardized_xlsx,
    )
