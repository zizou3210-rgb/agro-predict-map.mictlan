from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from cimmyt_app.ce_pipeline.prediction.prediction import (
    PREDICTION_PREDICTED_COLUMN,
    run_ce_saved_model_prediction,
)
from cimmyt_app.ce_pipeline.phase05.phase05 import CePhase05Outputs
from cimmyt_app.pipeline.common import dataframe_to_geojson
from cimmyt_app.server import (
    _build_manual_grid_profile_overlay_payload,
    build_prediction_display_feature_collection,
    should_skip_running_preprocess_geojson,
)


TEST_WORKBOOK = Path(__file__).resolve().parent / "source" / "AGG_2024_2025_V5.xlsx"
TEST_MODEL_ID = "agg-2024-2025-test-model"
TEST_GERMPLASM = "CIM-RT-EAPP1-E -013"
BOUNDING_BOX = {
    "latitude_min": 0.384626,
    "latitude_max": 0.762280,
    "longitude_min": 37.594737,
    "longitude_max": 38.091162,
}


def build_selection_summary() -> dict[str, object]:
    return {
        "initial_settings": {
            "target_column": "Grain Yield (T/Ha)",
            "longitude_column": "_GPS coordinates_longitude",
            "latitude_column": "_GPS coordinates_latitude",
            "planting_date_column": "Date of planting",
            "harvesting_date_column": "Date_of_harvesting",
            "soil_texture_column": "Soil type/texture",
            "soil_depth_column": "Soil Depth (cm)-How deep do you expect maize roots to grow in this soil?",
        },
        "divisions": {
            "germplams_identifiers": ["Name", "Farm", "Site Number", "Plot", "EntryCode"],
            "categorical_data": ["Education/Training of the farmer"],
            "cuantitative_data": [],
            "DG": [],
        },
    }


def build_manual_bbox_grid() -> dict[str, object]:
    longitude_mid = round((BOUNDING_BOX["longitude_min"] + BOUNDING_BOX["longitude_max"]) / 2.0, 6)
    latitude_mid = round((BOUNDING_BOX["latitude_min"] + BOUNDING_BOX["latitude_max"]) / 2.0, 6)
    return {
        "label": "Manual bounds",
        "grid_resolution_km": 5.0,
        "grid_cell_count": 2,
        "cells": [
            {
                "grid_cell_index": 1,
                "grid_cell_id": "Manual bounds:R1C1",
                "grid_row_index": 1,
                "grid_column_index": 1,
                "label": "Manual bounds",
                "latitude_min": BOUNDING_BOX["latitude_min"],
                "latitude_max": BOUNDING_BOX["latitude_max"],
                "longitude_min": BOUNDING_BOX["longitude_min"],
                "longitude_max": longitude_mid,
                "center_latitude": latitude_mid,
                "center_longitude": round((BOUNDING_BOX["longitude_min"] + longitude_mid) / 2.0, 6),
            },
            {
                "grid_cell_index": 2,
                "grid_cell_id": "Manual bounds:R1C2",
                "grid_row_index": 1,
                "grid_column_index": 2,
                "label": "Manual bounds",
                "latitude_min": BOUNDING_BOX["latitude_min"],
                "latitude_max": BOUNDING_BOX["latitude_max"],
                "longitude_min": longitude_mid,
                "longitude_max": BOUNDING_BOX["longitude_max"],
                "center_latitude": latitude_mid,
                "center_longitude": round((longitude_mid + BOUNDING_BOX["longitude_max"]) / 2.0, 6),
            },
        ],
    }


def build_large_manual_bbox_grid() -> dict[str, object]:
    columns = 12
    rows = 9
    lon_step = (BOUNDING_BOX["longitude_max"] - BOUNDING_BOX["longitude_min"]) / columns
    lat_step = (BOUNDING_BOX["latitude_max"] - BOUNDING_BOX["latitude_min"]) / rows
    cells: list[dict[str, object]] = []
    cell_index = 1
    for row_index in range(rows):
        lat_min = round(BOUNDING_BOX["latitude_min"] + lat_step * row_index, 6)
        lat_max = round(
            BOUNDING_BOX["latitude_max"] if row_index == rows - 1 else BOUNDING_BOX["latitude_min"] + lat_step * (row_index + 1),
            6,
        )
        for column_index in range(columns):
            lon_min = round(BOUNDING_BOX["longitude_min"] + lon_step * column_index, 6)
            lon_max = round(
                BOUNDING_BOX["longitude_max"] if column_index == columns - 1 else BOUNDING_BOX["longitude_min"] + lon_step * (column_index + 1),
                6,
            )
            cells.append(
                {
                    "grid_cell_index": cell_index,
                    "grid_cell_id": f"Manual bounds:R{row_index + 1}C{column_index + 1}",
                    "grid_row_index": row_index + 1,
                    "grid_column_index": column_index + 1,
                    "label": "Manual bounds",
                    "latitude_min": lat_min,
                    "latitude_max": lat_max,
                    "longitude_min": lon_min,
                    "longitude_max": lon_max,
                    "center_latitude": round((lat_min + lat_max) / 2.0, 6),
                    "center_longitude": round((lon_min + lon_max) / 2.0, 6),
                }
            )
            cell_index += 1
    return {
        "label": "Manual bounds",
        "grid_resolution_km": 5.0,
        "grid_cell_count": len(cells),
        "cells": cells,
    }


class HighPotentialSitesUseCaseTest(unittest.TestCase):
    def test_should_skip_running_preprocess_geojson_for_manual_grid_prediction_status(self) -> None:
        self.assertTrue(
            should_skip_running_preprocess_geojson(
                {
                    "selected_model_id": "20260607-211759",
                    "climate_scope": "regional_manual",
                    "selected_id_header": "Farm",
                }
            )
        )
        self.assertFalse(
            should_skip_running_preprocess_geojson(
                {
                    "selected_model_id": "20260607-211759",
                    "climate_scope": "regional_manual",
                    "selected_id_header": "",
                }
            )
        )
        self.assertFalse(
            should_skip_running_preprocess_geojson(
                {
                    "selected_model_id": "",
                    "climate_scope": "regional_manual",
                    "selected_id_header": "Farm",
                }
            )
        )

    def test_manual_bbox_prediction_with_farm_selected_id_writes_lightweight_map_geojson(self) -> None:
        self.assertTrue(TEST_WORKBOOK.exists(), "The AGG_2024_2025_V5.xlsx test workbook is required.")

        with tempfile.TemporaryDirectory(prefix="hps_farm_geojson_") as tmp_dir_name:
            tmp_dir = Path(tmp_dir_name)
            model_dir = tmp_dir / "model"
            model_dir.mkdir(parents=True, exist_ok=True)
            selection_summary = build_selection_summary()
            selection_summary_file = tmp_dir / "selection_summary.json"
            selection_summary_file.write_text(
                json.dumps(selection_summary, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            registered_model = SimpleNamespace(
                metadata={
                    "model_id": TEST_MODEL_ID,
                    "selection_summary": selection_summary,
                },
                model_dir=model_dir,
            )

            def fake_create_phase03_workbook(
                phase02_workbook: Path,
                _selection_summary_file: Path,
                output_workbook: Path,
                output_log_file: Path,
                **_: object,
            ) -> dict[str, object]:
                phase02_df = pd.read_excel(phase02_workbook, dtype=object)
                selected_phase02_rows = phase02_df[
                    phase02_df["Name"].astype(str).str.strip() == TEST_GERMPLASM
                ].copy()
                self.assertEqual(len(selected_phase02_rows.index), 1)
                selected_rows = pd.concat(
                    [selected_phase02_rows.copy(), selected_phase02_rows.copy()],
                    ignore_index=True,
                )

                manual_grid = build_manual_bbox_grid()
                for row_index, cell in enumerate(manual_grid["cells"]):
                    selected_rows.loc[selected_rows.index[row_index], "_GPS coordinates_latitude"] = cell["center_latitude"]
                    selected_rows.loc[selected_rows.index[row_index], "_GPS coordinates_longitude"] = cell["center_longitude"]
                    selected_rows.loc[selected_rows.index[row_index], "Forecast grid cell id"] = cell["grid_cell_id"]
                    selected_rows.loc[selected_rows.index[row_index], "Forecast grid cell index"] = cell["grid_cell_index"]
                    selected_rows.loc[selected_rows.index[row_index], "Farm"] = f"Farm {row_index + 1}"
                    selected_rows.loc[selected_rows.index[row_index], "Country"] = "Kenya"
                    selected_rows.loc[selected_rows.index[row_index], "Very Heavy Column"] = f"payload-{row_index}"

                output_workbook.parent.mkdir(parents=True, exist_ok=True)
                selected_rows.to_excel(output_workbook, index=False)

                phase03_log = {
                    "phase": "phase03",
                    "source_workbook": str(phase02_workbook),
                    "output_workbook": str(output_workbook),
                    "input_row_count": 1,
                    "output_row_count": 2,
                    "initial_settings": selection_summary["initial_settings"],
                    "divisions": selection_summary["divisions"],
                    "nasa": {
                        "phase": "phase02_climate_enriched",
                        "input_row_count": 1,
                        "phase02_source_row_count": 1,
                        "climate_input_row_count": 2,
                        "matched_rows": 2,
                        "unmatched_rows": 0,
                        "nasa_unique_queries": 0,
                        "manual_bbox_locality_count": 2,
                        "manual_bbox_grid_cell_count": 2,
                        "manual_bbox_grid": manual_grid,
                    },
                }
                output_log_file.write_text(
                    json.dumps(phase03_log, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                return phase03_log

            def fake_create_phase04_workbook(
                phase03_workbook: Path,
                _selection_summary_file: Path,
                output_workbook: Path,
                output_log_file: Path,
                **kwargs: object,
            ) -> dict[str, object]:
                self.assertTrue(kwargs.get("stream_traceability_workbook"))
                phase03_df = pd.read_excel(phase03_workbook, dtype=object)
                output_workbook.parent.mkdir(parents=True, exist_ok=True)
                phase03_df.to_excel(output_workbook, index=False)
                training_input_csv = output_workbook.parent / "phase04prediction_training_input.csv"
                training_input_xlsx = output_workbook.parent / "phase04prediction_training_input.xlsx"
                pd.DataFrame([{"feature_a": 1.0}, {"feature_a": 2.0}]).to_csv(training_input_csv, index=False)
                pd.DataFrame([{"feature_a": 1.0}, {"feature_a": 2.0}]).to_excel(training_input_xlsx, index=False)
                output_log_file.write_text(
                    json.dumps({"phase": "phase04", "output_workbook": str(output_workbook)}, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                return {"phase": "phase04", "output_workbook": str(output_workbook)}

            def fake_run_ce_phase05(
                *,
                phase04_workbook: Path,
                training_input_csv: Path,
                run_dir: Path,
                source_name: str,
                target_column: str,
                selected_id_header: str = "",
                **_: object,
            ) -> CePhase05Outputs:
                phase04_df = pd.read_excel(phase04_workbook, dtype=object)
                model_dir_local = run_dir / "model"
                model_dir_local.mkdir(parents=True, exist_ok=True)

                prediction_df = phase04_df.copy()
                prediction_df[PREDICTION_PREDICTED_COLUMN] = [6.25, 7.5]
                prediction_df["Country"] = "Kenya"
                prediction_df["Farm"] = ["Farm 1", "Farm 2"]
                prediction_df["Very Heavy Column"] = ["payload-0", "payload-1"]

                model_input_csv = model_dir_local / "grain_yield_model_input.csv"
                raw_prediction_json = model_dir_local / "grain_yield_predictions.json"
                phase5_prediction_csv = model_dir_local / "phase5_with_predictions.csv"
                phase5_prediction_xlsx = model_dir_local / "phase5_with_predictions.xlsx"
                prediction_with_context_csv = model_dir_local / "prediction_with_context.csv"
                prediction_with_context_xlsx = model_dir_local / "prediction_with_context.xlsx"
                geojson_file = model_dir_local / "ce_phase05_with_predictions.geojson"

                pd.DataFrame([{"feature_a": 1.0}, {"feature_a": 2.0}]).to_csv(model_input_csv, index=False)
                raw_prediction_json.write_text(
                    json.dumps([6.25, 7.5], ensure_ascii=False),
                    encoding="utf-8",
                )
                prediction_df.to_csv(phase5_prediction_csv, index=False)
                prediction_df.to_excel(phase5_prediction_xlsx, index=False)
                prediction_df.to_csv(prediction_with_context_csv, index=False)
                prediction_df.to_excel(prediction_with_context_xlsx, index=False)
                geojson = dataframe_to_geojson(prediction_df, geojson_file)

                summary = {
                    "workflow": "ce_pipeline_prediction",
                    "source_name": source_name,
                    "target_column": target_column,
                    "phase04_training_csv": str(training_input_csv),
                    "prediction_csv": str(prediction_with_context_csv),
                    "prediction_xlsx": str(prediction_with_context_xlsx),
                    "prediction_model_raw_csv": str(phase5_prediction_csv),
                    "prediction_model_raw_xlsx": str(phase5_prediction_xlsx),
                    "prediction_model_name": "Extreme Gradient Boosting",
                    "prediction_model_id": TEST_MODEL_ID,
                    "prediction_model_created_at": "2026-07-07T00:00:00",
                    "prediction_model_display_name": "AGG Test Model",
                    "prediction_model_description": "Mocked saved-model prediction for High-Potential Sites.",
                    "prediction_model_metric_name": "mean_absolute_error",
                    "prediction_model_metric_value": 0.5,
                    "selected_model_id": TEST_MODEL_ID,
                    "selected_id_header": selected_id_header,
                    "geojson_file": str(geojson_file),
                    "total_features": len(prediction_df.index),
                }
                summary_file = run_dir / "summary.json"
                summary_file.write_text(
                    json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                return CePhase05Outputs(
                    summary=summary,
                    geojson=geojson,
                    summary_file=summary_file,
                    geojson_file=geojson_file,
                )

            with patch(
                "cimmyt_app.ce_pipeline.prediction.prediction.get_registered_model",
                return_value=registered_model,
            ), patch(
                "cimmyt_app.ce_pipeline.prediction.prediction._resolve_saved_model",
                return_value=(registered_model, selection_summary, selection_summary_file),
            ), patch(
                "cimmyt_app.ce_pipeline.prediction.prediction._read_saved_normalization_stats",
                return_value={},
            ), patch(
                "cimmyt_app.ce_pipeline.prediction.prediction.create_phase03_workbook",
                side_effect=fake_create_phase03_workbook,
            ), patch(
                "cimmyt_app.ce_pipeline.prediction.prediction.create_phase04_workbook",
                side_effect=fake_create_phase04_workbook,
            ), patch(
                "cimmyt_app.ce_pipeline.prediction.prediction.run_ce_phase05",
                side_effect=fake_run_ce_phase05,
            ):
                outputs = run_ce_saved_model_prediction(
                    TEST_WORKBOOK,
                    tmp_dir / "runtime_farm",
                    selected_model_id=TEST_MODEL_ID,
                    forecast_planting_date="",
                    forecast_harvesting_date="",
                    selected_germplasm_names=[TEST_GERMPLASM],
                    selected_germplasm_row_ids=[],
                    selected_germplasm_selection_mode="all_matches",
                    regional_bounds_label="Manual bounds",
                    regional_bounds_latitude_min=BOUNDING_BOX["latitude_min"],
                    regional_bounds_latitude_max=BOUNDING_BOX["latitude_max"],
                    regional_bounds_longitude_min=BOUNDING_BOX["longitude_min"],
                    regional_bounds_longitude_max=BOUNDING_BOX["longitude_max"],
                    nasa_grid_resolution_km=5,
                    use_source_row_dates=True,
                    selected_id_header="Farm",
                )

            lightweight_geojson = json.loads(outputs.geojson_file.read_text(encoding="utf-8"))
            first_properties = lightweight_geojson["features"][0]["properties"]
            self.assertIn("Farm", first_properties)
            self.assertIn("Forecast grid cell id", first_properties)
            self.assertIn(PREDICTION_PREDICTED_COLUMN, first_properties)
            self.assertNotIn("Very Heavy Column", first_properties)

    def test_single_germplasm_manual_bbox_prediction_builds_ui_ready_numeric_map(self) -> None:
        self.assertTrue(TEST_WORKBOOK.exists(), "The AGG_2024_2025_V5.xlsx test workbook is required.")

        with tempfile.TemporaryDirectory(prefix="hps_use_case_") as tmp_dir_name:
            tmp_dir = Path(tmp_dir_name)
            model_dir = tmp_dir / "model"
            model_dir.mkdir(parents=True, exist_ok=True)
            selection_summary = build_selection_summary()
            selection_summary_file = tmp_dir / "selection_summary.json"
            selection_summary_file.write_text(
                json.dumps(selection_summary, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            registered_model = SimpleNamespace(
                metadata={
                    "model_id": TEST_MODEL_ID,
                    "selection_summary": selection_summary,
                },
                model_dir=model_dir,
            )

            def fake_create_phase03_workbook(
                phase02_workbook: Path,
                _selection_summary_file: Path,
                output_workbook: Path,
                output_log_file: Path,
                **_: object,
            ) -> dict[str, object]:
                phase02_df = pd.read_excel(phase02_workbook, dtype=object)
                selected_phase02_rows = phase02_df[
                    phase02_df["Name"].astype(str).str.strip() == TEST_GERMPLASM
                ].copy()
                self.assertEqual(len(selected_phase02_rows.index), 1)
                selected_rows = pd.concat(
                    [selected_phase02_rows.copy(), selected_phase02_rows.copy()],
                    ignore_index=True,
                )

                manual_grid = build_manual_bbox_grid()
                first_cell, second_cell = manual_grid["cells"]
                selected_rows.loc[selected_rows.index[0], "_GPS coordinates_latitude"] = first_cell["center_latitude"]
                selected_rows.loc[selected_rows.index[0], "_GPS coordinates_longitude"] = first_cell["center_longitude"]
                selected_rows.loc[selected_rows.index[0], "Forecast grid cell id"] = first_cell["grid_cell_id"]
                selected_rows.loc[selected_rows.index[0], "Forecast grid cell index"] = first_cell["grid_cell_index"]
                selected_rows.loc[selected_rows.index[0], "Country"] = "Kenya"

                selected_rows.loc[selected_rows.index[1], "_GPS coordinates_latitude"] = second_cell["center_latitude"]
                selected_rows.loc[selected_rows.index[1], "_GPS coordinates_longitude"] = second_cell["center_longitude"]
                selected_rows.loc[selected_rows.index[1], "Forecast grid cell id"] = second_cell["grid_cell_id"]
                selected_rows.loc[selected_rows.index[1], "Forecast grid cell index"] = second_cell["grid_cell_index"]
                selected_rows.loc[selected_rows.index[1], "Country"] = "Kenya"

                output_workbook.parent.mkdir(parents=True, exist_ok=True)
                selected_rows.to_excel(output_workbook, index=False)

                phase03_log = {
                    "phase": "phase03",
                    "source_workbook": str(phase02_workbook),
                    "output_workbook": str(output_workbook),
                    "input_row_count": 2,
                    "output_row_count": 2,
                    "initial_settings": selection_summary["initial_settings"],
                    "divisions": selection_summary["divisions"],
                    "nasa": {
                        "phase": "phase02_climate_enriched",
                        "input_row_count": 2,
                        "phase02_source_row_count": 87,
                        "climate_input_row_count": 2,
                        "matched_rows": 2,
                        "unmatched_rows": 0,
                        "nasa_unique_queries": 0,
                        "manual_bbox_locality_count": 2,
                        "manual_bbox_grid_cell_count": 2,
                        "manual_bbox_grid": manual_grid,
                    },
                }
                output_log_file.write_text(
                    json.dumps(phase03_log, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                return phase03_log

            def fake_create_phase04_workbook(
                phase03_workbook: Path,
                _selection_summary_file: Path,
                output_workbook: Path,
                output_log_file: Path,
                **kwargs: object,
            ) -> dict[str, object]:
                self.assertTrue(kwargs.get("stream_traceability_workbook"))
                phase03_df = pd.read_excel(phase03_workbook, dtype=object)
                output_workbook.parent.mkdir(parents=True, exist_ok=True)
                phase03_df.to_excel(output_workbook, index=False)
                training_input_csv = output_workbook.parent / "phase04prediction_training_input.csv"
                training_input_xlsx = output_workbook.parent / "phase04prediction_training_input.xlsx"
                pd.DataFrame([{"feature_a": 1.0}, {"feature_a": 2.0}]).to_csv(training_input_csv, index=False)
                pd.DataFrame([{"feature_a": 1.0}, {"feature_a": 2.0}]).to_excel(training_input_xlsx, index=False)
                output_log_file.write_text(
                    json.dumps({"phase": "phase04", "output_workbook": str(output_workbook)}, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                return {"phase": "phase04", "output_workbook": str(output_workbook)}

            def fake_run_ce_phase05(
                *,
                phase04_workbook: Path,
                training_input_csv: Path,
                run_dir: Path,
                source_name: str,
                target_column: str,
                selected_id_header: str = "",
                **_: object,
            ) -> CePhase05Outputs:
                phase04_df = pd.read_excel(phase04_workbook, dtype=object)
                model_dir_local = run_dir / "model"
                model_dir_local.mkdir(parents=True, exist_ok=True)

                prediction_df = phase04_df.copy()
                prediction_df[PREDICTION_PREDICTED_COLUMN] = [6.25, 7.5]
                prediction_df["Country"] = "Kenya"

                model_input_csv = model_dir_local / "grain_yield_model_input.csv"
                raw_prediction_json = model_dir_local / "grain_yield_predictions.json"
                phase5_prediction_csv = model_dir_local / "phase5_with_predictions.csv"
                phase5_prediction_xlsx = model_dir_local / "phase5_with_predictions.xlsx"
                prediction_with_context_csv = model_dir_local / "prediction_with_context.csv"
                prediction_with_context_xlsx = model_dir_local / "prediction_with_context.xlsx"
                geojson_file = model_dir_local / "ce_phase05_with_predictions.geojson"

                pd.DataFrame([{"feature_a": 1.0}, {"feature_a": 2.0}]).to_csv(model_input_csv, index=False)
                raw_prediction_json.write_text(
                    json.dumps([6.25, 7.5], ensure_ascii=False),
                    encoding="utf-8",
                )
                prediction_df.to_csv(phase5_prediction_csv, index=False)
                prediction_df.to_excel(phase5_prediction_xlsx, index=False)
                prediction_df.to_csv(prediction_with_context_csv, index=False)
                prediction_df.to_excel(prediction_with_context_xlsx, index=False)
                geojson = dataframe_to_geojson(prediction_df, geojson_file)

                summary = {
                    "workflow": "ce_pipeline_prediction",
                    "source_name": source_name,
                    "target_column": target_column,
                    "phase04_training_csv": str(training_input_csv),
                    "prediction_csv": str(prediction_with_context_csv),
                    "prediction_xlsx": str(prediction_with_context_xlsx),
                    "prediction_model_raw_csv": str(phase5_prediction_csv),
                    "prediction_model_raw_xlsx": str(phase5_prediction_xlsx),
                    "prediction_model_name": "Extreme Gradient Boosting",
                    "prediction_model_id": TEST_MODEL_ID,
                    "prediction_model_created_at": "2026-07-07T00:00:00",
                    "prediction_model_display_name": "AGG Test Model",
                    "prediction_model_description": "Mocked saved-model prediction for High-Potential Sites.",
                    "prediction_model_metric_name": "mean_absolute_error",
                    "prediction_model_metric_value": 0.5,
                    "selected_model_id": TEST_MODEL_ID,
                    "selected_id_header": selected_id_header,
                    "geojson_file": str(geojson_file),
                    "total_features": len(prediction_df.index),
                }
                summary_file = run_dir / "summary.json"
                summary_file.write_text(
                    json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                return CePhase05Outputs(
                    summary=summary,
                    geojson=geojson,
                    summary_file=summary_file,
                    geojson_file=geojson_file,
                )

            with patch(
                "cimmyt_app.ce_pipeline.prediction.prediction.get_registered_model",
                return_value=registered_model,
            ), patch(
                "cimmyt_app.ce_pipeline.prediction.prediction._resolve_saved_model",
                return_value=(registered_model, selection_summary, selection_summary_file),
            ), patch(
                "cimmyt_app.ce_pipeline.prediction.prediction._read_saved_normalization_stats",
                return_value={},
            ), patch(
                "cimmyt_app.ce_pipeline.prediction.prediction.create_phase03_workbook",
                side_effect=fake_create_phase03_workbook,
            ), patch(
                "cimmyt_app.ce_pipeline.prediction.prediction.create_phase04_workbook",
                side_effect=fake_create_phase04_workbook,
            ), patch(
                "cimmyt_app.ce_pipeline.prediction.prediction.run_ce_phase05",
                side_effect=fake_run_ce_phase05,
            ):
                outputs = run_ce_saved_model_prediction(
                    TEST_WORKBOOK,
                    tmp_dir / "runtime",
                    selected_model_id=TEST_MODEL_ID,
                    forecast_planting_date="",
                    forecast_harvesting_date="",
                    selected_germplasm_names=[TEST_GERMPLASM],
                    selected_germplasm_row_ids=[],
                    selected_germplasm_selection_mode="all_matches",
                    regional_bounds_label="Manual bounds",
                    regional_bounds_latitude_min=BOUNDING_BOX["latitude_min"],
                    regional_bounds_latitude_max=BOUNDING_BOX["latitude_max"],
                    regional_bounds_longitude_min=BOUNDING_BOX["longitude_min"],
                    regional_bounds_longitude_max=BOUNDING_BOX["longitude_max"],
                    nasa_grid_resolution_km=5,
                    use_source_row_dates=True,
                    selected_id_header="",
                )

            summary = outputs.summary
            self.assertEqual(summary["workflow"], "ce_saved_model_prediction")
            self.assertEqual(summary["selected_germplasm_names"], [TEST_GERMPLASM])
            self.assertEqual(summary["selected_id_header"], "")
            self.assertEqual(summary["climate_scope"], "regional_manual")
            self.assertFalse(summary["multi_profile_mode"])
            self.assertEqual(summary["manual_bbox_grid"]["grid_cell_count"], 2)
            self.assertEqual(summary["manual_bbox_grid"]["cells"][0]["latitude_min"], BOUNDING_BOX["latitude_min"])
            self.assertEqual(summary["manual_bbox_grid"]["cells"][1]["longitude_max"], BOUNDING_BOX["longitude_max"])

            phase02_log_path = Path(summary["phase02prediction_xlsx"]).with_name("phase02prediction_log.json")
            phase02_log = json.loads(phase02_log_path.read_text(encoding="utf-8"))
            self.assertEqual(phase02_log["output_row_count"], 1)
            self.assertFalse(phase02_log["prediction_profile_analysis"]["multi_profile_mode"])
            self.assertEqual(phase02_log["prediction_profile_analysis"]["profile_count"], 1)

            display_geojson = build_prediction_display_feature_collection(summary)
            self.assertEqual(display_geojson["type"], "FeatureCollection")
            self.assertEqual(len(display_geojson["features"]), 2)
            display_values = sorted(
                float(feature["properties"][PREDICTION_PREDICTED_COLUMN])
                for feature in display_geojson["features"]
            )
            self.assertEqual(display_values, [6.25, 7.5])

            overlay_payload = _build_manual_grid_profile_overlay_payload(summary, [TEST_GERMPLASM])
            self.assertEqual(overlay_payload["labels"], [TEST_GERMPLASM])
            self.assertEqual(len(overlay_payload["heat_samples"]), 2)
            self.assertEqual(
                sorted({str(sample["profileLabel"]).strip() for sample in overlay_payload["heat_samples"]}),
                [TEST_GERMPLASM],
            )

    def test_single_germplasm_with_ten_reps_builds_averaged_numeric_manual_grid_map(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hps_reps_use_case_") as tmp_dir_name:
            tmp_dir = Path(tmp_dir_name)
            model_dir = tmp_dir / "model"
            model_dir.mkdir(parents=True, exist_ok=True)
            selection_summary = build_selection_summary()
            selection_summary_file = tmp_dir / "selection_summary.json"
            selection_summary_file.write_text(
                json.dumps(selection_summary, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            registered_model = SimpleNamespace(
                metadata={
                    "model_id": TEST_MODEL_ID,
                    "selection_summary": selection_summary,
                },
                model_dir=model_dir,
            )

            def fake_create_phase03_workbook(
                phase02_workbook: Path,
                _selection_summary_file: Path,
                output_workbook: Path,
                output_log_file: Path,
                **_: object,
            ) -> dict[str, object]:
                phase02_df = pd.read_excel(phase02_workbook, dtype=object)
                selected_phase02_rows = phase02_df[
                    phase02_df["Name"].astype(str).str.strip() == "CIM-RT-EAPP1-E -001"
                ].copy()
                self.assertEqual(len(selected_phase02_rows.index), 10)

                manual_grid = build_large_manual_bbox_grid()
                expanded_rows: list[dict[str, object]] = []
                for cell in manual_grid["cells"]:
                    for rep_index, (_, row) in enumerate(selected_phase02_rows.iterrows(), start=1):
                        record = dict(row)
                        record["_GPS coordinates_latitude"] = cell["center_latitude"]
                        record["_GPS coordinates_longitude"] = cell["center_longitude"]
                        record["Forecast grid cell id"] = cell["grid_cell_id"]
                        record["Forecast grid cell index"] = cell["grid_cell_index"]
                        record["Country"] = "Kenya"
                        record["Synthetic Rep Index"] = rep_index
                        expanded_rows.append(record)
                phase03_df = pd.DataFrame(expanded_rows)
                output_workbook.parent.mkdir(parents=True, exist_ok=True)
                phase03_df.to_excel(output_workbook, index=False)

                phase03_log = {
                    "phase": "phase03",
                    "source_workbook": str(phase02_workbook),
                    "output_workbook": str(output_workbook),
                    "input_row_count": 10,
                    "output_row_count": len(phase03_df.index),
                    "initial_settings": selection_summary["initial_settings"],
                    "divisions": selection_summary["divisions"],
                    "nasa": {
                        "phase": "phase02_climate_enriched",
                        "input_row_count": 10,
                        "phase02_source_row_count": 1080,
                        "climate_input_row_count": 1080,
                        "matched_rows": 1080,
                        "unmatched_rows": 0,
                        "nasa_unique_queries": 0,
                        "manual_bbox_locality_count": 108,
                        "manual_bbox_grid_cell_count": 108,
                        "manual_bbox_grid": manual_grid,
                    },
                }
                output_log_file.write_text(
                    json.dumps(phase03_log, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                return phase03_log

            def fake_create_phase04_workbook(
                phase03_workbook: Path,
                _selection_summary_file: Path,
                output_workbook: Path,
                output_log_file: Path,
                **_: object,
            ) -> dict[str, object]:
                phase03_df = pd.read_excel(phase03_workbook, dtype=object)
                output_workbook.parent.mkdir(parents=True, exist_ok=True)
                phase03_df.to_excel(output_workbook, index=False)
                training_input_csv = output_workbook.parent / "phase04prediction_training_input.csv"
                training_input_xlsx = output_workbook.parent / "phase04prediction_training_input.xlsx"
                pd.DataFrame([{"feature_a": float(index)} for index in range(1, 1081)]).to_csv(training_input_csv, index=False)
                pd.DataFrame([{"feature_a": float(index)} for index in range(1, 1081)]).to_excel(training_input_xlsx, index=False)
                output_log_file.write_text(
                    json.dumps({"phase": "phase04", "output_workbook": str(output_workbook)}, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                return {"phase": "phase04", "output_workbook": str(output_workbook)}

            def fake_run_ce_phase05(
                *,
                phase04_workbook: Path,
                training_input_csv: Path,
                run_dir: Path,
                source_name: str,
                target_column: str,
                selected_id_header: str = "",
                **_: object,
            ) -> CePhase05Outputs:
                phase04_df = pd.read_excel(phase04_workbook, dtype=object)
                model_dir_local = run_dir / "model"
                model_dir_local.mkdir(parents=True, exist_ok=True)

                prediction_df = phase04_df.copy()
                predicted_values: list[float] = []
                for _, row in prediction_df.iterrows():
                    cell_index = int(row["Forecast grid cell index"])
                    rep_index = int(row["Synthetic Rep Index"])
                    predicted_values.append(round(1.6 + cell_index * 0.01 + rep_index * 0.001, 6))
                prediction_df[PREDICTION_PREDICTED_COLUMN] = predicted_values
                prediction_df["Country"] = "Kenya"

                model_input_csv = model_dir_local / "grain_yield_model_input.csv"
                raw_prediction_json = model_dir_local / "grain_yield_predictions.json"
                phase5_prediction_csv = model_dir_local / "phase5_with_predictions.csv"
                phase5_prediction_xlsx = model_dir_local / "phase5_with_predictions.xlsx"
                prediction_with_context_csv = model_dir_local / "prediction_with_context.csv"
                prediction_with_context_xlsx = model_dir_local / "prediction_with_context.xlsx"
                geojson_file = model_dir_local / "ce_phase05_with_predictions.geojson"

                pd.DataFrame([{"feature_a": float(index)} for index in range(1, len(prediction_df.index) + 1)]).to_csv(model_input_csv, index=False)
                raw_prediction_json.write_text(json.dumps(predicted_values, ensure_ascii=False), encoding="utf-8")
                prediction_df.to_csv(phase5_prediction_csv, index=False)
                prediction_df.to_excel(phase5_prediction_xlsx, index=False)
                prediction_df.to_csv(prediction_with_context_csv, index=False)
                prediction_df.to_excel(prediction_with_context_xlsx, index=False)
                geojson = dataframe_to_geojson(prediction_df, geojson_file)

                summary = {
                    "workflow": "ce_pipeline_prediction",
                    "source_name": source_name,
                    "target_column": target_column,
                    "phase04_training_csv": str(training_input_csv),
                    "prediction_csv": str(prediction_with_context_csv),
                    "prediction_xlsx": str(prediction_with_context_xlsx),
                    "prediction_model_raw_csv": str(phase5_prediction_csv),
                    "prediction_model_raw_xlsx": str(phase5_prediction_xlsx),
                    "prediction_model_name": "Extreme Gradient Boosting",
                    "prediction_model_id": TEST_MODEL_ID,
                    "prediction_model_created_at": "2026-07-07T00:00:00",
                    "prediction_model_display_name": "AGG Test Model",
                    "prediction_model_description": "Mocked saved-model prediction for repeated single-germplasm High-Potential Sites.",
                    "prediction_model_metric_name": "mean_absolute_error",
                    "prediction_model_metric_value": 0.5,
                    "selected_model_id": TEST_MODEL_ID,
                    "selected_id_header": selected_id_header,
                    "geojson_file": str(geojson_file),
                    "total_features": len(prediction_df.index),
                }
                summary_file = run_dir / "summary.json"
                summary_file.write_text(
                    json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                return CePhase05Outputs(
                    summary=summary,
                    geojson=geojson,
                    summary_file=summary_file,
                    geojson_file=geojson_file,
                )

            with patch(
                "cimmyt_app.ce_pipeline.prediction.prediction.get_registered_model",
                return_value=registered_model,
            ), patch(
                "cimmyt_app.ce_pipeline.prediction.prediction._resolve_saved_model",
                return_value=(registered_model, selection_summary, selection_summary_file),
            ), patch(
                "cimmyt_app.ce_pipeline.prediction.prediction._read_saved_normalization_stats",
                return_value={},
            ), patch(
                "cimmyt_app.ce_pipeline.prediction.prediction.create_phase03_workbook",
                side_effect=fake_create_phase03_workbook,
            ), patch(
                "cimmyt_app.ce_pipeline.prediction.prediction.create_phase04_workbook",
                side_effect=fake_create_phase04_workbook,
            ), patch(
                "cimmyt_app.ce_pipeline.prediction.prediction.run_ce_phase05",
                side_effect=fake_run_ce_phase05,
            ):
                outputs = run_ce_saved_model_prediction(
                    TEST_WORKBOOK,
                    tmp_dir / "runtime_reps",
                    selected_model_id=TEST_MODEL_ID,
                    forecast_planting_date="",
                    forecast_harvesting_date="",
                    selected_germplasm_names=["CIM-RT-EAPP1-E -001"],
                    selected_germplasm_row_ids=[],
                    selected_germplasm_selection_mode="all_matches",
                    regional_bounds_label="Manual bounds",
                    regional_bounds_latitude_min=BOUNDING_BOX["latitude_min"],
                    regional_bounds_latitude_max=BOUNDING_BOX["latitude_max"],
                    regional_bounds_longitude_min=BOUNDING_BOX["longitude_min"],
                    regional_bounds_longitude_max=BOUNDING_BOX["longitude_max"],
                    nasa_grid_resolution_km=5,
                    use_source_row_dates=True,
                    selected_id_header="",
                )

            summary = outputs.summary
            self.assertEqual(summary["selected_germplasm_names"], ["CIM-RT-EAPP1-E -001"])
            self.assertEqual(summary["selected_id_header"], "")
            self.assertEqual(summary["prediction_feature_count"], 1080)
            self.assertEqual(summary["manual_bbox_grid"]["grid_cell_count"], 108)
            self.assertFalse(summary["multi_profile_mode"])

            phase02_log_path = Path(summary["phase02prediction_xlsx"]).with_name("phase02prediction_log.json")
            phase02_log = json.loads(phase02_log_path.read_text(encoding="utf-8"))
            self.assertEqual(phase02_log["output_row_count"], 10)
            self.assertFalse(phase02_log["prediction_profile_analysis"]["multi_profile_mode"])
            self.assertEqual(phase02_log["prediction_profile_analysis"]["profile_count"], 1)

            display_geojson = build_prediction_display_feature_collection(summary)
            self.assertEqual(len(display_geojson["features"]), 108)
            self.assertEqual(
                sorted({str(feature["properties"].get("Name") or "").strip() for feature in display_geojson["features"]}),
                ["CIM-RT-EAPP1-E -001"],
            )
            display_values = sorted(
                float(feature["properties"][PREDICTION_PREDICTED_COLUMN])
                for feature in display_geojson["features"]
            )
            self.assertAlmostEqual(display_values[0], 1.6155, places=6)
            self.assertAlmostEqual(display_values[-1], 2.6855, places=6)

            overlay_payload = _build_manual_grid_profile_overlay_payload(summary, ["CIM-RT-EAPP1-E -001"])
            self.assertEqual(overlay_payload["labels"], ["CIM-RT-EAPP1-E -001"])
            self.assertEqual(len(overlay_payload["heat_samples"]), 108)


if __name__ == "__main__":
    unittest.main()
