from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .common import DATE_HEADERS, normalize_phase2_dates, parse_numeric_value


GRAIN_YIELD_HEADER = "Grain Yield (T/Ha)"
WEED_CONTROL_HEADER = "Weed control practices"
WEED_CONTROL_OLD_VALUE = "Mechanical (machinery)"
WEED_CONTROL_NEW_VALUE = "Hand"

REMOVED_HEADERS = {
    "_8_1_BM_Who_in_your_h_e_on_farm_experiment",
    "_8_2_BM_Who_in_your_h_e_on_farm_experiment",
    "Percentage_Poor_husk_cover_Plot_1",
    "Bad Husk Cover (%)",
    "Percentage_Number_of_ears_harvested_Plot_1",
    "Ears/Plant (#)",
    "Grain_moisture_Plot_1",
    "Plant_height_Plot_1",
    "Ear_height_Plot_1",
    "Ear Position",
    "Plant stand ; plot 1",
    "Plot Area",
}


@dataclass
class Phase2Outputs:
    dataframe: pd.DataFrame
    csv_file: Path
    xlsx_file: Path
    excluded_file: Path


def run_phase2(
    input_file: Path,
    phase_dir: Path,
    *,
    allow_zero_grain_yield: bool = False,
) -> Phase2Outputs:
    phase_dir.mkdir(parents=True, exist_ok=True)

    csv_file = phase_dir / "phase2.csv"
    xlsx_file = phase_dir / "phase2.xlsx"
    excluded_file = phase_dir / "withCeroGrain_Yield_(T_Ha).xlsx"

    df = pd.read_excel(input_file, dtype=object)
    df.columns = [str(column).strip() for column in df.columns]
    df = df[[column for column in df.columns if column not in REMOVED_HEADERS]].copy()

    normalize_phase2_dates(df, DATE_HEADERS)

    if WEED_CONTROL_HEADER in df.columns:
        df[WEED_CONTROL_HEADER] = df[WEED_CONTROL_HEADER].replace(
            WEED_CONTROL_OLD_VALUE,
            WEED_CONTROL_NEW_VALUE,
        )

    excluded_reasons: list[str] = []
    keep_mask: list[bool] = []

    for _, row in df.iterrows():
        reasons: list[str] = []
        planting_date_value = row.get("Date of planting")
        harvesting_date_value = row.get("Date_of_harvesting")
        grain_yield_value = parse_numeric_value(row.get(GRAIN_YIELD_HEADER))

        if planting_date_value is None or str(planting_date_value).strip() == "":
            reasons.append("date_of_planting_blank")
        if harvesting_date_value is None or str(harvesting_date_value).strip() == "":
            reasons.append("date_of_harvesting_blank")
        if (
            not allow_zero_grain_yield
            and grain_yield_value is not None
            and grain_yield_value <= 0
        ):
            reasons.append("grain_yield_le_zero")

        excluded_reasons.append(";".join(reasons))
        keep_mask.append(not reasons)

    kept_df = df.loc[keep_mask].copy()
    excluded_df = df.loc[[not item for item in keep_mask]].copy()
    if not excluded_df.empty:
        excluded_df.insert(0, "excluded_reason", [reason for reason, keep in zip(excluded_reasons, keep_mask) if not keep])

    kept_df.to_csv(csv_file, index=False)
    kept_df.to_excel(xlsx_file, index=False)
    excluded_df.to_excel(excluded_file, index=False)

    return Phase2Outputs(
        dataframe=kept_df,
        csv_file=csv_file,
        xlsx_file=xlsx_file,
        excluded_file=excluded_file,
    )
