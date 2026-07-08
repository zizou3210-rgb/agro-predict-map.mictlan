from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


LOG_COLUMN_SOURCE = "Farmers total land area (acres)"
LOG_COLUMN_OUTPUT = "Farmers total land area (acres)_log1p"
ZERO_TO_EMPTY_COLUMN = "Grain_moisture_Plot_1"
HARVEST_STAND_PERCENT_COLUMN = "Percentage_Plant_harvest_stand_t_harvesting_Plot_1"
YIELD_COLUMN = "Grain Yield (T/Ha)"
GENDER_COLUMN = "Gender of the farmer (plot manager)"
GENDER_OLD_VALUE = "Joint"
GENDER_NEW_VALUE = "Male"
EDUCATION_COLUMN = "Education/Training of the farmer"
EDUCATION_OLD_VALUE = "None/incomplete primary"
EDUCATION_NEW_VALUE = "Primary"
SOIL_COLUMN = "Soil type/texture"
SOIL_REPLACEMENTS = {
    "Sandy": "Sandy Loam",
    "Clay": "Clay Loam",
}
SOIL_DEPTH_COLUMN = (
    "Soil Depth (cm)-How deep do you expect maize roots to grow in this soil?"
)
SOIL_DEPTH_REPLACEMENTS = {
    "100cm": "100cm o mas",
    "125cm": "100cm o mas",
    "150cm or more": "100cm o mas",
}
CROPPING_PRACTICES_COLUMN = "Cropping practices"
CROPPING_PRACTICES_OLD_VALUE = "Fallow/shifting cultivation"
CROPPING_PRACTICES_NEW_VALUE = "Rotation cropping"
IS_FERTILIZER_COLUMN = "is_fertilizer"
FERTILIZER_TIMES_COLUMN = "Number_of_times_fertilizer_was_applied"
DATE_COLUMNS_TO_DROP = (
    "Date of planting",
    "Date_of_harvesting",
)
ADDITIONAL_COLUMNS_TO_DROP = (
    "Plant_harvest_stand_t_harvesting_Plot_1",
    "Number_of_plants_wit_root_lodging_Plot_1",
    "Number_of_plants_wit_stem_lodging_Plot_1",
    "Poor_husk_cover_Plot_1",
    "Number_of_ears_harvested_Plot_1",
    "Count_number_of_rotten_ears_Plot_1",
)


@dataclass
class Phase3Outputs:
    dataframe: pd.DataFrame
    csv_file: Path
    xlsx_file: Path


def build_final_df(df: pd.DataFrame) -> pd.DataFrame:
    final_df = df.copy()
    if (
        IS_FERTILIZER_COLUMN in final_df.columns
        and FERTILIZER_TIMES_COLUMN in final_df.columns
    ):
        fertilizer_times = pd.to_numeric(
            final_df[FERTILIZER_TIMES_COLUMN],
            errors="coerce",
        )
        is_fertilizer = pd.to_numeric(
            final_df[IS_FERTILIZER_COLUMN],
            errors="coerce",
        )
        final_df[IS_FERTILIZER_COLUMN] = final_df[IS_FERTILIZER_COLUMN].mask(
            fertilizer_times.ge(1) & is_fertilizer.ne(1),
            1,
        )

    final_df = final_df.drop(
        columns=[
            LOG_COLUMN_SOURCE,
            FERTILIZER_TIMES_COLUMN,
            *DATE_COLUMNS_TO_DROP,
            *ADDITIONAL_COLUMNS_TO_DROP,
        ],
        errors="ignore",
    )
    final_df = final_df.rename(columns={LOG_COLUMN_OUTPUT: LOG_COLUMN_SOURCE})

    if ZERO_TO_EMPTY_COLUMN in final_df.columns:
        grain_moisture = pd.to_numeric(final_df[ZERO_TO_EMPTY_COLUMN], errors="coerce")
        final_df[ZERO_TO_EMPTY_COLUMN] = final_df[ZERO_TO_EMPTY_COLUMN].mask(
            grain_moisture == 0,
            pd.NA,
        )

    if HARVEST_STAND_PERCENT_COLUMN in final_df.columns and YIELD_COLUMN in final_df.columns:
        harvest_stand_percent = pd.to_numeric(
            final_df[HARVEST_STAND_PERCENT_COLUMN],
            errors="coerce",
        )
        yield_values = pd.to_numeric(final_df[YIELD_COLUMN], errors="coerce")
        final_df[HARVEST_STAND_PERCENT_COLUMN] = final_df[
            HARVEST_STAND_PERCENT_COLUMN
        ].mask(harvest_stand_percent.eq(0) & yield_values.gt(0), pd.NA)

    if GENDER_COLUMN in final_df.columns:
        final_df[GENDER_COLUMN] = final_df[GENDER_COLUMN].replace(
            GENDER_OLD_VALUE,
            GENDER_NEW_VALUE,
        )
    if EDUCATION_COLUMN in final_df.columns:
        final_df[EDUCATION_COLUMN] = final_df[EDUCATION_COLUMN].replace(
            EDUCATION_OLD_VALUE,
            EDUCATION_NEW_VALUE,
        )
    if SOIL_COLUMN in final_df.columns:
        final_df[SOIL_COLUMN] = final_df[SOIL_COLUMN].replace(SOIL_REPLACEMENTS)
    if SOIL_DEPTH_COLUMN in final_df.columns:
        final_df[SOIL_DEPTH_COLUMN] = final_df[SOIL_DEPTH_COLUMN].replace(
            SOIL_DEPTH_REPLACEMENTS
        )
    if CROPPING_PRACTICES_COLUMN in final_df.columns:
        final_df[CROPPING_PRACTICES_COLUMN] = final_df[
            CROPPING_PRACTICES_COLUMN
        ].replace(CROPPING_PRACTICES_OLD_VALUE, CROPPING_PRACTICES_NEW_VALUE)
    return final_df


def run_phase3(input_csv: Path, phase_dir: Path) -> Phase3Outputs:
    phase_dir.mkdir(parents=True, exist_ok=True)
    log_output_file = phase_dir / "phase3_log_transformed.csv"
    transformed_xlsx_file = phase_dir / "phase3_transformed.xlsx"
    transformed_csv_file = phase_dir / "phase3_transformed.csv"

    df = pd.read_csv(input_csv, dtype=object)
    if LOG_COLUMN_SOURCE in df.columns:
        numeric_col = pd.to_numeric(df[LOG_COLUMN_SOURCE], errors="coerce")
        invalid_mask = df[LOG_COLUMN_SOURCE].notna() & numeric_col.isna()
        if invalid_mask.any():
            raise ValueError(
                f"Column '{LOG_COLUMN_SOURCE}' contains non-numeric values and "
                "cannot be transformed with log1p."
            )
        negative_mask = numeric_col < 0
        if negative_mask.any():
            raise ValueError(
                f"Column '{LOG_COLUMN_SOURCE}' contains negative values and "
                "cannot be transformed with log1p."
            )
        df[LOG_COLUMN_OUTPUT] = numeric_col.apply(
            lambda value: math.log1p(value) if pd.notna(value) else pd.NA
        )
    df.to_csv(log_output_file, index=False)

    final_df = build_final_df(df)
    final_df.to_csv(transformed_csv_file, index=False)
    final_df.to_excel(transformed_xlsx_file, index=False)

    return Phase3Outputs(
        dataframe=final_df,
        csv_file=transformed_csv_file,
        xlsx_file=transformed_xlsx_file,
    )
