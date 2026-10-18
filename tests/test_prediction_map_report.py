import csv
import io
import json
import tempfile
import unittest
from pathlib import Path

from server import (
    _build_manual_grid_prediction_workbook_bytes,
    _build_manual_grid_profile_overlay_payload,
    build_prediction_display_feature_collection,
)


class PredictionMapReportTest(unittest.TestCase):
    def test_report_matches_cell_winners_for_each_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "raw.geojson"
            cells = [dict(grid_cell_id=str(i), center_longitude=i, center_latitude=0,
                          longitude_min=i-.1, longitude_max=i+.1, latitude_min=-.1, latitude_max=.1)
                     for i in (1, 2)]
            features = []
            # A wins cell 1 by its highest repetition, B wins cell 2.
            for cell, name, values in [(1, "A", [1, 6]), (1, "B", [4, 5]),
                                       (2, "A", [1, 2]), (2, "B", [3, 4])]:
                for value in values:
                    features.append(dict(type="Feature", geometry=dict(type="Point", coordinates=[cell, 0]),
                                         properties={"Name": name, "Forecast grid cell id": str(cell),
                                                     "Grain Yield predicted": value}))
            path.write_text(json.dumps(dict(type="FeatureCollection", features=features)))
            summary = dict(climate_scope="regional_manual", geojson_file=str(path),
                           tabular_format="csv", manual_bbox_grid=dict(cells=cells))
            for labels in (None, ["A"], ["B"], ["A", "B"]):
                with self.subTest(labels=labels):
                    content, _ = _build_manual_grid_prediction_workbook_bytes(summary, labels)
                    rows = list(csv.DictReader(io.StringIO(content.decode())))
                    overlay = _build_manual_grid_profile_overlay_payload(summary, labels)
                    self.assertEqual({r["Forecast grid cell id"]: r["Name"] for r in rows},
                                     {s["gridCellId"]: s["profileLabel"] for s in overlay["heat_samples"]})
                    self.assertEqual(len(rows), 2)
                    if labels is None:
                        display = build_prediction_display_feature_collection(summary)
                        self.assertEqual({r["Forecast grid cell id"]: float(r["Grain Yield predicted"]) for r in rows},
                                         {f["properties"]["Forecast grid cell id"]: f["properties"]["Grain Yield predicted"] for f in display["features"]})


if __name__ == "__main__":
    unittest.main()
