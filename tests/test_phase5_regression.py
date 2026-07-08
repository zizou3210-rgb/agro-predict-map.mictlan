from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd
from pandas.testing import assert_frame_equal

from cimmyt_app.pipeline.phase2 import run_phase2
from cimmyt_app.pipeline.phase3 import run_phase3
from cimmyt_app.pipeline.phase4 import run_phase4
from cimmyt_app.pipeline.phase5 import run_phase5
from cimmyt_app.pipeline.common import GERMPLASM_COLUMNS


ROOT_DIR = Path(__file__).resolve().parents[2]
PHASE1_INPUT = ROOT_DIR / "EA_merged" / "phases" / "phase1" / "phase1.xlsx"
PHASE5_REFERENCE = ROOT_DIR / "EA_merged" / "phases" / "phase5" / "phase5_standardized.xlsx"


def normalize_frame(df: pd.DataFrame) -> pd.DataFrame:
    normalized = df.copy()
    normalized.columns = [str(column).strip() for column in normalized.columns]
    normalized = normalized.reindex(sorted(normalized.columns), axis=1)
    normalized = normalized.reset_index(drop=True)

    for column in normalized.columns:
        series = normalized[column]
        if pd.api.types.is_numeric_dtype(series):
            normalized[column] = pd.to_numeric(series, errors="coerce")
        else:
            normalized[column] = series.map(
                lambda value: None if pd.isna(value) or str(value).strip() == "" else str(value).strip()
            )
    return normalized


class Phase5RegressionTest(unittest.TestCase):
    maxDiff = None

    def test_phase2_keeps_zero_grain_yield_rows_for_saved_model_prediction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir_name:
            tmp_dir = Path(tmp_dir_name)
            input_df = pd.DataFrame(
                [
                    {
                        "Date of planting": "2026-03-28",
                        "Date_of_harvesting": "2026-08-23",
                        "Grain Yield (T/Ha)": 0,
                        "_GPS coordinates_latitude": -0.546307,
                        "_GPS coordinates_longitude": 37.429588,
                        "Name": "BAZOOKA",
                    }
                ]
            )
            input_path = tmp_dir / "phase1_prediction.xlsx"
            input_df.to_excel(input_path, index=False)

            training_phase2 = run_phase2(input_path, tmp_dir / "phase2_training")
            prediction_phase2 = run_phase2(
                input_path,
                tmp_dir / "phase2_prediction",
                allow_zero_grain_yield=True,
            )

            self.assertEqual(len(training_phase2.dataframe), 0)
            self.assertEqual(len(prediction_phase2.dataframe), 1)

    def test_phase5_matches_ea_merged_reference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir_name:
            tmp_dir = Path(tmp_dir_name)
            phase2 = run_phase2(PHASE1_INPUT, tmp_dir / "phase2")
            phase3 = run_phase3(phase2.csv_file, tmp_dir / "phase3")
            phase4 = run_phase4(phase3.csv_file, tmp_dir / "phase4")
            phase5 = run_phase5(phase4.csv_file, tmp_dir / "phase5")

            actual_df = pd.read_excel(phase5.xlsx_file)
            expected_df = pd.read_excel(PHASE5_REFERENCE)

        actual_normalized = normalize_frame(actual_df)
        expected_normalized = normalize_frame(expected_df)

        for column in GERMPLASM_COLUMNS:
            actual_normalized = actual_normalized.drop(columns=[column], errors="ignore")

        self.assertEqual(
            list(actual_normalized.columns),
            list(expected_normalized.columns),
            "The app phase5 output columns differ from the EA_merged phase5 reference.",
        )
        self.assertEqual(
            len(actual_normalized),
            len(expected_normalized),
            "The app phase5 output row count differs from the EA_merged phase5 reference.",
        )

        assert_frame_equal(
            actual_normalized,
            expected_normalized,
            check_dtype=False,
            check_exact=False,
            atol=1e-9,
            rtol=1e-9,
        )

    def test_phase5_preserves_germplasm_columns_for_map_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir_name:
            tmp_dir = Path(tmp_dir_name)
            input_df = pd.read_excel(PHASE1_INPUT)
            germplasm_seed = {
                "Trial series name": "EAPP1-01 (Medium)",
                "Rep": "1",
                "Farm": "1",
                "Site Number": "1",
                "Plot": "1",
                "EntryCode": "ENTRY-001",
                "Name": "PIONEER",
                "Local check, Name of variety provided by farmer": "Local Variety",
            }
            for column, value in germplasm_seed.items():
                input_df[column] = value

            enriched_input = tmp_dir / "phase1_with_germplasm.xlsx"
            input_df.to_excel(enriched_input, index=False)

            phase2 = run_phase2(enriched_input, tmp_dir / "phase2")
            phase3 = run_phase3(phase2.csv_file, tmp_dir / "phase3")
            phase4 = run_phase4(phase3.csv_file, tmp_dir / "phase4")
            phase5 = run_phase5(phase4.csv_file, tmp_dir / "phase5")

            for column in GERMPLASM_COLUMNS:
                self.assertIn(column, phase5.dataframe.columns)
                self.assertIn(column, phase5.geo_dataframe.columns)
