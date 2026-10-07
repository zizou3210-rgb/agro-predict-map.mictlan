from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import numpy as np

from ce_pipeline.phase03 import script03


@unittest.skipIf(script03.rasterio is None, "Rasterio is optional")
class ChcBatchReadingTest(unittest.TestCase):
    def setUp(self):
        script03._clear_thread_raster_image_cache()
        script03._clear_raster_pixel_index_cache()
        script03._clear_chc_pixel_daily_sample_cache()
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.addCleanup(script03._clear_thread_raster_image_cache)
        self.addCleanup(script03._clear_raster_pixel_index_cache)
        self.addCleanup(script03._clear_chc_pixel_daily_sample_cache)
        self.pixels = {}
        for row in range(8, 12):
            for col in range(8, 12):
                latitude, longitude = 2-(row+0.5)*0.05, 32+(col+0.5)*0.05
                pixel_id, _, _ = script03.resolve_chc_pixel_metadata(latitude, longitude)
                self.pixels[pixel_id] = (latitude, longitude)
        self.paths = {}
        for day in (date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3)):
            self.paths[day] = {}
            for dataset, offset in (("chirps", 0), ("chirts_tmax", 20), ("chirts_tmin", 10)):
                path = Path(self.directory.name) / f"{dataset}-{day}.tif"
                data = np.arange(32*32, dtype="float32").reshape(32, 32)/100 + offset
                data[8, 8] = script03.CHIRPS_FILL_VALUE if dataset == "chirps" else script03.CHIRTS_FILL_VALUE
                data[9, 9] = np.nan
                if dataset == "chirts_tmin":
                    data[10, 10] = script03.CHIRTS_FILL_VALUE
                with script03.rasterio.open(
                    path, "w", driver="GTiff", width=32, height=32, count=1,
                    dtype="float32", crs="EPSG:4326",
                    transform=script03.rasterio.transform.from_origin(32, 2, 0.05, 0.05),
                    tiled=True, blockxsize=16, blockysize=16,
                ) as raster:
                    raster.write(data, 1)
                self.paths[day][dataset] = path

    def test_native_block_values_equal_scalar_including_fill_nan_and_boundary(self):
        pixels = {**self.pixels, "out-of-coverage": (-90, 32.5)}
        with patch.object(script03, "resolve_phase03_raster_backend", return_value="rasterio"):
            for dataset, path in self.paths[date(2026, 1, 1)].items():
                batch = script03._sample_raster_pixel_batch(path, dataset, pixels)
                for pixel_id, (lat, lon) in pixels.items():
                    scalar = script03._sample_raster_value(
                        path, dataset=dataset, pixel_id=pixel_id, latitude=lat, longitude=lon,
                        fill_value=script03.CHIRPS_FILL_VALUE if dataset == "chirps" else script03.CHIRTS_FILL_VALUE,
                        latitude_min=script03.CHIRPS_MIN_LATITUDE if dataset == "chirps" else script03.CHIRTS_MIN_LATITUDE,
                        latitude_max=script03.CHIRPS_MAX_LATITUDE if dataset == "chirps" else script03.CHIRTS_MAX_LATITUDE,
                    )
                    self.assertEqual(batch[pixel_id], scalar)

    def test_batch_materialization_equals_scalar_and_warm_cache_reads_no_rasters(self):
        items = []
        reference = {}
        for pixel_id, (lat, lon) in self.pixels.items():
            _, center_lat, center_lon = script03.resolve_chc_pixel_metadata(lat, lon)
            values = {
                script03.ea_pipeline.format_nasa_date(day): script03._sample_climate_day_for_pixel(
                    pixel_id=pixel_id, current_date=day, latitude=lat, longitude=lon, raster_paths=paths,
                ) for day, paths in self.paths.items()
            }
            for start in (date(2026, 1, 1), date(2026, 1, 2)):
                end = date(2026, 1, 3)
                key = script03._build_chc_cache_key(center_lat, center_lon, start, end)
                reference[key] = script03._materialize_nasa_series_from_daily_values(values, start_date=start, end_date=end)
                items.append(((pixel_id, start.isoformat(), end.isoformat()), {"latitude": str(lat), "longitude": str(lon)}))
        daily = {}
        persisted = {}
        resolutions = []

        def lookup_daily(pixel_id, start, end, **kwargs):
            return {k: v for k, v in daily.items() if k[0] == pixel_id and start <= k[1] <= end}

        def resolve(day, cache_dir):
            resolutions.append(day)
            return self.paths[day], {}

        # Match the original precompute's planting-to-harvest bounds for this
        # deliberately short fixture; actual climate-window bounds have separate tests.
        bounds = {pixel_id: (date(2026, 1, 1), date(2026, 1, 3)) for pixel_id in self.pixels}
        with patch.object(script03, "collect_required_chc_date_bounds", return_value=bounds), \
             patch.object(script03, "get_daily_climate_cache_range", side_effect=lookup_daily), \
             patch.object(script03, "get_nasa_cache_entries", return_value={}), \
             patch.object(script03, "_resolve_daily_raster_paths", side_effect=resolve), \
             patch.object(script03, "upsert_daily_climate_cache_entries", side_effect=lambda entries: daily.update(entries)), \
             patch.object(script03, "upsert_nasa_cache_entries", side_effect=lambda entries: persisted.update(entries)):
            cache = {}
            stats = script03._precompute_chc_series_by_date(items, cache, worker_count=2, debug_file=None)
            self.assertEqual(cache, reference)
            self.assertEqual(persisted, reference)
            self.assertEqual(stats["series_materialized"], len(reference))
            self.assertEqual(resolutions, list(self.paths))
            self.assertEqual(len(daily), len(self.pixels)*3)
            with patch.object(script03, "_sample_raster_pixel_batch", side_effect=AssertionError("warm cache read a raster")):
                warm_cache = {}
                script03._precompute_chc_series_by_date(items, warm_cache, worker_count=2, debug_file=None)
            self.assertEqual(warm_cache, reference)
            self.assertEqual(resolutions, list(self.paths))
            # Repair one missing pixel/day without reading its neighbours again.
            missing_key = next(iter(daily))
            del daily[missing_key]
            resolutions.clear()
            with patch.object(script03, "_sample_raster_pixel_batch", wraps=script03._sample_raster_pixel_batch) as sample_batch:
                repaired_cache = {}
                script03._precompute_chc_series_by_date(items, repaired_cache, worker_count=2, debug_file=None)
            self.assertEqual(repaired_cache, reference)
            self.assertEqual(resolutions, [date.fromisoformat(missing_key[1])])
            self.assertEqual(sample_batch.call_count, 3)
            self.assertTrue(all(set(call.args[2]) == {missing_key[0]} for call in sample_batch.call_args_list))

    def test_aggregation_cache_is_bounded_and_keeps_object_identity(self):
        script03._CHC_SERIES_AGGREGATION_CACHE.clear()
        script03._CHC_WINDOW_METRICS_CACHE.clear()
        self.addCleanup(script03._CHC_SERIES_AGGREGATION_CACHE.clear)
        self.addCleanup(script03._CHC_WINDOW_METRICS_CACHE.clear)
        for value in range(300):
            series = {"T2M": {"20260101": float(value)}, "PRECTOTCORR": {"20260101": 1.0}}
            result = script03.aggregate_metrics_fast(series, date(2026, 1, 1), date(2026, 1, 1))
            self.assertEqual(result, {"avg_t2m": float(value), "total_prectotcorr": 1.0})
        self.assertLessEqual(len(script03._CHC_SERIES_AGGREGATION_CACHE), 128)
        self.assertLessEqual(len(script03._CHC_WINDOW_METRICS_CACHE), 128)

    def test_five_year_climate_outputs_equal_scalar_route(self):
        ea = script03.ea_pipeline
        override = {"forecast_years_back": 5, "use_source_row_dates": True, "climate_scope": "point"}
        representatives = []
        for pixel_id, (lat, lon) in list(self.pixels.items())[:2]:
            row = {key: "" for key in ea.CLIMATE_INPUT_COLUMNS}
            row.update(latitude=str(lat), longitude=str(lon), date_of_planting="2026-04-07", date_of_harvesting="2026-09-05")
            representatives.append(((pixel_id, "2026-04-07", "2026-09-05"), row))
        items = script03.build_forecast_reference_precompute_series_items(representatives, override)
        self.assertEqual({date.fromisoformat(key[1]).year for key, _ in items}, {2021, 2022, 2023, 2024, 2025})

        def value(dataset, day, latitude):
            return None if dataset == "chirts_tmin" and day.day % 5 == 0 else float(day.year-2020)+latitude+(20 if dataset == "chirts_tmax" else 0)

        def paths(day, cache_dir):
            return {dataset: Path(f"/tmp/{dataset}-{day}.tif") for dataset in ("chirps", "chirts_tmax", "chirts_tmin")}, {}

        def scalar(path, **kwargs):
            return value(kwargs["dataset"], date.fromisoformat(path.stem[-10:]), kwargs["latitude"])

        def batch(path, dataset, pixels):
            day = date.fromisoformat(path.stem[-10:])
            return {pixel_id: value(dataset, day, lat) for pixel_id, (lat, lon) in pixels.items()}

        outputs = []
        with patch.object(script03, "_resolve_daily_raster_paths", side_effect=paths), \
             patch.object(script03, "get_nasa_cache_entries", return_value={}), \
             patch.object(script03, "get_daily_climate_cache_range", return_value={}), \
             patch.object(script03, "upsert_daily_climate_cache_entries"), \
             patch.object(script03, "upsert_nasa_cache_entries"), \
             patch.object(script03, "_sample_raster_value", side_effect=scalar), \
             patch.object(script03, "_sample_raster_pixel_batch", side_effect=batch), \
             patch.object(ea, "fetch_nasa_series", script03.fetch_chc_series), \
             patch.object(ea, "aggregate_metrics", script03.aggregate_metrics_fast):
            for enabled in (False, True):
                script03._clear_chc_pixel_daily_sample_cache()
                cache = {}
                with patch.object(script03, "resolve_phase03_daily_climate_cache_enabled", return_value=enabled):
                    script03.precompute_chc_series_batches(items, cache, worker_count=2, debug_file=None)
                outputs.append([ea.build_output_row(row, cache, climate_override=override)[0] for _, row in representatives])
        self.assertEqual(outputs[0], outputs[1])
