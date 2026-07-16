from __future__ import annotations

import csv
import hashlib
import json
import unittest
from pathlib import Path


BASELINE_MODEL_ID = "20260607-211759"
EXPECTED_TRAINING_INPUT_SHA256 = "6b1a97326f5d97bf6c310dc8ff46629588ba028a9c89cd5b3c473fc2e51c7b3b"
EXPECTED_ROW_COUNT = 1658
EXPECTED_CLIMATE_COLUMN_COUNT = 21
EXPECTED_FIRST_ROW_NORMALIZED_CLIMATE = {
    "planting_week_1_total_prectotcorr (mm)": "-1.34584713934811",
    "planting_week_2_total_prectotcorr (mm)": "0.06530004212159961",
    "planting_week_2_avg_t2m (C)": "0.7754974323315461",
    "intermediate_period_total_prectotcorr (mm)": "-0.49005073245138614",
    "intermediate_period_avg_t2m (C)": "0.7090970329958206",
}
EXPECTED_FIRST_ROW_RAW_CLIMATE = {
    "planting_week_1_total_prectotcorr (mm)": 24.6325,
    "planting_week_2_total_prectotcorr (mm)": 77.8974,
    "planting_week_2_avg_t2m (C)": 26.5812,
    "intermediate_period_total_prectotcorr (mm)": 34.7621,
    "intermediate_period_avg_t2m (C)": 25.7669,
}
EXPECTED_NORMALIZATION_STATS = {
    "planting_week_1_total_prectotcorr (mm)": {"apply_log": True, "mean": 4.134655510899812, "std": 0.6914520783809593},
    "planting_week_2_total_prectotcorr (mm)": {"apply_log": True, "mean": 4.3180408889220825, "std": 0.7673407803975953},
    "intermediate_period_avg_t2m (C)": {"apply_log": False, "mean": 24.376869486404832, "std": 1.9602825127084693},
}


class TrainingClimateBaselineRegressionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        cls.model_dir = repo_root / 'pipeline' / 'model' / BASELINE_MODEL_ID
        cls.training_input_csv = cls.model_dir / 'phase04_training_input.csv'
        cls.original_geojson = cls.model_dir / 'workspace_original_geojson.json'
        cls.training_geojson = cls.model_dir / 'workspace_training_geojson.json'
        cls.normalization_stats_file = cls.model_dir / 'phase04_normalization_stats.json'

    def test_baseline_artifacts_exist(self) -> None:
        self.assertTrue(self.model_dir.is_dir())
        self.assertTrue(self.training_input_csv.is_file())
        self.assertTrue(self.original_geojson.is_file())
        self.assertTrue(self.training_geojson.is_file())
        self.assertTrue(self.normalization_stats_file.is_file())

    def test_training_input_csv_matches_saved_baseline_signature(self) -> None:
        digest = hashlib.sha256(self.training_input_csv.read_bytes()).hexdigest()
        self.assertEqual(digest, EXPECTED_TRAINING_INPUT_SHA256)

    def test_training_input_preserves_expected_climate_columns_and_values(self) -> None:
        with self.training_input_csv.open(newline='', encoding='utf-8') as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)

        self.assertEqual(len(rows), EXPECTED_ROW_COUNT)
        first_row = rows[0]
        climate_columns = [
            header for header in reader.fieldnames or []
            if 'planting_week_' in header or 'intermediate_period_' in header or 'harvest_back_week_' in header
        ]
        self.assertEqual(len(climate_columns), EXPECTED_CLIMATE_COLUMN_COUNT)
        for column, expected_value in EXPECTED_FIRST_ROW_NORMALIZED_CLIMATE.items():
            self.assertEqual(first_row[column], expected_value)

    def test_raw_workspace_geojson_keeps_pre_normalized_climate_values(self) -> None:
        original_payload = json.loads(self.original_geojson.read_text(encoding='utf-8'))
        training_payload = json.loads(self.training_geojson.read_text(encoding='utf-8'))

        original_features = original_payload.get('features', [])
        training_features = training_payload.get('features', [])
        self.assertEqual(len(original_features), EXPECTED_ROW_COUNT)
        self.assertEqual(len(training_features), EXPECTED_ROW_COUNT)

        original_properties = original_features[0].get('properties', {})
        training_properties = training_features[0].get('properties', {})
        for column, expected_value in EXPECTED_FIRST_ROW_RAW_CLIMATE.items():
            self.assertAlmostEqual(float(original_properties[column]), expected_value, places=4)
            self.assertNotEqual(original_properties[column], training_properties[column])

    def test_normalization_stats_for_climate_training_columns_match_baseline(self) -> None:
        payload = json.loads(self.normalization_stats_file.read_text(encoding='utf-8'))
        for column, expected in EXPECTED_NORMALIZATION_STATS.items():
            self.assertIn(column, payload)
            self.assertEqual(bool(payload[column].get('apply_log')), expected['apply_log'])
            self.assertAlmostEqual(float(payload[column].get('mean')), expected['mean'])
            self.assertAlmostEqual(float(payload[column].get('std')), expected['std'])


if __name__ == '__main__':
    unittest.main()
