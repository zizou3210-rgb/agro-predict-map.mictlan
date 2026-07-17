from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from ce_pipeline.phase03 import script03
from preprocess import ea_pipeline


class ClimatePerformanceRegressionTest(unittest.TestCase):
    def test_aggregate_metrics_matches_expected_values_and_reuses_window_cache(self) -> None:
        nasa_series = {
            "T2M": {
                "20260101": 10.0,
                "20260102": 20.0,
                "20260103": None,
                "20260104": 30.0,
            },
            "PRECTOTCORR": {
                "20260101": 1.0,
                "20260102": 2.0,
                "20260103": None,
                "20260104": 4.0,
            },
        }

        first = ea_pipeline.aggregate_metrics(nasa_series, date(2026, 1, 1), date(2026, 1, 4))
        second = ea_pipeline.aggregate_metrics(nasa_series, date(2026, 1, 1), date(2026, 1, 4))

        self.assertEqual(first, second)
        self.assertAlmostEqual(first["avg_t2m"], 20.0)
        self.assertAlmostEqual(first["total_prectotcorr"], 7.0)

    def test_build_output_row_uses_target_windows_without_changing_results(self) -> None:
        row = {
            column: ""
            for column in ea_pipeline.CLIMATE_ID_COLUMNS
        }
        row.update(
            {
                "latitude": "1.25",
                "longitude": "32.50",
                "date_of_planting": "2026-01-01",
                "date_of_harvesting": "2026-03-15",
            }
        )

        nasa_series = {
            "T2M": {ea_pipeline.format_nasa_date(current): 25.0 for current in ea_pipeline.daterange(date(2026, 1, 1), date(2026, 3, 15))},
            "PRECTOTCORR": {ea_pipeline.format_nasa_date(current): 2.0 for current in ea_pipeline.daterange(date(2026, 1, 1), date(2026, 3, 15))},
        }

        with patch("preprocess.ea_pipeline.fetch_nasa_series", return_value=nasa_series):
            output_row, audit_row = ea_pipeline.build_output_row(row, cache={})

        self.assertEqual(output_row["planting_week_1_total_prectotcorr"], "14")
        self.assertEqual(output_row["planting_week_2_total_prectotcorr"], "14")
        self.assertEqual(output_row["planting_week_2_avg_t2m"], "25")
        self.assertEqual(output_row["harvest_back_week_1_total_prectotcorr"], "14")
        self.assertEqual(output_row["harvest_back_week_1_avg_t2m"], "25")
        self.assertEqual(audit_row["planting_week_1_start"], "2026-01-01")
        self.assertEqual(audit_row["harvest_back_week_1_end"], "2026-03-15")

    def test_fetch_chc_series_reuses_pixel_day_samples(self) -> None:
        cache = {}
        sample_calls: list[tuple[str, str]] = []

        def fake_resolve(dataset: str, current_date: date, cache_dir):  # noqa: ANN001
            return Path(f"/tmp/{dataset}-{current_date.isoformat()}.tif")

        def fake_sample(path, **kwargs):  # noqa: ANN001
            sample_calls.append((Path(path).name, kwargs["latitude"].__class__.__name__))
            name = Path(path).name.lower()
            if "chirps" in name:
                return 1.0
            if "tmax" in name:
                return 30.0
            return 10.0

        from pathlib import Path

        original_cache = script03._CHC_PIXEL_DAILY_SAMPLE_CACHE
        script03._CHC_PIXEL_DAILY_SAMPLE_CACHE = {}
        try:
            with patch("ce_pipeline.phase03.script03._resolve_prepared_raster_path", side_effect=fake_resolve), patch(
                "ce_pipeline.phase03.script03._sample_raster_value", side_effect=fake_sample
            ):
                script03._CHC_PREPARED_RASTER_PATHS = {
                    ("chirps", "2026-01-01"): Path("/tmp/chirps-2026-01-01.tif"),
                    ("chirts_tmax", "2026-01-01"): Path("/tmp/CHIRTS-ERA5.daily_Tmax.2026.01.01.tif"),
                    ("chirts_tmin", "2026-01-01"): Path("/tmp/CHIRTS-ERA5.daily_Tmin.2026.01.01.tif"),
                }
                first = script03.fetch_chc_series("1.2498", "32.5002", date(2026, 1, 1), date(2026, 1, 1), cache)
                second = script03.fetch_chc_series("1.2497", "32.5003", date(2026, 1, 1), date(2026, 1, 1), cache={})

            self.assertEqual(first["PRECTOTCORR"]["20260101"], 1.0)
            self.assertEqual(first["T2M"]["20260101"], 20.0)
            self.assertEqual(second["T2M"]["20260101"], 20.0)
            self.assertEqual(len(sample_calls), 3)
        finally:
            script03._CHC_PIXEL_DAILY_SAMPLE_CACHE = original_cache
            script03._CHC_PREPARED_RASTER_PATHS = {}

    def test_memory_guard_blocks_new_compute_workers_when_limits_are_exceeded(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "APP_PHASE03_MAX_MEMORY_PERCENT": "75",
                "APP_PHASE03_MIN_AVAILABLE_MEMORY_MB": "2500",
            },
            clear=False,
        ), patch(
            "ce_pipeline.phase03.script03.get_system_memory_status",
            return_value={"used_percent": 81.0, "available_mb": 1800.0, "total_mb": 12000.0},
        ):
            allowed, details = script03.memory_allows_new_compute_task(active_workers=1)

        self.assertFalse(allowed)
        self.assertTrue(details["memory_guard_enabled"])
        self.assertEqual(details["memory_max_percent"], 75)
        self.assertEqual(details["memory_min_available_mb"], 2500)

    def test_memory_guard_allows_bootstrap_worker_even_when_memory_is_high(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "APP_PHASE03_MAX_MEMORY_PERCENT": "70",
                "APP_PHASE03_MIN_AVAILABLE_MEMORY_MB": "3000",
            },
            clear=False,
        ), patch(
            "ce_pipeline.phase03.script03.get_system_memory_status",
            return_value={"used_percent": 90.0, "available_mb": 1200.0, "total_mb": 12000.0},
        ):
            allowed, details = script03.memory_allows_new_compute_task(active_workers=0)

        self.assertTrue(allowed)
        self.assertTrue(details["memory_forced_single_start"])

    def test_build_climate_series_groups_deduplicates_same_pixel_and_dates(self) -> None:
        row_a = {
            "latitude": "1.2498",
            "longitude": "32.5002",
            "date_of_planting": "2026-01-01",
            "date_of_harvesting": "2026-03-15",
        }
        row_b = {
            "latitude": "1.2497",
            "longitude": "32.5003",
            "date_of_planting": "2026-01-01",
            "date_of_harvesting": "2026-03-15",
        }
        row_c = {
            "latitude": "1.2497",
            "longitude": "32.5003",
            "date_of_planting": "2026-01-02",
            "date_of_harvesting": "2026-03-15",
        }

        groups, row_series_keys = script03.build_climate_series_groups([row_a, row_b, row_c])

        self.assertEqual(len(groups), 2)
        self.assertEqual(len(row_series_keys), 3)
        self.assertEqual(sorted(len(items) for items in groups.values()), [1, 2])

    def test_versioned_climate_feature_cache_round_trip(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp_dir_name:
            cache_path = Path(tmp_dir_name) / "climate_feature_cache.json"
            series_key = ("CHC_0p05_R1C2", "2026-01-01", "2026-03-15")
            serialized = script03.serialize_climate_series_key(series_key)
            payload = {
                serialized: {
                    "series_key": {
                        "pixel_id": series_key[0],
                        "date_of_planting": series_key[1],
                        "date_of_harvesting": series_key[2],
                    },
                    "output_row": {"planting_week_1_total_prectotcorr": "14"},
                    "audit_row": {"forecast_reference_year": "2025"},
                }
            }

            script03.save_climate_feature_cache(cache_path, payload)
            loaded = script03.load_climate_feature_cache(cache_path)

            self.assertEqual(loaded, payload)

    def test_versioned_climate_feature_cache_invalidates_mismatched_payload(self) -> None:
        from tempfile import TemporaryDirectory
        import json

        with TemporaryDirectory() as tmp_dir_name:
            cache_path = Path(tmp_dir_name) / "climate_feature_cache.json"
            good_key = script03.serialize_climate_series_key(("CHC_0p05_R1C2", "2026-01-01", "2026-03-15"))
            bad_payload = {
                "cache_version": script03.CLIMATE_FEATURE_CACHE_VERSION,
                "entries": {
                    good_key: {
                        "series_key": {
                            "pixel_id": "DIFFERENT_PIXEL",
                            "date_of_planting": "2026-01-01",
                            "date_of_harvesting": "2026-03-15",
                        },
                        "output_row": {"planting_week_1_total_prectotcorr": "14"},
                        "audit_row": {"forecast_reference_year": "2025"},
                    }
                },
            }
            cache_path.write_text(json.dumps(bad_payload), encoding="utf-8")

            loaded = script03.load_climate_feature_cache(cache_path)

            self.assertEqual(loaded, {})

    def test_enrich_soils_resolves_unique_points_once_and_propagates_rows(self) -> None:
        records = [
            {
                "_GPS coordinates_latitude": "1.250000",
                "_GPS coordinates_longitude": "32.500000",
            },
            {
                "_GPS coordinates_latitude": "1.250000",
                "_GPS coordinates_longitude": "32.500000",
            },
            {
                "_GPS coordinates_latitude": "1.300000",
                "_GPS coordinates_longitude": "32.600000",
            },
        ]

        calls: list[tuple[float, float]] = []

        def fake_resolve(latitude, longitude, *, payload):  # noqa: ANN001
            calls.append((latitude, longitude))
            return ({
                "Soil type/texture": "Loam",
                "Soil Depth (cm)-How deep do you expect maize roots to grow in this soil?": "100cm o mas",
                "soil_source": "soilgrids",
                "soil_texture_usda_class": "Loam",
            }, "soilgrids", True)

        with patch("ce_pipeline.phase03.script03.soil_enrichment.load_cache_payload", return_value={}), patch(
            "ce_pipeline.phase03.script03.soil_enrichment.write_cache_payload"
        ), patch(
            "ce_pipeline.phase03.script03.soil_enrichment.resolve_soil_record_from_payload",
            side_effect=fake_resolve,
        ):
            enriched, metadata = script03.enrich_soils(records, Path("/tmp/test_soil_cache.json"))

        self.assertEqual(len(calls), 2)
        self.assertEqual(metadata["soil_enriched_cells"], 2)
        self.assertEqual(metadata["soil_enriched_rows"], 3)
        self.assertEqual(metadata["soil_service_success_cells"], 2)
        self.assertEqual(enriched[0]["Soil type/texture"], "Loam")
        self.assertEqual(enriched[1]["Soil type/texture"], "Loam")
        self.assertEqual(enriched[2]["Soil type/texture"], "Loam")


if __name__ == "__main__":
    unittest.main()
