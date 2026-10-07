from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from ce_pipeline.phase03 import script03
from preprocess import ea_pipeline


class ClimatePerformanceRegressionTest(unittest.TestCase):
    def test_daily_climate_cache_is_opt_in(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            self.assertFalse(script03.resolve_phase03_daily_climate_cache_enabled())
        with patch.dict(
            "os.environ",
            {"APP_PHASE03_DAILY_CLIMATE_CACHE_ENABLED": "true"},
            clear=True,
        ):
            self.assertTrue(script03.resolve_phase03_daily_climate_cache_enabled())

    def test_raster_plan_skips_all_work_when_feature_cache_is_complete(self) -> None:
        with patch(
            "ce_pipeline.phase03.script03.get_nasa_cache_entries",
            side_effect=AssertionError("feature-cache hits must not query series or raster caches"),
        ), patch(
            "ce_pipeline.phase03.script03.get_daily_climate_cache_range",
            side_effect=AssertionError("feature-cache hits must not query daily cache"),
        ):
            precompute_items, required_dates = script03.plan_chc_precompute_series_and_raster_dates(
                [],
                None,
                daily_climate_cache_enabled=True,
            )

        self.assertEqual(precompute_items, [])
        self.assertEqual(required_dates, [])

    def test_workspace_expands_rows_then_skips_prefetch_on_feature_cache_hit(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory(prefix="phase03_cache_first_") as tmp_dir_name:
            output_dir = Path(tmp_dir_name) / "phase02"
            output_dir.mkdir(parents=True)
            row = {column: "" for column in ea_pipeline.CLIMATE_ID_COLUMNS}
            row.update(
                {
                    "latitude": "1.2498",
                    "longitude": "32.5002",
                    "date_of_planting": "2026-01-01",
                    "date_of_harvesting": "2026-02-28",
                    "forecast_grid_cell_id": "Manual bounds:R1C1",
                    "forecast_grid_cell_index": "1",
                }
            )
            series_key = script03.build_climate_series_key(row)
            serialized_key = script03.serialize_climate_series_key(series_key)
            cached_payload = {
                "series_key": {
                    "pixel_id": series_key[0],
                    "date_of_planting": series_key[1],
                    "date_of_harvesting": series_key[2],
                },
                "output_row": {column: "" for column in ea_pipeline.build_output_columns()},
                "audit_row": {},
            }
            events: list[str] = []
            progress_events = []
            prefetch_date_calls: list[list[date]] = []

            def expand_records(*_args, **_kwargs):
                events.append("expand")
                return [row], [row], {"manual_bbox_grid_cell_count": 1}

            def load_feature_cache(_keys, *, touch_access):
                events.append("feature_cache")
                return {serialized_key: cached_payload}

            def prefetch(required_dates):
                events.append("prefetch")
                prefetch_date_calls.append(required_dates)
                return {
                    "task_total": 0,
                    "downloaded": 0,
                    "cached": 0,
                    "prepared_raster_paths": {},
                }

            with patch.dict(ea_pipeline.PHASE_DIRS, {"phase02": output_dir}), patch(
                "preprocess.ea_pipeline.expand_records_for_manual_bbox_localities",
                side_effect=expand_records,
            ), patch(
                "preprocess.ea_pipeline.write_csv"
            ), patch(
                "preprocess.ea_pipeline.write_workbook"
            ), patch(
                "preprocess.ea_pipeline.write_metadata"
            ), patch(
                "ce_pipeline.phase03.script03.resolve_shared_climate_feature_cache_path",
                return_value=Path(tmp_dir_name) / "feature_cache.sqlite3",
            ), patch(
                "ce_pipeline.phase03.script03.get_climate_feature_cache_entries",
                side_effect=load_feature_cache,
            ), patch(
                "ce_pipeline.phase03.script03.get_nasa_cache_entries",
                side_effect=AssertionError("feature-cache hit should avoid series lookup"),
            ):
                result = script03.build_phase02_records_parallel_workspace(
                    [ea_pipeline.YIELD_HEADER],
                    [row],
                    progress_file=None,
                    progress_callback=lambda *event: progress_events.append(event),
                    skip_soil_enrichment=True,
                    climate_override={
                        "climate_scope": "regional_manual",
                        "regional_bounds_label": "Manual bounds",
                    },
                    climate_prefetch_callback=prefetch,
                )

            self.assertEqual(events, ["expand", "feature_cache", "prefetch"])
            windows = [event for event in progress_events if event[1] == "Computing climate windows"]
            self.assertEqual(windows[-1][3]["stage_percent"], 100)
            self.assertEqual(windows[-1][3]["stage_completed"], 1)
            self.assertIn("Saving climate workbook", [event[1] for event in progress_events])
            self.assertIn("Saving window audit", [event[1] for event in progress_events])
            completed_stages = {
                event[1] for event in progress_events
                if (event[3] or {}).get("stage_percent") == 100
            }
            self.assertTrue({
                "Grouping climate series", "Checking climate feature cache",
                "Saving climate feature cache", "Building climate output rows",
                "Indexing climate output rows", "Joining climate features to selected profiles",
                "Building climate metadata", "Saving climate metadata",
            } <= completed_stages)
            self.assertEqual(prefetch_date_calls, [[]])
            self.assertEqual(result[2]["climate_prefetch"]["task_total"], 0)
            self.assertEqual(
                set(result[2]["phase_timings_seconds"]),
                {
                    "feature_cache_lookup",
                    "cache_and_raster_plan",
                    "raster_prefetch",
                    "climate_precompute_and_raster_sampling",
                    "climate_output_and_series_compute",
                },
            )

    def test_raster_plan_uses_only_dates_missing_from_daily_cache(self) -> None:
        series_items = [
            (
                ("CHC_0p05_R1775C4250", "2026-01-01", "2026-02-28"),
                {"latitude": "1.2498", "longitude": "32.5002"},
            ),
        ]

        def cached_nasa_series(*_args, **_kwargs):
            return {}

        def full_daily_range(pixel_id, start_date, end_date, *, cache_version):
            start_value = date.fromisoformat(start_date)
            end_value = date.fromisoformat(end_date)
            return {
                (pixel_id, current_date.isoformat(), cache_version): {
                    "T2M": 20.0,
                    "PRECTOTCORR": 1.0,
                }
                for current_date in ea_pipeline.daterange(start_value, end_value)
            }

        with patch(
            "ce_pipeline.phase03.script03.get_nasa_cache_entries",
            side_effect=cached_nasa_series,
        ), patch(
            "ce_pipeline.phase03.script03.get_daily_climate_cache_range",
            side_effect=full_daily_range,
        ) as daily_cache_mock:
            precompute_items, required_dates = script03.plan_chc_precompute_series_and_raster_dates(
                series_items,
                None,
                daily_climate_cache_enabled=True,
            )

        self.assertEqual(len(precompute_items), 1)
        self.assertEqual(required_dates, [])
        self.assertEqual(daily_cache_mock.call_count, 1)

    def test_raster_plan_includes_union_gap_scanned_by_pixel_precompute(self) -> None:
        series_items = [
            (
                ("CHC_0p05_R1775C4250", "2026-01-01", "2026-01-15"),
                {"latitude": "1.2498", "longitude": "32.5002"},
            ),
            (
                ("CHC_0p05_R1775C4250", "2026-06-01", "2026-06-15"),
                {"latitude": "1.2498", "longitude": "32.5002"},
            ),
        ]

        with patch(
            "ce_pipeline.phase03.script03.get_nasa_cache_entries",
            return_value={},
        ):
            precompute_items, required_dates = script03.plan_chc_precompute_series_and_raster_dates(
                series_items,
                None,
                daily_climate_cache_enabled=False,
            )

        required_set = set(required_dates)
        all_windows = []
        for series_key, _row in precompute_items:
            planting_week_1, planting_week_2, harvest_back_windows, intermediate_window = (
                ea_pipeline.build_climate_windows(
                    date.fromisoformat(series_key[1]),
                    date.fromisoformat(series_key[2]),
                )
            )
            all_windows.extend([planting_week_1, planting_week_2])
            all_windows.extend((start, end) for _name, start, end in harvest_back_windows)
            if intermediate_window is not None:
                all_windows.append(intermediate_window)
        union_start = min(start for start, _end in all_windows)
        union_end = max(end for _start, end in all_windows)
        self.assertEqual(required_set, set(ea_pipeline.daterange(union_start, union_end)))
        self.assertIn(date(2026, 3, 1), required_set)

    def test_raster_plan_skips_series_already_in_nasa_cache(self) -> None:
        series_items = [
            (
                ("CHC_0p05_R1775C4250", "2026-01-01", "2026-02-28"),
                {"latitude": "1.2498", "longitude": "32.5002"},
            ),
        ]

        with patch(
            "ce_pipeline.phase03.script03.get_nasa_cache_entries",
            return_value={
                ("1.22500", "32.52500", "2026-01-01", "2026-02-28"): {
                    "T2M": {},
                    "PRECTOTCORR": {},
                }
            },
        ), patch(
            "ce_pipeline.phase03.script03.get_daily_climate_cache_range",
            side_effect=AssertionError("series-cache hit must not query daily cache"),
        ):
            precompute_items, required_dates = script03.plan_chc_precompute_series_and_raster_dates(
                series_items,
                None,
                daily_climate_cache_enabled=True,
            )

        self.assertEqual(precompute_items, [])
        self.assertEqual(required_dates, [])

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

    def test_aggregate_metrics_fallback_does_not_recurse_when_window_end_is_missing(self) -> None:
        nasa_series = {
            "T2M": {"20260102": 10.0, "20260103": None},
            "PRECTOTCORR": {"20260102": 2.0},
        }
        original_aggregate = ea_pipeline.aggregate_metrics
        with patch.object(ea_pipeline, "aggregate_metrics", script03.aggregate_metrics_fast):
            metrics = script03.aggregate_metrics_fast(
                nasa_series,
                date(2026, 1, 1),
                date(2026, 1, 3),
            )

        self.assertEqual(metrics, original_aggregate(nasa_series, date(2026, 1, 1), date(2026, 1, 3)))

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
            ), patch(
                "ce_pipeline.phase03.script03.get_nasa_cache_entry", return_value=None
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

    def test_build_chc_daily_values_uses_persisted_samples_without_reading_rasters(self) -> None:
        pixel_id = "CHC_0p05_R1775C4250"
        daily_entries = {
            (pixel_id, "2026-01-01", script03.DAILY_CLIMATE_CACHE_VERSION): {
                "T2M": 20.0,
                "PRECTOTCORR": 1.5,
            },
            (pixel_id, "2026-01-02", script03.DAILY_CLIMATE_CACHE_VERSION): {
                "T2M": None,
                "PRECTOTCORR": None,
            },
        }
        progress: list[tuple[int, int]] = []

        with patch(
            "ce_pipeline.phase03.script03.resolve_phase03_daily_climate_cache_enabled",
            return_value=True,
        ), patch(
            "ce_pipeline.phase03.script03.get_daily_climate_cache_range",
            return_value=daily_entries,
        ), patch(
            "ce_pipeline.phase03.script03._build_daily_raster_plan",
            side_effect=AssertionError("warm daily cache must not resolve raster paths"),
        ):
            daily_values = script03._build_chc_daily_values_for_pixel(
                pixel_id=pixel_id,
                latitude=1.2498,
                longitude=32.5002,
                start_date=date(2026, 1, 1),
                end_date=date(2026, 1, 2),
                progress_callback=lambda processed, total: progress.append((processed, total)),
            )

        self.assertEqual(
            daily_values,
            {"20260101": (20.0, 1.5), "20260102": (None, None)},
        )
        self.assertEqual(progress[-1], (2, 2))

    def test_precompute_chc_series_batches_reuses_pixel_daily_scan_for_multiple_windows(self) -> None:
        from tempfile import TemporaryDirectory

        cache = {}
        sample_calls: list[str] = []
        persisted_entries = {}
        series_items = [
            (
                ("CHC_0p05_R1775C4250", "2026-01-01", "2026-01-03"),
                {
                    "latitude": "1.2498",
                    "longitude": "32.5002",
                    "date_of_planting": "2026-01-01",
                    "date_of_harvesting": "2026-01-03",
                },
            ),
            (
                ("CHC_0p05_R1775C4250", "2026-01-02", "2026-01-03"),
                {
                    "latitude": "1.2498",
                    "longitude": "32.5002",
                    "date_of_planting": "2026-01-02",
                    "date_of_harvesting": "2026-01-03",
                },
            ),
        ]

        def fake_resolve(dataset: str, current_date: date, cache_dir):  # noqa: ANN001
            return Path(f"/tmp/{dataset}-{current_date.isoformat()}.tif")

        def fake_sample(path, **kwargs):  # noqa: ANN001
            sample_calls.append(Path(path).name)
            name = Path(path).name.lower()
            if "chirps" in name:
                return 1.0
            if "tmax" in name:
                return 30.0
            return 10.0

        with patch("ce_pipeline.phase03.script03._resolve_prepared_raster_path", side_effect=fake_resolve), patch(
            "ce_pipeline.phase03.script03._sample_raster_value", side_effect=fake_sample
        ), patch(
            "ce_pipeline.phase03.script03.resolve_phase03_daily_climate_cache_enabled",
            return_value=True,
        ), patch(
            "ce_pipeline.phase03.script03.get_nasa_cache_entry", return_value=None
        ), patch(
            "ce_pipeline.phase03.script03.get_nasa_cache_entries", return_value={}
        ), patch(
            "ce_pipeline.phase03.script03.get_daily_climate_cache_range", return_value={}
        ), patch(
            "ce_pipeline.phase03.script03.upsert_daily_climate_cache_entries",
            side_effect=lambda entries: persisted_daily_entries.update(entries),
        ), patch(
            "ce_pipeline.phase03.script03.upsert_nasa_cache_entries",
            side_effect=lambda entries: persisted_entries.update(entries),
        ):
            persisted_daily_entries = {}
            script03._CHC_PREPARED_RASTER_PATHS = {
                ("chirps", "2026-01-01"): Path("/tmp/chirps-2026-01-01.tif"),
                ("chirts_tmax", "2026-01-01"): Path("/tmp/CHIRTS-ERA5.daily_Tmax.2026.01.01.tif"),
                ("chirts_tmin", "2026-01-01"): Path("/tmp/CHIRTS-ERA5.daily_Tmin.2026.01.01.tif"),
                ("chirps", "2026-01-02"): Path("/tmp/chirps-2026-01-02.tif"),
                ("chirts_tmax", "2026-01-02"): Path("/tmp/CHIRTS-ERA5.daily_Tmax.2026.01.02.tif"),
                ("chirts_tmin", "2026-01-02"): Path("/tmp/CHIRTS-ERA5.daily_Tmin.2026.01.02.tif"),
                ("chirps", "2026-01-03"): Path("/tmp/chirps-2026-01-03.tif"),
                ("chirts_tmax", "2026-01-03"): Path("/tmp/CHIRTS-ERA5.daily_Tmax.2026.01.03.tif"),
                ("chirts_tmin", "2026-01-03"): Path("/tmp/CHIRTS-ERA5.daily_Tmin.2026.01.03.tif"),
            }
            with TemporaryDirectory(prefix="phase03_debug_") as debug_dir:
                stats = script03.precompute_chc_series_batches(
                    series_items,
                    cache,
                    worker_count=2,
                    debug_file=Path(debug_dir) / "phase03.log",
                )

        self.assertEqual(stats["pixel_groups"], 1)
        self.assertEqual(stats["series_materialized"], 2)
        self.assertEqual(len(sample_calls), 9)
        self.assertEqual(len(persisted_daily_entries), 3)
        self.assertEqual(len(persisted_entries), 2)
        self.assertEqual(
            cache[("1.22500", "32.52500", "2026-01-01", "2026-01-03")]["T2M"]["20260101"],
            20.0,
        )
        self.assertEqual(
            cache[("1.22500", "32.52500", "2026-01-02", "2026-01-03")]["PRECTOTCORR"]["20260102"],
            1.0,
        )
        script03._CHC_PREPARED_RASTER_PATHS = {}

    def test_parallel_raster_cache_stays_bounded(self) -> None:
        class DummyImage(script03.Image.Image):
            def __init__(self, path):
                self.path = path
                self.closed = False

            def load(self):
                return self

            def close(self) -> None:
                self.closed = True

        opened_images: list[DummyImage] = []
        script03._clear_thread_raster_image_cache()
        try:
            with patch(
                "ce_pipeline.phase03.script03.resolve_phase03_raster_backend",
                return_value="pil",
            ), patch(
                "ce_pipeline.phase03.script03.Image.open",
                side_effect=lambda path: opened_images.append(DummyImage(path)) or opened_images[-1],
            ):
                for index in range(script03.resolve_phase03_max_open_rasters() + 5):
                    script03._get_raster_cache_entry(Path(f"/tmp/raster-{index}.tif"))

            cache = script03._get_thread_raster_image_cache()
            self.assertLessEqual(len(cache), script03.resolve_phase03_max_open_rasters())
            closed_images = [image for image in opened_images if image.closed]
            self.assertEqual(len(closed_images), 5)
        finally:
            script03._clear_thread_raster_image_cache()

    def test_resolve_raster_path_downloads_once_when_file_is_cached(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp_dir_name:
            cache_dir = Path(tmp_dir_name)
            with patch(
                "ce_pipeline.phase03.script03._download_with_retries",
                side_effect=lambda url, target: target.parent.mkdir(parents=True, exist_ok=True) or target.write_bytes(b"data"),
            ) as download_mock:
                first_path, first_downloaded = script03._resolve_raster_path(
                    "chirps",
                    date(2026, 1, 1),
                    cache_dir,
                )
                second_path, second_downloaded = script03._resolve_raster_path(
                    "chirps",
                    date(2026, 1, 1),
                    cache_dir,
                )

            self.assertEqual(first_path, second_path)
            self.assertTrue(first_downloaded)
            self.assertFalse(second_downloaded)
            self.assertEqual(download_mock.call_count, 1)

    def test_strict_prepared_raster_resolution_fails_without_downloading(self) -> None:
        original_prepared_paths = dict(script03._CHC_PREPARED_RASTER_PATHS)
        original_strict_mode = script03._CHC_STRICT_PREPARED_RASTERS
        script03._CHC_PREPARED_RASTER_PATHS = {}
        script03._CHC_STRICT_PREPARED_RASTERS = True
        try:
            with patch(
                "ce_pipeline.phase03.script03._resolve_raster_path",
                side_effect=AssertionError("strict compute must never download on demand"),
            ), self.assertRaisesRegex(RuntimeError, "prefetch/repair was incomplete"):
                script03._resolve_prepared_raster_path(
                    "chirps",
                    date(2026, 1, 1),
                    Path("/tmp/strict-raster-cache"),
                )
        finally:
            script03._CHC_PREPARED_RASTER_PATHS = original_prepared_paths
            script03._CHC_STRICT_PREPARED_RASTERS = original_strict_mode

    def test_strict_invalid_raster_fails_without_removing_or_redownloading(self) -> None:
        cache_key = ("chirps", "CHC_0p05_R1C2", "2026-01-01")
        original_sample_cache = script03._CHC_PIXEL_DAILY_SAMPLE_CACHE
        original_strict_mode = script03._CHC_STRICT_PREPARED_RASTERS
        script03._CHC_PIXEL_DAILY_SAMPLE_CACHE = {}
        script03._CHC_STRICT_PREPARED_RASTERS = True
        try:
            with patch(
                "ce_pipeline.phase03.script03._sample_raster_value",
                side_effect=OSError("corrupt raster"),
            ), patch(
                "ce_pipeline.phase03.script03._invalidate_and_remove_raster",
                side_effect=AssertionError("strict compute must not remove a raster"),
            ), patch(
                "ce_pipeline.phase03.script03._resolve_raster_path",
                side_effect=AssertionError("strict compute must not redownload a raster"),
            ), self.assertRaisesRegex(RuntimeError, "must repair chirps"):
                script03._sample_chc_dataset_value(
                    "chirps",
                    Path("/tmp/invalid-prepared-chirps.tif"),
                    pixel_id=cache_key[1],
                    current_date=date(2026, 1, 1),
                    latitude=1.0,
                    longitude=32.0,
                    fill_value=-9999.0,
                    latitude_min=-90.0,
                    latitude_max=90.0,
                )
        finally:
            script03._CHC_PIXEL_DAILY_SAMPLE_CACHE = original_sample_cache
            script03._CHC_STRICT_PREPARED_RASTERS = original_strict_mode

    def test_prefetch_repairs_invalid_cached_raster_before_compute(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory(prefix="phase03_prefetch_repair_") as tmp_dir_name:
            cache_dir = Path(tmp_dir_name)
            resolve_counts: dict[str, int] = {}
            validation_calls: list[tuple[str, int]] = []
            progress_reports: list[dict[str, object]] = []

            def fake_resolve(dataset, current_date, _cache_dir):  # noqa: ANN001
                resolve_counts[dataset] = resolve_counts.get(dataset, 0) + 1
                target = cache_dir / dataset / f"{current_date.isoformat()}.tif"
                return target, dataset == "chirps" and resolve_counts[dataset] > 1

            def validate(path, *, dataset, current_date):  # noqa: ANN001
                validation_calls.append((dataset, resolve_counts[dataset]))
                if dataset == "chirps" and resolve_counts[dataset] == 1:
                    raise RuntimeError("invalid cached raster")

            with patch(
                "ce_pipeline.phase03.script03.resolve_shared_chc_cache_dir",
                return_value=cache_dir,
            ), patch(
                "ce_pipeline.phase03.script03._resolve_raster_path",
                side_effect=fake_resolve,
            ), patch(
                "ce_pipeline.phase03.script03._validate_chc_raster_file",
                side_effect=validate,
            ), patch(
                "ce_pipeline.phase03.script03._invalidate_and_remove_raster"
            ), patch(
                "ce_pipeline.phase03.script03.resolve_phase03_worker_limit",
                return_value=1,
            ):
                metadata = script03.prefetch_chc_rasters(
                    [date(2026, 1, 1)],
                    progress_callback=lambda _percent, _stage, _message, details: progress_reports.append(details or {}),
                )

            self.assertEqual(resolve_counts, {"chirps": 2, "chirts_tmax": 1, "chirts_tmin": 1})
            self.assertEqual(metadata["task_total"], 3)
            self.assertEqual(metadata["downloaded"], 1)
            self.assertEqual(metadata["cached"], 2)
            self.assertIn(("chirps", "2026-01-01"), metadata["prepared_raster_paths"])
            self.assertEqual(len(validation_calls), 4)
            self.assertGreaterEqual(metadata["elapsed_seconds"], 0.0)
            self.assertGreaterEqual(metadata["raster_resolve_seconds"], 0.0)
            self.assertGreaterEqual(metadata["raster_validation_seconds"], 0.0)
            self.assertGreaterEqual(metadata["download_resolution_seconds"], 0.0)
            self.assertEqual(progress_reports[-1]["climate_prefetch_tasks_completed"], 3)
            self.assertIn("climate_prefetch_files_per_second", progress_reports[-1])
            self.assertIn("climate_prefetch_eta_seconds", progress_reports[-1])

    def test_validate_chc_raster_file_checks_rasterio_readability(self) -> None:
        class FakeTransform:
            a = 0.05
            e = -0.05

        class FakeDataset:
            count = 1
            width = 10
            height = 10
            transform = FakeTransform()

            def __init__(self):
                self.read_calls = []

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, band, *, window, masked):
                self.read_calls.append((band, window, masked))
                return [[1.0]]

        dataset = FakeDataset()

        class FakeRasterio:
            @staticmethod
            def open(_path):
                return dataset

        with patch(
            "ce_pipeline.phase03.script03.resolve_phase03_raster_backend",
            return_value="rasterio",
        ), patch(
            "ce_pipeline.phase03.script03.rasterio",
            new=FakeRasterio(),
        ), patch(
            "ce_pipeline.phase03.script03.Window",
            new=lambda *args: args,
        ):
            script03._validate_chc_raster_file(
                Path("/tmp/valid-chc-raster.tif"),
                dataset="chirps",
                current_date=date(2026, 1, 1),
            )

        self.assertEqual(len(dataset.read_calls), 1)
        self.assertEqual(dataset.read_calls[0], (1, (0, 0, 1, 1), False))

    def test_validate_chc_raster_file_rejects_tiff_without_geotiff_tags(self) -> None:
        class FakeImage:
            format = "TIFF"
            width = 10
            height = 10
            tag_v2 = {}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def verify(self):
                raise AssertionError("invalid geotiff should fail before verify")

        with patch(
            "ce_pipeline.phase03.script03.resolve_phase03_raster_backend",
            return_value="pil",
        ), patch(
            "ce_pipeline.phase03.script03.Image.open",
            return_value=FakeImage(),
        ), self.assertRaisesRegex(RuntimeError, "Invalid CHC climate raster"):
            script03._validate_chc_raster_file(
                Path("/tmp/missing-geotags.tif"),
                dataset="chirps",
                current_date=date(2026, 1, 1),
            )

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

        def fake_resolve(latitude, longitude, *, payload, lookup_shared_cache=True):  # noqa: ANN001
            calls.append((latitude, longitude))
            return ({
                "Soil type/texture": "Loam",
                "Soil Depth (cm)-How deep do you expect maize roots to grow in this soil?": "100cm o mas",
                "soil_source": "soilgrids",
                "soil_texture_usda_class": "Loam",
            }, "soilgrids", True)

        with patch.dict("os.environ", {"APP_PHASE03_SOIL_PROVIDER": "rest"}), patch("ce_pipeline.phase03.script03.soil_enrichment.load_cache_payload", return_value={}), patch(
            "ce_pipeline.phase03.script03.soil_enrichment.write_cache_payload"
        ), patch(
            "ce_pipeline.phase03.script03.soil_enrichment.resolve_soil_record_from_payload",
            side_effect=fake_resolve,
        ):
            with patch.object(script03.soil_enrichment, "get_soil_cache_entries", return_value={}), patch.object(
                script03.soil_enrichment, "upsert_soil_cache_entries",
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
