from __future__ import annotations

import unittest
from pathlib import Path

import pandas as pd

from pipeline.common import GERMPLASM_COLUMNS
from pipeline.model.grain_yield_model import (
    build_model_input,
    read_model_feature_names,
    read_selected_feature_names,
    resolve_active_model,
    resolve_prediction_feature_names,
)


ROOT_DIR = Path(__file__).resolve().parents[2]
LEGACY_WORKSPACE = (
    ROOT_DIR
    / "EA_merged"
    / "phases"
    / "phase_analysis"
    / "Grain_Yield_T_Ha"
    / "work_space_featurehero"
    / "20260408_190836"
)


class ModelInputSelectionTest(unittest.TestCase):
    def test_best_features_mask_maps_to_sort_original_columns(self) -> None:
        best_features_file = LEGACY_WORKSPACE / "best_features_sort_original.pkl"
        sort_original_file = LEGACY_WORKSPACE / "sort_original.csv"

        feature_names = read_selected_feature_names(best_features_file, sort_original_file)

        self.assertTrue(feature_names, "The selected feature list should not be empty.")
        self.assertEqual(len(feature_names), 29)
        self.assertIn("Weed control practices_Chemical", feature_names)
        self.assertIn("harvest_back_week_8_total_prectotcorr (mm)", feature_names)
        self.assertNotIn("Grain Yield (T/Ha)", feature_names)

    def test_prediction_prefers_features_embedded_in_model(self) -> None:
        model_file = LEGACY_WORKSPACE / "best_model_sort_original.pkl"
        best_features_file = LEGACY_WORKSPACE / "best_features_sort_original.pkl"
        sort_original_file = LEGACY_WORKSPACE / "sort_original.csv"

        feature_names = resolve_prediction_feature_names(
            model_file,
            best_features_file,
            sort_original_file,
        )
        embedded_feature_names = read_model_feature_names(model_file)

        self.assertEqual(feature_names, embedded_feature_names)
        self.assertTrue(feature_names)
        self.assertEqual(len(feature_names), len(embedded_feature_names))
        self.assertIn("Weed control practices_Chemical", feature_names)
        self.assertNotIn("Grain Yield (T/Ha)", feature_names)

    def test_active_model_can_resolve_feature_selection_artifacts(self) -> None:
        resolved_model = resolve_active_model()

        self.assertTrue(resolved_model.model_file.exists())
        self.assertTrue(resolved_model.best_features_file.exists())
        self.assertTrue(resolved_model.sort_original_file.exists())

    def test_build_model_input_drops_germplasm_columns(self) -> None:
        feature_names = ["feature_a", "feature_b"]
        row = {column: f"value-{index}" for index, column in enumerate(GERMPLASM_COLUMNS, start=1)}
        row.update(
            {
                "Country": "Kenya",
                "_GPS coordinates_latitude": 1.23,
                "_GPS coordinates_longitude": 36.8,
                "Grain Yield (T/Ha)": 4.5,
                "feature_a": 10,
                "feature_b": 20,
            }
        )
        df = pd.DataFrame([row])

        model_df = build_model_input(df, feature_names)

        self.assertEqual(list(model_df.columns), feature_names)
        self.assertEqual(model_df.iloc[0]["feature_a"], 10)
        self.assertEqual(model_df.iloc[0]["feature_b"], 20)
