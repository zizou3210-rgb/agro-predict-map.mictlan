from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from preprocess import ea_pipeline
from preprocess.soil_enrichment import (
    DEFAULT_DEPTH_BUCKET,
    enrich_manual_bbox_prediction_soils,
    pipeline_texture_bucket,
    usda_texture_class_from_fractions,
)
from pipeline.africa_country_localities import (
    filter_localities_within_bounds,
    list_african_countries,
    normalize_bounds,
    resolve_african_country,
    sample_localities_within_bounds,
)


def build_base_record() -> dict[str, object]:
    return {
        "Country": "Uganda",
        "GPS coordinates": "1.25 32.50",
        "_GPS coordinates_latitude": "1.25",
        "_GPS coordinates_longitude": "32.50",
        "_GPS coordinates_altitude": "1100",
        "_GPS coordinates_precision": "10",
        "Date of planting": "2025-03-01",
        "Date_of_harvesting": "2025-08-01",
        "Trial series name": "EAPP1-01",
        "Rep": "1",
        "Farm": "2",
        "Site Number": "3",
        "Plot": "4",
        "EntryCode": "ENTRY-001",
        "Name": "CIM-RT-EAPP1-E -001",
        "Local check, Name of variety provided by farmer": "",
    }


class AfricanCountryLocalitiesTest(unittest.TestCase):
    def test_list_african_countries_uses_english_names_and_iso_codes(self) -> None:
        countries = list_african_countries()

        self.assertIn({"country": "Kenya", "iso2": "KE"}, countries)
        self.assertIn({"country": "Tanzania", "iso2": "TZ"}, countries)
        self.assertIn({"country": "Uganda", "iso2": "UG"}, countries)

    def test_resolve_african_country_accepts_iso_and_country_name(self) -> None:
        self.assertEqual(resolve_african_country("KE").country, "Kenya")
        self.assertEqual(resolve_african_country("Kenya").iso2, "KE")

    def test_normalize_bounds_sorts_manual_limits(self) -> None:
        self.assertEqual(
            normalize_bounds(1.0, -1.0, 37.8, 34.42),
            (-1.0, 1.0, 34.42, 37.8),
        )

    @patch("cimmyt_app.pipeline.africa_country_localities.load_country_localities")
    def test_filter_localities_within_bounds_filters_and_sorts_population_desc(
        self,
        mock_load_country_localities,
    ) -> None:
        def fake_loader(country_value: str, cache_dir=None):  # noqa: ANN001
            dataset = {
                "KE": [
                    {
                        "name": "Nairobi",
                        "latitude": "-1.286389",
                        "longitude": "36.817223",
                        "population": 4397073,
                        "country": "Kenya",
                        "country_code": "KE",
                        "geoname_id": "184745",
                    },
                    {
                        "name": "Mombasa",
                        "latitude": "-4.043477",
                        "longitude": "39.668206",
                        "population": 1208333,
                        "country": "Kenya",
                        "country_code": "KE",
                        "geoname_id": "186301",
                    },
                ],
                "UG": [
                    {
                        "name": "Kampala",
                        "latitude": "0.313611",
                        "longitude": "32.581111",
                        "population": 1680600,
                        "country": "Uganda",
                        "country_code": "UG",
                        "geoname_id": "232422",
                    }
                ],
            }
            return dataset.get(country_value, [])

        mock_load_country_localities.side_effect = fake_loader

        filtered = filter_localities_within_bounds(-2.0, 1.0, 32.0, 37.0)

        self.assertEqual(
            [item["name"] for item in filtered],
            ["Nairobi", "Kampala"],
        )

    @patch("cimmyt_app.pipeline.africa_country_localities.load_country_localities")
    def test_filter_localities_within_bounds_accepts_reversed_limits(
        self,
        mock_load_country_localities,
    ) -> None:
        def fake_loader(country_value: str, cache_dir=None):  # noqa: ANN001
            if country_value == "KE":
                return [
                    {
                        "name": "Nairobi",
                        "latitude": "-1.286389",
                        "longitude": "36.817223",
                        "population": 4397073,
                        "country": "Kenya",
                        "country_code": "KE",
                        "geoname_id": "184745",
                    }
                ]
            return []

        mock_load_country_localities.side_effect = fake_loader

        filtered = filter_localities_within_bounds(1.0, -2.0, 37.0, 32.0)

        self.assertEqual([item["name"] for item in filtered], ["Nairobi"])

    @patch("cimmyt_app.pipeline.africa_country_localities.filter_localities_within_bounds")
    def test_sample_localities_within_bounds_returns_count_and_sample(
        self,
        mock_filter_localities_within_bounds,
    ) -> None:
        mock_filter_localities_within_bounds.return_value = [
            {"name": "Nairobi", "population": 4397073},
            {"name": "Kampala", "population": 1680600},
            {"name": "Kisumu", "population": 409928},
        ]

        summary = sample_localities_within_bounds(-2.0, 1.0, 32.0, 37.0, limit=2)

        self.assertEqual(summary["locality_count"], 3)
        self.assertEqual([item["name"] for item in summary["sample"]], ["Nairobi", "Kampala"])

    @patch("cimmyt_app.pipeline.africa_country_localities.parse_geonames_localities")
    @patch("cimmyt_app.pipeline.africa_country_localities.download_geonames_country_dump")
    def test_load_country_localities_retries_after_corrupt_zip(
        self,
        mock_download_geonames_country_dump,
        mock_parse_geonames_localities,
    ) -> None:
        from pipeline.africa_country_localities import load_country_localities

        locality_rows = [
            {
                "name": "Nairobi",
                "latitude": "-1.286389",
                "longitude": "36.817223",
                "population": 4397073,
                "country": "Kenya",
                "country_code": "KE",
                "geoname_id": "184745",
            }
        ]

        with tempfile.TemporaryDirectory(prefix="geonames_cache_test_") as temp_dir:
            cache_dir = Path(temp_dir)
            zip_path = cache_dir / "KE.zip"
            zip_path.write_bytes(b"corrupt zip")

            def fake_download(country, cache_dir=None):  # noqa: ANN001
                target_dir = Path(cache_dir or temp_dir)
                rewritten_zip = target_dir / "KE.zip"
                rewritten_zip.write_bytes(b"fresh zip placeholder")
                return rewritten_zip

            mock_download_geonames_country_dump.side_effect = fake_download
            mock_parse_geonames_localities.side_effect = [EOFError(), locality_rows]

            loaded = load_country_localities("KE", cache_dir=cache_dir)

            self.assertEqual(loaded, locality_rows)
            self.assertEqual(mock_parse_geonames_localities.call_count, 2)
            self.assertEqual(json.loads((cache_dir / "KE_localities.json").read_text(encoding="utf-8")), locality_rows)


class Phase02LocalityExpansionTest(unittest.TestCase):
    @patch("cimmyt_app.preprocess.ea_pipeline.load_country_localities")
    def test_expand_records_for_country_localities_copies_original_row_and_overrides_coordinates(
        self,
        mock_load_country_localities,
    ) -> None:
        mock_load_country_localities.return_value = [
            {
                "name": "Nairobi",
                "geoname_id": "184745",
                "population": 4397073,
                "latitude": "-1.286389",
                "longitude": "36.817223",
                "country": "Kenya",
                "country_code": "KE",
            },
            {
                "name": "Kisumu",
                "geoname_id": "191245",
                "population": 409928,
                "latitude": "-0.102211",
                "longitude": "34.761711",
                "country": "Kenya",
                "country_code": "KE",
            },
        ]
        climate_override = {
            "regional_country": "KE",
            "forecast_planting_date": "2026-04-07",
            "forecast_harvesting_date": "2026-09-10",
            "selected_model_id": "model-123",
        }

        expanded_records, data_input_rows, metadata = ea_pipeline.expand_records_for_country_localities(
            [build_base_record()],
            climate_override,
        )

        self.assertEqual(len(expanded_records), 2)
        self.assertEqual(len(data_input_rows), 2)
        self.assertEqual(metadata["forecast_country"], "Kenya")
        self.assertEqual(metadata["forecast_country_code"], "KE")
        self.assertEqual(metadata["selected_model_id"], "model-123")

        first_row = expanded_records[0]
        self.assertEqual(first_row["Country"], "Kenya")
        self.assertEqual(first_row["GPS coordinates"], "-1.286389 36.817223")
        self.assertEqual(first_row["_GPS coordinates_latitude"], "-1.286389")
        self.assertEqual(first_row["_GPS coordinates_longitude"], "36.817223")
        self.assertEqual(first_row["Forecast locality"], "Nairobi")
        self.assertEqual(first_row["Forecast country"], "Kenya")
        self.assertEqual(first_row["Forecast country code"], "KE")
        self.assertEqual(first_row["Selected model id"], "model-123")
        self.assertEqual(first_row["Original GPS coordinates"], "1.25 32.50")


class SoilEnrichmentTest(unittest.TestCase):
    def test_usda_texture_mapping_feeds_pipeline_bucket(self) -> None:
        texture_class = usda_texture_class_from_fractions(620.0, 230.0, 150.0)
        self.assertEqual(texture_class, "Sandy Loam")
        self.assertEqual(pipeline_texture_bucket(texture_class), "Sandy Loam")

    @patch("cimmyt_app.preprocess.soil_enrichment.resolve_soil_record")
    def test_enrich_manual_bbox_prediction_soils_fills_blank_soil_columns(self, mock_resolve_soil_record) -> None:
        mock_resolve_soil_record.return_value = {
            "Soil type/texture": "Clay Loam",
            "Soil Depth (cm)-How deep do you expect maize roots to grow in this soil?": "75cm",
            "soil_source": "soilgrids",
        }
        records = [
            {
                "_GPS coordinates_latitude": "0.313611",
                "_GPS coordinates_longitude": "32.581111",
                "Forecast grid cell id": "cell-a",
                "Selected model id": "model-123",
                "Soil type/texture": "",
                "Soil Depth (cm)-How deep do you expect maize roots to grow in this soil?": "",
            }
        ]

        enriched, metadata = enrich_manual_bbox_prediction_soils(
            records,
            climate_scope="regional_manual",
            selected_model_id="model-123",
            cache_path=Path(tempfile.gettempdir()) / "soil_enrichment_test_cache.json",
        )

        self.assertEqual(enriched[0]["Soil type/texture"], "Clay Loam")
        self.assertEqual(
            enriched[0]["Soil Depth (cm)-How deep do you expect maize roots to grow in this soil?"],
            "75cm",
        )
        self.assertEqual(metadata["soil_enriched_rows"], 1)
        self.assertEqual(metadata["soil_enriched_cells"], 1)

    def test_enrich_manual_bbox_prediction_soils_uses_fallback_for_missing_coordinates(self) -> None:
        records = [
            {
                "_GPS coordinates_latitude": "",
                "_GPS coordinates_longitude": "",
                "Forecast grid cell id": "cell-a",
                "Selected model id": "model-123",
                "Soil type/texture": "",
                "Soil Depth (cm)-How deep do you expect maize roots to grow in this soil?": "",
            }
        ]

        enriched, _ = enrich_manual_bbox_prediction_soils(
            records,
            climate_scope="regional_manual",
            selected_model_id="model-123",
            cache_path=Path(tempfile.gettempdir()) / "soil_enrichment_test_cache.json",
        )

        self.assertEqual(enriched[0]["Soil type/texture"], "Loam")
        self.assertEqual(
            enriched[0]["Soil Depth (cm)-How deep do you expect maize roots to grow in this soil?"],
            DEFAULT_DEPTH_BUCKET,
        )

    def test_expand_records_for_manual_bbox_localities_uses_grid_cells_and_preserves_model(
        self,
    ) -> None:
        climate_override = {
            "regional_bounds_latitude_min": -0.5,
            "regional_bounds_latitude_max": 1.0,
            "regional_bounds_longitude_min": 32.0,
            "regional_bounds_longitude_max": 33.0,
            "forecast_planting_date": "2026-04-07",
            "forecast_harvesting_date": "2026-09-10",
            "selected_model_id": "model-123",
        }

        expanded_records, data_input_rows, metadata = ea_pipeline.expand_records_for_manual_bbox_localities(
            [build_base_record()],
            climate_override,
        )

        self.assertGreater(len(expanded_records), 0)
        self.assertEqual(len(expanded_records), len(data_input_rows))
        self.assertEqual(metadata["manual_bbox_locality_count"], len(expanded_records))
        self.assertEqual(metadata["selected_model_id"], "model-123")
        self.assertEqual(metadata["manual_bbox_grid_cell_count"], len(expanded_records))

        first_row = expanded_records[0]
        self.assertTrue(str(first_row["Forecast locality"]).strip())
        self.assertEqual(
            str(first_row["Forecast locality"]),
            str(first_row["Forecast grid cell id"]),
        )
        self.assertEqual(first_row["Forecast country code"], "")
        self.assertEqual(first_row["Selected model id"], "model-123")
        self.assertIn(" ", str(first_row["GPS coordinates"]))
        self.assertEqual(first_row["Original GPS coordinates"], "1.25 32.50")


if __name__ == "__main__":
    unittest.main()
