#!/usr/bin/env python3
"""Isolated local benchmark for Phase03 raster vs daily-SQLite sampling.

Stages hard links to the rasters used by a completed Phase03 run into a new
APP_RUNTIME_DIR, then compares three compute passes: raster-only, daily-cache
population, and daily-cache hot. It intentionally bypasses feature/NASA-series
caches so those cannot hide the raster/daily-cache work being measured.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import sqlite3
import sys
import tempfile
import threading
import time
from datetime import date
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from config_env import resolve_runtime_root

DATASETS = ("chirps", "chirts_tmax", "chirts_tmin")
DEFAULT_RUN_DIR = (
    Path.home()
    / ".local/share/MictlanAgriXGBoost/pipeline_runs/20260826-162146-8d184287"
    / "ce_pipeline_prediction/phase03"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--phase03-dir",
        type=Path,
        default=DEFAULT_RUN_DIR,
        help="Directory containing dataInput.csv, phase03prediction_log.json, and output.csv.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=0,
        help="Compute workers; default is the count recorded in the reference run.",
    )
    parser.add_argument(
        "--reuse-sandbox",
        type=Path,
        default=None,
        help="Reuse an existing phase03-daily-cache-benchmark-* sandbox directory.",
    )
    parser.add_argument(
        "--reset-sandbox-daily-cache",
        action="store_true",
        help="Delete daily-cache rows only from the explicitly selected benchmark sandbox DB.",
    )
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def prepare_sandbox(
    *,
    source_chc_cache: Path,
    sandbox_runtime: Path,
    required_dates: list[date],
    script03,
) -> tuple[dict[tuple[str, str], Path], dict[str, int]]:
    target_chc_cache = sandbox_runtime / "cache" / "chc_climate"
    target_chc_cache.mkdir(parents=True, exist_ok=True)
    if os.stat(source_chc_cache).st_dev != os.stat(target_chc_cache).st_dev:
        raise RuntimeError(
            "Benchmark sandbox and raster cache are on different filesystems; "
            "hard links are unavailable, and the script will not copy the 56+ GiB raster set."
        )

    prepared_paths: dict[tuple[str, str], Path] = {}
    linked_files = 0
    existing_links = 0
    total_bytes = 0
    missing_sources: list[str] = []
    for current_date in required_dates:
        for dataset in DATASETS:
            source_path, _url = script03._resolve_raster_request(dataset, current_date, source_chc_cache)
            target_path, _target_url = script03._resolve_raster_request(dataset, current_date, target_chc_cache)
            if not source_path.is_file():
                missing_sources.append(str(source_path))
                continue
            target_path.parent.mkdir(parents=True, exist_ok=True)
            if target_path.exists():
                existing_links += 1
            else:
                os.link(source_path, target_path)
                linked_files += 1
            total_bytes += source_path.stat().st_size
            prepared_paths[(dataset, current_date.isoformat())] = target_path

    if missing_sources:
        raise FileNotFoundError(
            f"{len(missing_sources)} required local rasters are missing; no network fallback is allowed. "
            f"Examples: {missing_sources[:5]}"
        )
    return prepared_paths, {
        "linked_files": linked_files,
        "already_staged_files": existing_links,
        "raster_file_count": len(prepared_paths),
        "raster_bytes_logical": total_bytes,
    }


def compare_climate_outputs(
    *,
    input_rows: list[dict[str, str]],
    reference_rows: list[dict[str, str]],
    output_by_series: dict[tuple[str, str, str], dict[str, str]],
    climate_columns: list[str],
    script03,
    tolerance: float = 1e-6,
) -> dict[str, Any]:
    expected_by_series: dict[tuple[str, str, str], dict[str, str]] = {}
    for input_row, reference_row in zip(input_rows, reference_rows):
        expected_by_series.setdefault(script03.build_climate_series_key(input_row), reference_row)

    mismatches = []
    comparisons = 0
    for series_key, actual_row in output_by_series.items():
        reference_row = expected_by_series.get(series_key)
        if reference_row is None:
            mismatches.append({"series": series_key, "error": "missing reference row"})
            continue
        for column in climate_columns:
            expected = str(reference_row.get(column, "") or "").strip()
            actual = str(actual_row.get(column, "") or "").strip()
            comparisons += 1
            if expected == actual:
                continue
            if not expected or not actual:
                mismatches.append({"series": series_key, "column": column, "expected": expected, "actual": actual})
            else:
                try:
                    if not math.isclose(float(expected), float(actual), rel_tol=0.0, abs_tol=tolerance):
                        mismatches.append({"series": series_key, "column": column, "expected": expected, "actual": actual})
                except ValueError:
                    mismatches.append({"series": series_key, "column": column, "expected": expected, "actual": actual})
            if len(mismatches) >= 20:
                break
        if len(mismatches) >= 20:
            break
    return {
        "climate_value_comparisons": comparisons,
        "mismatch_count_sampled": len(mismatches),
        "mismatches": mismatches,
        "tolerance": tolerance,
    }


def main() -> int:
    args = parse_args()
    phase03_dir = args.phase03_dir.expanduser().resolve()
    source_runtime = resolve_runtime_root()
    if not phase03_dir.is_dir():
        raise FileNotFoundError(f"Phase03 reference directory not found: {phase03_dir}")

    if args.reuse_sandbox is not None:
        benchmark_runtime = args.reuse_sandbox.expanduser().resolve()
        if (
            benchmark_runtime.parent != source_runtime.resolve()
            or not benchmark_runtime.name.startswith("phase03-daily-cache-benchmark-")
        ):
            raise ValueError("--reuse-sandbox must be a direct phase03-daily-cache-benchmark-* child of APP_RUNTIME_DIR.")
        if not benchmark_runtime.is_dir():
            raise FileNotFoundError(f"Benchmark sandbox does not exist: {benchmark_runtime}")
    else:
        benchmark_runtime = Path(
            tempfile.mkdtemp(prefix="phase03-daily-cache-benchmark-", dir=source_runtime)
        ).resolve()
    # The override is set before importing Phase03/shared_cache so all SQLite and
    # CHC path resolution in this process is confined to the new sandbox.
    os.environ["APP_RUNTIME_DIR"] = str(benchmark_runtime)
    os.environ["APP_PHASE03_DAILY_CLIMATE_CACHE_ENABLED"] = "0"

    from ce_pipeline.phase03 import script03
    from preprocess import ea_pipeline
    from unittest.mock import patch

    sandbox_db_path = benchmark_runtime / "cache" / "shared_cache.sqlite3"
    if args.reset_sandbox_daily_cache:
        if args.reuse_sandbox is None or not sandbox_db_path.is_file():
            raise ValueError("Sandbox cache reset requires an existing explicitly selected benchmark sandbox DB.")
        with sqlite3.connect(sandbox_db_path) as connection:
            connection.execute("DELETE FROM daily_climate_cache")

    if script03.rasterio is None:
        raise RuntimeError("Rasterio is required for this benchmark; PIL would load full global rasters.")

    input_rows = load_csv(phase03_dir / "dataInput.csv")
    reference_rows = load_csv(phase03_dir / "output.csv")
    phase_log = json.loads((phase03_dir / "phase03prediction_log.json").read_text(encoding="utf-8"))
    climate_override = phase_log.get("climate_override", {})
    grouped_rows, _row_series_keys = script03.build_climate_series_groups(input_rows)
    representative_items = list(
        (series_key, rows[0]) for series_key, rows in grouped_rows.items()
    )
    precompute_items = script03.build_forecast_reference_precompute_series_items(
        representative_items,
        climate_override,
    )
    required_dates_by_pixel = script03.collect_required_chc_dates_for_series_items(precompute_items)
    all_required_dates = sorted(
        {current_date for pixel_dates in required_dates_by_pixel.values() for current_date in pixel_dates}
    )

    source_chc_cache = source_runtime / "cache" / "chc_climate"
    prepared_paths, staged_stats = prepare_sandbox(
        source_chc_cache=source_chc_cache,
        sandbox_runtime=benchmark_runtime,
        required_dates=all_required_dates,
        script03=script03,
    )

    # Validate staged links read-only before timing. If validation fails, do not
    # repair/delete or download anything; the source cache remains untouched.
    validation_started = time.monotonic()
    for (dataset, date_text), path in prepared_paths.items():
        script03._validate_chc_raster_file(
            path,
            dataset=dataset,
            current_date=date.fromisoformat(date_text),
        )
    staged_stats["raster_validation_seconds"] = round(time.monotonic() - validation_started, 3)

    worker_count = args.workers or int(phase_log.get("nasa", {}).get("parallel_workers", 4) or 4)
    climate_columns = [
        column
        for column in ea_pipeline.build_output_columns()
        if column not in ea_pipeline.CLIMATE_ID_COLUMNS
    ]
    effective_override = dict(climate_override)
    if str(effective_override.get("climate_scope") or "").strip() in {
        "country_localities",
        "regional_manual",
    }:
        effective_override["climate_scope"] = "point"

    original_sample = script03._sample_raster_value
    original_prepared_paths = dict(script03._CHC_PREPARED_RASTER_PATHS)
    original_strict_mode = script03._CHC_STRICT_PREPARED_RASTERS
    output_by_series_by_case: dict[str, dict[tuple[str, str, str], dict[str, str]]] = {}
    runs: dict[str, dict[str, Any]] = {}

    def execute_case(label: str, *, daily_cache_enabled: bool) -> dict[str, Any]:
        os.environ["APP_PHASE03_DAILY_CLIMATE_CACHE_ENABLED"] = "1" if daily_cache_enabled else "0"
        script03._CHC_PREPARED_RASTER_PATHS = prepared_paths
        script03._CHC_STRICT_PREPARED_RASTERS = True
        script03._clear_chc_pixel_daily_sample_cache()
        script03._clear_raster_pixel_index_cache()
        sample_count = 0
        sample_count_lock = threading.Lock()

        def counted_sample(*sample_args, **sample_kwargs):
            nonlocal sample_count
            with sample_count_lock:
                sample_count += 1
            return original_sample(*sample_args, **sample_kwargs)

        script03._sample_raster_value = counted_sample
        cache: dict[tuple[str, str, str, str], dict[str, dict[str, float | None]]] = {}
        persisted_series = {}
        cache_stats = {"cache_hits": 0, "cache_misses": 0}
        wall_started = time.monotonic()
        cpu_started = time.process_time()
        with patch.object(script03, "append_phase03_debug_log"), patch.object(
            script03, "get_nasa_cache_entries", return_value={}
        ), patch.object(
            script03, "get_nasa_cache_entry", side_effect=lambda key: persisted_series.get(key)
        ), patch.object(script03, "upsert_nasa_cache_entries", side_effect=lambda entries: persisted_series.update(entries)):
            batch_stats = script03.precompute_chc_series_batches(
                precompute_items,
                cache,
                worker_count=worker_count,
                debug_file=benchmark_runtime / f"{label}.debug.log",
            )
            output_by_series: dict[tuple[str, str, str], dict[str, str]] = {}
            with patch.object(ea_pipeline, "fetch_nasa_series", script03.fetch_chc_series), patch.object(
                ea_pipeline,
                "aggregate_metrics",
                script03.aggregate_metrics_fast,
            ):
                for series_key, row in representative_items:
                    output_row, _audit_row = ea_pipeline.build_output_row(
                        row,
                        cache,
                        cache_path=None,
                        climate_override=effective_override,
                        cache_stats=cache_stats,
                    )
                    output_by_series[series_key] = output_row
        elapsed = max(0.0, time.monotonic() - wall_started)
        cpu_seconds = max(0.0, time.process_time() - cpu_started)
        script03._sample_raster_value = original_sample
        output_by_series_by_case[label] = output_by_series
        result = {
            "wall_seconds": round(elapsed, 3),
            "process_cpu_seconds": round(cpu_seconds, 3),
            "raster_pixel_sample_calls": sample_count,
            "series_cache_hits": cache_stats["cache_hits"],
            "series_cache_misses": cache_stats["cache_misses"],
            **batch_stats,
        }
        result["output_comparison"] = compare_climate_outputs(
            input_rows=input_rows,
            reference_rows=reference_rows,
            output_by_series=output_by_series,
            climate_columns=climate_columns,
            script03=script03,
        )
        return result

    try:
        # Raster-only control, then one daily-cache population run, then the
        # measured warm-cache run. The NASA series cache is bypassed in each pass.
        runs["raster_only_control"] = execute_case("raster-only-control", daily_cache_enabled=False)
        runs["daily_cache_population"] = execute_case("daily-cache-population", daily_cache_enabled=True)
        runs["daily_cache_hot"] = execute_case("daily-cache-hot", daily_cache_enabled=True)
    finally:
        script03._sample_raster_value = original_sample
        script03._CHC_PREPARED_RASTER_PATHS = original_prepared_paths
        script03._CHC_STRICT_PREPARED_RASTERS = original_strict_mode

    with sqlite3.connect(sandbox_db_path) as connection:
        daily_cache_rows = connection.execute(
            "SELECT COUNT(*) FROM daily_climate_cache WHERE cache_version = ?",
            (script03.DAILY_CLIMATE_CACHE_VERSION,),
        ).fetchone()[0]

    baseline_prediction = phase03_dir.parent / "prediction.csv"
    summary = {
        "phase03_reference_dir": str(phase03_dir),
        "sandbox_runtime_dir": str(benchmark_runtime),
        "source_chc_cache_dir": str(source_chc_cache),
        "raster_staging": staged_stats,
        "run_shape": {
            "data_input_rows": len(input_rows),
            "unique_climate_series": len(grouped_rows),
            "precompute_series": len(precompute_items),
            "unique_pixels": len(required_dates_by_pixel),
            "unique_raster_dates": len(all_required_dates),
            "required_raster_files": len(prepared_paths),
            "worker_count": worker_count,
        },
        "daily_cache_rows_after_runs": daily_cache_rows,
        "runs": runs,
        "reference_prediction_csv_sha256": sha256(baseline_prediction) if baseline_prediction.is_file() else None,
        "prediction_recomputed": False,
        "network_downloads": 0,
        "notes": [
            "The benchmark directly exercises precompute_chc_series_batches and climate-window aggregation.",
            "Feature cache is bypassed; NASA series cache reads/writes are disabled for every pass.",
            "Rasters are hard-linked into the isolated sandbox; workers run strict and cannot download or delete them.",
            "Phase04 predictions are not recomputed; compare the unchanged baseline prediction after climate-output parity passes.",
        ],
    }
    result_path = benchmark_runtime / "phase03_daily_cache_benchmark.json"
    result_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Benchmark summary: {result_path}")
    return 0 if all(
        run["output_comparison"]["mismatch_count_sampled"] == 0 for run in runs.values()
    ) else 2


if __name__ == "__main__":
    raise SystemExit(main())
