from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from server import (
    build_completed_summary_for_ui,
    resolve_ce_training_results_download_path,
    should_inline_completed_geojson,
)


class ServerTrainingDownloadTest(unittest.TestCase):
    def test_build_completed_summary_for_ui_strips_heavy_prediction_fields(self) -> None:
        summary = {
            "prediction_model_name": "EA_GG_2024_2025",
            "prediction_feature_count": 2322,
            "manual_bbox_grid": {"cells": [{"grid_cell_id": "A1"}]},
            "preprocess_log": {"climate": {"rows": 123}},
        }

        compact = build_completed_summary_for_ui(summary)

        self.assertEqual(compact["prediction_model_name"], "EA_GG_2024_2025")
        self.assertEqual(compact["prediction_feature_count"], 2322)
        self.assertNotIn("manual_bbox_grid", compact)
        self.assertNotIn("preprocess_log", compact)

    def test_should_inline_completed_geojson_skips_large_regional_manual_runs(self) -> None:
        self.assertFalse(
            should_inline_completed_geojson(
                {
                    "climate_scope": "regional_manual",
                    "prediction_feature_count": 2322,
                }
            )
        )
        self.assertTrue(
            should_inline_completed_geojson(
                {
                    "climate_scope": "point",
                    "prediction_feature_count": 25,
                }
            )
        )

    def test_resolve_ce_training_results_download_path_prefers_training_summary(self) -> None:
        with tempfile.TemporaryDirectory(prefix="training_download_") as temp_dir:
            run_dir = Path(temp_dir)
            training_dir = run_dir / "ce_pipeline" / "training"
            training_dir.mkdir(parents=True, exist_ok=True)
            workbook = training_dir / "ce_phase05_with_predictions.xlsx"
            workbook.write_bytes(b"test")
            (training_dir / "summary.json").write_text(
                json.dumps({"prediction_xlsx": str(workbook)}),
                encoding="utf-8",
            )

            resolved = resolve_ce_training_results_download_path(run_dir)

            self.assertEqual(resolved, workbook)

    def test_resolve_ce_training_results_download_path_falls_back_to_result_payload(self) -> None:
        with tempfile.TemporaryDirectory(prefix="training_download_") as temp_dir:
            run_dir = Path(temp_dir)
            fallback_dir = run_dir / "ce_pipeline" / "phase05" / "model"
            fallback_dir.mkdir(parents=True, exist_ok=True)
            workbook = fallback_dir / "ce_phase05_with_predictions.xlsx"
            workbook.write_bytes(b"test")
            (run_dir / "ce_summary_result.json").write_text(
                json.dumps({"training_summary": {"prediction_xlsx": str(workbook)}}),
                encoding="utf-8",
            )

            resolved = resolve_ce_training_results_download_path(run_dir)

            self.assertEqual(resolved, workbook)


if __name__ == "__main__":
    unittest.main()
