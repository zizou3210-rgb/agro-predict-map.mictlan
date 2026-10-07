"""Compare scalar and batched reads using existing rasters and an isolated cache."""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ce_pipeline.phase03 import script03
from preprocess import ea_pipeline


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-csv", required=True, type=Path)
    parser.add_argument("--pixels", type=int, default=64)
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--start", type=date.fromisoformat, default=date(2021, 4, 7))
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.pixels <= 128 or args.days < 60 or args.workers < 1:
        parser.error("Use 1–128 pixels, at least 60 days and at least one worker.")
    end = args.start + timedelta(days=args.days-1)
    rows = {}
    with args.input_csv.open() as handle:
        for row in csv.DictReader(handle):
            pixel_id, _, _ = script03.resolve_chc_pixel_metadata(float(row["latitude"]), float(row["longitude"]))
            row["date_of_planting"], row["date_of_harvesting"] = args.start.isoformat(), end.isoformat()
            rows.setdefault(pixel_id, row)
            if len(rows) == args.pixels:
                break
    items = [((pixel_id, args.start.isoformat(), end.isoformat()), row) for pixel_id, row in rows.items()]
    paths = {}
    source_cache = script03.resolve_shared_chc_cache_dir()
    for day in script03._iter_dates_inclusive(args.start, end):
        for dataset in ("chirps", "chirts_tmax", "chirts_tmin"):
            path = script03._resolve_raster_request(dataset, day, source_cache)[0]
            if not path.is_file():
                raise FileNotFoundError(f"Benchmark refuses downloads; missing {path}")
            paths[(dataset, day.isoformat())] = path
    runs = {}
    outputs = {}
    original_get_value = script03._get_raster_pixel_value
    original_get_entry = script03._get_raster_cache_entry
    original_sample_batch = script03._sample_raster_pixel_batch
    with tempfile.TemporaryDirectory(prefix="chc-block-benchmark-") as runtime, patch.dict(os.environ, {"APP_RUNTIME_DIR": runtime}), \
         patch.object(script03, "_CHC_PREPARED_RASTER_PATHS", paths), \
         patch.object(script03, "_CHC_STRICT_PREPARED_RASTERS", True):
        for label, enabled in (("scalar", False), ("batch_cold", True), ("batch_warm", True)):
            os.environ["APP_PHASE03_DAILY_CLIMATE_CACHE_ENABLED"] = "1" if enabled else "0"
            script03._clear_chc_pixel_daily_sample_cache()
            script03._CHC_SERIES_AGGREGATION_CACHE.clear()
            script03._CHC_WINDOW_METRICS_CACHE.clear()
            counters = {"scalar_pixel_reads": 0, "batch_source_calls": 0, "raster_opens": 0}

            def scalar_read(*a, **kw):
                counters["scalar_pixel_reads"] += 1
                return original_get_value(*a, **kw)

            def raster_entry(path):
                if path not in script03._get_thread_raster_image_cache():
                    counters["raster_opens"] += 1
                return original_get_entry(path)

            def batch_read(*a, **kw):
                counters["batch_source_calls"] += 1
                return original_sample_batch(*a, **kw)

            cache = {}
            started = time.monotonic()
            # Each pass excludes the series cache so the warm run specifically
            # measures daily-cache reuse, rather than reusing final features.
            with patch.object(script03, "get_nasa_cache_entries", return_value={}), \
                 patch.object(script03, "upsert_nasa_cache_entries"), \
                 patch.object(script03, "_get_raster_pixel_value", side_effect=scalar_read), \
                 patch.object(script03, "_get_raster_cache_entry", side_effect=raster_entry), \
                 patch.object(script03, "_sample_raster_pixel_batch", side_effect=batch_read), \
                 patch.object(ea_pipeline, "fetch_nasa_series", script03.fetch_chc_series), \
                 patch.object(ea_pipeline, "aggregate_metrics", script03.aggregate_metrics_fast):
                stats = script03.precompute_chc_series_batches(items, cache, worker_count=args.workers, debug_file=None)
                outputs[label] = [ea_pipeline.build_output_row(row, cache, cache_path=None)[0] for _, row in items]
            runs[label] = {"seconds": round(time.monotonic()-started, 3), **counters, "stats": stats}
            print(json.dumps({label: runs[label]}), flush=True)
    for label in ("batch_cold", "batch_warm"):
        if outputs[label] != outputs["scalar"]:
            raise AssertionError(f"Climate output differs in {label}")
    report = {"pixels": len(rows), "days": args.days, "workers": args.workers,
              "climate_outputs_identical": True, "downloads": 0, "runs": runs,
              "cold_speedup": runs["scalar"]["seconds"]/max(runs["batch_cold"]["seconds"], 0.001)}
    args.output.write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
