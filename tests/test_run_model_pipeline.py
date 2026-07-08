from __future__ import annotations

import unittest

import pandas as pd

from cimmyt_app.pipeline.run_model_pipeline import combine_geo_and_prediction_dataframes


class RunModelPipelineTest(unittest.TestCase):
    def test_combine_geo_and_prediction_dataframes_drops_overlapping_germplasm_columns(self) -> None:
        geo_df = pd.DataFrame(
            {
                "Trial series name": ["EAPP1-01 (Medium)"],
                "Rep": ["1"],
                "Farm": ["1"],
                "Site Number": ["1"],
                "Plot": ["1"],
                "EntryCode": ["ENTRY-001"],
                "Name": ["PIONEER"],
                "Local check, Name of variety provided by farmer": ["Local Variety"],
                "_GPS coordinates_latitude": [19.5],
                "_GPS coordinates_longitude": [-99.2],
            }
        )
        prediction_df = pd.DataFrame(
            {
                "Trial series name": ["SHOULD-NOT-WIN"],
                "Rep": ["999"],
                "Farm": ["999"],
                "Site Number": ["999"],
                "Plot": ["999"],
                "EntryCode": ["OVERLAP"],
                "Name": ["OVERLAP"],
                "Local check, Name of variety provided by farmer": ["OVERLAP"],
                "idPK": ["0001-Set-01"],
                "Grain Yield predicted": [6.25],
            }
        )

        combined = combine_geo_and_prediction_dataframes(geo_df, prediction_df)

        self.assertEqual(combined.loc[0, "EntryCode"], "ENTRY-001")
        self.assertEqual(combined.loc[0, "Name"], "PIONEER")
        self.assertEqual(combined.loc[0, "idPK"], "0001-Set-01")
        self.assertEqual(combined.loc[0, "Grain Yield predicted"], 6.25)
        self.assertEqual(list(combined.columns).count("EntryCode"), 1)
        self.assertEqual(list(combined.columns).count("Name"), 1)

    def test_combine_geo_and_prediction_dataframes_preserves_forecast_metadata_columns(self) -> None:
        geo_df = pd.DataFrame(
            {
                "Trial series name": ["EAPP1-01 (Medium)"],
                "Rep": ["1"],
                "Farm": ["1"],
                "Site Number": ["1"],
                "Plot": ["1"],
                "Name": ["PIONEER"],
                "_GPS coordinates_latitude": [0.313611],
                "_GPS coordinates_longitude": [32.581111],
                "Forecast locality": ["Kampala"],
                "Forecast country": ["Uganda"],
                "Selected model id": ["model-123"],
                "Original GPS coordinates": ["1.25 32.50"],
            }
        )
        prediction_df = pd.DataFrame(
            {
                "idPK": ["0001-Set-01"],
                "Grain Yield predicted": [6.25],
            }
        )

        combined = combine_geo_and_prediction_dataframes(geo_df, prediction_df)

        self.assertEqual(combined.loc[0, "Forecast locality"], "Kampala")
        self.assertEqual(combined.loc[0, "Forecast country"], "Uganda")
        self.assertEqual(combined.loc[0, "Selected model id"], "model-123")
        self.assertEqual(combined.loc[0, "Original GPS coordinates"], "1.25 32.50")
        self.assertEqual(combined.loc[0, "Grain Yield predicted"], 6.25)
