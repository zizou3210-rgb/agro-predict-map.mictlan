from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from ce_pipeline.phase04.phase04 import CANONICAL_TARGET_COLUMN
from ce_pipeline.phase05.phase05 import run_ce_phase05
from pipeline.common import dataframe_to_geojson
from pipeline.model.grain_yield_model import GrainYieldPredictionOutputs


class PipelineGeojsonCountryTest(unittest.TestCase):
    def test_dataframe_to_geojson_derives_country_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir_name:
            tmp_dir = Path(tmp_dir_name)
            df = pd.DataFrame(
                {
                    "Country": [""],
                    "_GPS coordinates_latitude": [0.313611],
                    "_GPS coordinates_longitude": [32.581111],
                    "Name": ["PIONEER"],
                }
            )

            geojson = dataframe_to_geojson(df, tmp_dir / "derived_country.geojson")

            self.assertEqual(geojson["features"][0]["properties"]["Country"], "Uganda")
            self.assertEqual(geojson["features"][0]["properties"]["Derived Country"], "Uganda")


class CePhase05Test(unittest.TestCase):
    def test_run_ce_phase05_reuses_training_csv_and_builds_prediction_geojson(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir_name:
            tmp_dir = Path(tmp_dir_name)
            phase04_workbook = tmp_dir / "phase04.xlsx"
            training_input_csv = tmp_dir / "phase04_training_input.csv"
            run_dir = tmp_dir / "phase05"

            phase04_df = pd.DataFrame(
                {
                    "Country": [""],
                    "_GPS coordinates_latitude": [0.313611],
                    "_GPS coordinates_longitude": [32.581111],
                    "Trial series name": ["EAPP1-01 (Medium)"],
                    "Rep": ["1"],
                    "Farm": ["1"],
                    "Site Number": ["1"],
                    "Plot": ["1"],
                    "EntryCode": ["ENTRY-001"],
                    "Name": ["PIONEER"],
                    "Nursery Id": ["ID-01"],
                    "Local check, Name of variety provided by farmer": ["Local Variety"],
                    CANONICAL_TARGET_COLUMN: [5.5],
                    "Yield user selected": [5.5],
                    "Date of planting": ["2026-03-28"],
                    "Date_of_harvesting": ["2026-08-23"],
                    "Soil type/texture": ["Loam"],
                    "Soil Depth (cm)-How deep do you expect maize roots to grow in this soil?": ["75cm"],
                }
            )
            phase04_df.to_excel(phase04_workbook, index=False)

            training_input_df = pd.DataFrame(
                {
                    "Name": ["PIONEER"],
                    CANONICAL_TARGET_COLUMN: [5.5],
                    "feature_a": [1.25],
                }
            )
            training_input_df.to_csv(training_input_csv, index=False)
            training_input_csv.with_suffix(".xlsx").write_bytes(b"")

            model_dir = run_dir / "model"
            model_dir.mkdir(parents=True, exist_ok=True)
            model_input_csv = model_dir / "grain_yield_model_input.csv"
            output_csv = model_dir / "phase5_with_predictions.csv"
            output_xlsx = model_dir / "phase5_with_predictions.xlsx"
            model_input_csv.write_text("feature_a\n1.25\n", encoding="utf-8")
            output_csv.write_text("", encoding="utf-8")
            output_xlsx.write_bytes(b"")

            prediction_df = pd.DataFrame(
                {
                    "Name": ["PIONEER"],
                    CANONICAL_TARGET_COLUMN: [5.5],
                    "feature_a": [1.25],
                    "Grain Yield predicted": [6.25],
                }
            )

            mocked_prediction = GrainYieldPredictionOutputs(
                dataframe=prediction_df,
                source_dataframe=training_input_df,
                model_input_csv=model_input_csv,
                output_csv=output_csv,
                output_xlsx=output_xlsx,
                model_name="Extreme Gradient Boosting",
                feature_names=["feature_a"],
                model_metadata={
                    "model_id": "model-123",
                    "created_at": "2026-05-25T12:12:12",
                    "display_name": "Default model",
                    "description": "Model used for ce_pipeline prediction",
                    "metric_name": "mean_absolute_error",
                    "metric_value": 0.4321,
                },
            )

            with patch(
                "cimmyt_app.ce_pipeline.phase05.phase05.run_grain_yield_prediction",
                return_value=mocked_prediction,
            ):
                outputs = run_ce_phase05(
                    phase04_workbook=phase04_workbook,
                    training_input_csv=training_input_csv,
                    run_dir=run_dir,
                    source_name="phase04.xlsx",
                    target_column="Yield user selected",
                    selected_id_header="Nursery Id",
                    selected_model_id="model-123",
                )

            self.assertEqual(outputs.summary["workflow"], "ce_pipeline_prediction")
            self.assertEqual(outputs.summary["prediction_model_id"], "model-123")
            self.assertEqual(outputs.summary["selected_model_id"], "model-123")
            self.assertEqual(outputs.summary["selected_id_header"], "Nursery Id")
            self.assertTrue(outputs.summary_file.exists())
            self.assertTrue(outputs.geojson_file.exists())
            self.assertEqual(outputs.geojson["features"][0]["properties"]["Country"], "Uganda")
            self.assertEqual(outputs.geojson["features"][0]["properties"]["Nursery Id"], "ID-01")
            self.assertEqual(outputs.geojson["features"][0]["properties"]["Grain Yield predicted"], 6.25)


if __name__ == "__main__":
    unittest.main()
