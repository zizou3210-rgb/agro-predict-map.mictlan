from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


CATEGORICAL_COLUMNS = [
    "Education/Training of the farmer",
    "Gender of the farmer (plot manager)",
    "Age of the plot manager",
    "Soil type/texture",
    "Soil Depth (cm)-How deep do you expect maize roots to grow in this soil?",
    "Cropping practices",
    "is_fertilizer",
    "Weed control practices",
    "is_Trial_management_by_action_herbicide",
    "is_Trial_management_by_action_Insecticide",
]


@dataclass
class Phase4Outputs:
    dataframe: pd.DataFrame
    csv_file: Path
    xlsx_file: Path


def normalize_dummy_source_value(value: object) -> object:
    if pd.isna(value):
        return pd.NA
    text = str(value).strip()
    if not text or text in {"0", "0.0"}:
        return pd.NA
    numeric = pd.to_numeric(pd.Series([text]), errors="coerce").iloc[0]
    if pd.notna(numeric):
        return f"{float(numeric):.1f}"
    return text


def run_phase4(input_csv: Path, phase_dir: Path) -> Phase4Outputs:
    phase_dir.mkdir(parents=True, exist_ok=True)
    phase4_csv = phase_dir / "phase4.csv"
    phase4_xlsx = phase_dir / "phase4.xlsx"
    phase4_transform_csv = phase_dir / "phase4_transform.csv"
    phase4_transform_xlsx = phase_dir / "phase4_transform.xlsx"

    df = pd.read_csv(input_csv, dtype=object)
    df.to_csv(phase4_csv, index=False)
    df.to_excel(phase4_xlsx, index=False)

    missing_columns = [column for column in CATEGORICAL_COLUMNS if column not in df.columns]
    if missing_columns:
        raise KeyError("Missing categorical columns in phase4 input:\n- " + "\n- ".join(missing_columns))

    transformed_df = df.copy()
    for column in CATEGORICAL_COLUMNS:
        transformed_df[column] = transformed_df[column].apply(normalize_dummy_source_value)

    dummy_frames = []
    for column in CATEGORICAL_COLUMNS:
        dummies = pd.get_dummies(transformed_df[column], prefix=column, dtype="Int64")
        if not dummies.empty:
            dummies.columns = [str(name) for name in dummies.columns]
            dummies = dummies.astype("Int64")
            missing_mask = transformed_df[column].isna()
            if missing_mask.any():
                dummies.loc[missing_mask, :] = pd.NA
        dummy_frames.append(dummies)

    base_df = transformed_df.drop(columns=CATEGORICAL_COLUMNS, errors="ignore")
    final_df = pd.concat([base_df, *dummy_frames], axis=1)

    final_df.to_csv(phase4_transform_csv, index=False)
    final_df.to_excel(phase4_transform_xlsx, index=False)

    return Phase4Outputs(
        dataframe=final_df,
        csv_file=phase4_transform_csv,
        xlsx_file=phase4_transform_xlsx,
    )
