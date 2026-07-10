#!/usr/bin/env python3
from __future__ import annotations

if __package__ in {None, ""}:
    import sys
    from pathlib import Path

    APP_BOOT_DIR = Path(__file__).resolve().parents[2]
    PACKAGE_PARENT = APP_BOOT_DIR
    if str(PACKAGE_PARENT) not in sys.path:
        sys.path.insert(0, str(PACKAGE_PARENT))

import argparse
import importlib.util
import json
import math
import os
import shutil
import ssl
import sys
import time
from collections import OrderedDict
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, as_completed, wait
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from threading import Lock, RLock
from typing import Callable
from urllib.request import Request, urlopen

import certifi
from PIL import Image

from preprocess import ea_pipeline, soil_enrichment
from pipeline.nasa_country_region import build_manual_grid_cells

PHASE01_SCRIPT = Path(__file__).resolve().parents[1] / "phase01" / "phase1.py"
SOIL_TEXTURE_HEADER = soil_enrichment.SOIL_TEXTURE_HEADER
SOIL_DEPTH_HEADER = soil_enrichment.SOIL_DEPTH_HEADER
LAT_HEADER = soil_enrichment.LAT_HEADER
LON_HEADER = soil_enrichment.LON_HEADER
CE_ROW_ID_HEADER = "CE Row ID"
CE_MERGE_KEY_HEADERS = [
    ea_pipeline.TRIAL_SERIES_HEADER,
    "Site Number",
    "Plot",
    "EntryCode",
]
ProgressCallback = Callable[[int | float, str, str, dict[str, object] | None], None]


def prepare_ce_row_merge_keys(
    headers: list[str],
    records: list[dict[str, object]],
) -> tuple[list[str], list[dict[str, object]], dict[str, bool]]:
    prepared_headers = list(headers)
    existing_headers = set(headers)
    merge_header_presence = {header: header in existing_headers for header in CE_MERGE_KEY_HEADERS}

    if CE_ROW_ID_HEADER not in prepared_headers:
        prepared_headers.append(CE_ROW_ID_HEADER)

    backup_headers: list[str] = []
    for merge_header in CE_MERGE_KEY_HEADERS:
        backup_header = f"Original {merge_header}"
        if merge_header in existing_headers and backup_header not in prepared_headers:
            prepared_headers.append(backup_header)
            backup_headers.append(backup_header)
        if merge_header not in prepared_headers:
            prepared_headers.append(merge_header)

    prepared_records: list[dict[str, object]] = []
    for index, record in enumerate(records, start=1):
        updated = dict(record)
        row_id = str(index)
        updated[CE_ROW_ID_HEADER] = row_id
        for merge_header in CE_MERGE_KEY_HEADERS:
            backup_header = f"Original {merge_header}"
            if merge_header in existing_headers:
                updated[backup_header] = record.get(merge_header, "")
            updated[merge_header] = row_id
        prepared_records.append(updated)

    cleanup_metadata = {
        "merge_header_presence": merge_header_presence,
        "backup_headers": backup_headers,
    }
    return prepared_headers, prepared_records, cleanup_metadata


def restore_ce_row_merge_keys(
    headers: list[str],
    records: list[dict[str, object]],
    cleanup_metadata: dict[str, object],
) -> tuple[list[str], list[dict[str, object]]]:
    merge_header_presence = cleanup_metadata.get("merge_header_presence", {}) if isinstance(cleanup_metadata, dict) else {}
    backup_headers = cleanup_metadata.get("backup_headers", []) if isinstance(cleanup_metadata, dict) else []

    restored_records: list[dict[str, object]] = []
    for record in records:
        updated = dict(record)
        for merge_header in CE_MERGE_KEY_HEADERS:
            backup_header = f"Original {merge_header}"
            if bool(merge_header_presence.get(merge_header)):
                updated[merge_header] = updated.get(backup_header, "")
            else:
                updated.pop(merge_header, None)
            updated.pop(backup_header, None)
        restored_records.append(updated)

    restored_headers: list[str] = []
    for header in headers:
        if header in backup_headers:
            continue
        if header in CE_MERGE_KEY_HEADERS and not bool(merge_header_presence.get(header)):
            continue
        restored_headers.append(header)
    return restored_headers, restored_records


def resolve_runtime_root() -> Path:
    override = os.environ.get("APP_RUNTIME_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()

    home = Path.home()
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
        if local_app_data:
            return Path(local_app_data) / "MictlanAgriXGBoost"
        return home / "AppData" / "Local" / "MictlanAgriXGBoost"

    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "MictlanAgriXGBoost"

    xdg_data_home = os.environ.get("XDG_DATA_HOME", "").strip()
    # When the app is launched from the Snap-packaged editor, XDG_DATA_HOME points
    # into a snap-scoped directory. Use the regular home cache instead so phase03
    # reuses the same climate cache across launch contexts.
    if xdg_data_home and "/snap/code/" in xdg_data_home:
        return home / ".local" / "share" / "MictlanAgriXGBoost"
    if xdg_data_home:
        return Path(xdg_data_home).expanduser() / "MictlanAgriXGBoost"
    return home / ".local" / "share" / "MictlanAgriXGBoost"


def resolve_shared_nasa_cache_path() -> Path:
    return resolve_runtime_root() / "cache" / "nasa_power_cache.json"


def resolve_shared_climate_feature_cache_path() -> Path:
    return resolve_runtime_root() / "cache" / "climate_feature_cache.json"


def resolve_shared_soil_cache_path() -> Path:
    return resolve_runtime_root() / "cache" / "soilgrids_cache.json"


CHIRPS_DAILY_URL_TEMPLATE = (
    "https://data.chc.ucsb.edu/products/CHIRPS/v3.0/daily/final/rnl/"
    "{year}/chirps-v3.0.rnl.{year}.{month:02d}.{day:02d}.tif"
)
CHIRTS_ERA5_TMAX_URL_TEMPLATE = (
    "https://data.chc.ucsb.edu/experimental/CHIRTS-ERA5/tmax/tifs/daily/"
    "{year}/CHIRTS-ERA5.daily_Tmax.{year}.{month:02d}.{day:02d}.tif"
)
CHIRTS_ERA5_TMIN_URL_TEMPLATE = (
    "https://data.chc.ucsb.edu/experimental/CHIRTS-ERA5/tmin/tifs/daily/"
    "{year}/CHIRTS-ERA5.daily_Tmin.{year}.{month:02d}.{day:02d}.tif"
)
CHIRPS_FILL_VALUE = -9999.0
CHIRTS_FILL_VALUE = -9999.0
CHIRPS_MIN_LATITUDE = -60.0
CHIRPS_MAX_LATITUDE = 60.0
CHIRTS_MIN_LATITUDE = -60.0
CHIRTS_MAX_LATITUDE = 70.0
MAX_OPEN_RASTERS = 12
CHC_GRID_STEP_DEGREES = 0.05
CLIMATE_PIXEL_ID_HEADER = "Climate Pixel ID"
_RASTER_IMAGE_CACHE: OrderedDict[Path, Image.Image] = OrderedDict()
_RASTER_METADATA_CACHE: dict[Path, tuple[float, float, float, float, int, int]] = {}
_RASTER_CACHE_LOCK = RLock()
_CHC_DOWNLOAD_PROGRESS_HOOK: Callable[[str, int, int, bool], None] | None = None
_CHC_DOWNLOAD_PROGRESS_STATE: dict[str, int] = {"series_total": 0, "series_completed": 0, "series_total_days": 0, "download_max_processed_days": 0, "compute_max_processed_days": 0}
_CHC_SERIES_AGGREGATION_CACHE: dict[int, dict[str, object]] = {}
_CHC_WINDOW_METRICS_CACHE: dict[tuple[int, str, str], dict[str, float | None]] = {}
_CHC_PREPARED_RASTER_PATHS: dict[tuple[str, str], Path] = {}
_CHC_PARALLEL_PROGRESS_MODE = False
_CHC_PARALLEL_PROGRESS_LOCK = Lock()
_CHC_PARALLEL_PROGRESS_CONTEXT: dict[str, object] = {
    "progress_file": None,
    "progress_callback": None,
    "skip_soil_enrichment": True,
    "worker_count": 0,
    "series_total": 0,
    "series_progress": {},
    "last_report_at": 0.0,
}


def resolve_shared_chc_cache_dir() -> Path:
    return resolve_runtime_root() / "cache" / "chc_climate"


def resolve_phase03_worker_limit(kind: str, series_total: int) -> int:
    env_name = "APP_PHASE03_PREFETCH_MAX_WORKERS" if kind == "prefetch" else "APP_PHASE03_COMPUTE_MAX_WORKERS"
    raw_value = str(os.environ.get(env_name, "")).strip()
    if raw_value:
        try:
            configured = max(1, int(raw_value))
        except ValueError:
            configured = 1
        return max(1, min(configured, max(series_total, 1)))

    if sys.platform == "darwin":
        default_limit = 2 if kind == "prefetch" else 1
    else:
        default_limit = 6 if kind == "prefetch" else 4
    return max(1, min(default_limit, max(series_total, 1)))


def resolve_chc_pixel_metadata(latitude: float, longitude: float) -> tuple[str, float, float]:
    clamped_latitude = min(max(latitude, -89.999999), 89.999999)
    clamped_longitude = min(max(longitude, -179.999999), 179.999999)
    row_index = int(math.floor((90.0 - clamped_latitude) / CHC_GRID_STEP_DEGREES))
    column_index = int(math.floor((clamped_longitude + 180.0) / CHC_GRID_STEP_DEGREES))
    center_latitude = round(90.0 - ((row_index + 0.5) * CHC_GRID_STEP_DEGREES), 5)
    center_longitude = round(-180.0 + ((column_index + 0.5) * CHC_GRID_STEP_DEGREES), 5)
    pixel_id = f"CHC_0p05_R{row_index}C{column_index}"
    return pixel_id, center_latitude, center_longitude


def estimate_unique_climate_series_total(
    records: list[dict[str, object]],
) -> int:
    unique_series_keys: set[tuple[str, str, str]] = set()
    for record in records:
        planting_value = str(
            record.get(ea_pipeline.DATE_PLANTING_HEADER)
            or record.get("date_of_planting")
            or ""
        ).strip()
        harvesting_value = str(
            record.get(ea_pipeline.DATE_HARVESTING_HEADER)
            or record.get("date_of_harvesting")
            or ""
        ).strip()
        latitude_raw = record.get(ea_pipeline.LAT_HEADER, record.get("latitude"))
        longitude_raw = record.get(ea_pipeline.LON_HEADER, record.get("longitude"))
        if not planting_value or not harvesting_value:
            continue
        try:
            latitude = float(latitude_raw)
            longitude = float(longitude_raw)
        except (TypeError, ValueError):
            continue
        pixel_id, _, _ = resolve_chc_pixel_metadata(latitude, longitude)
        unique_series_keys.add((pixel_id, planting_value, harvesting_value))
    return max(1, len(unique_series_keys))


def build_climate_series_key(row: dict[str, object]) -> tuple[str, str, str]:
    planting_value = str(
        row.get(ea_pipeline.DATE_PLANTING_HEADER)
        or row.get("date_of_planting")
        or ""
    ).strip()
    harvesting_value = str(
        row.get(ea_pipeline.DATE_HARVESTING_HEADER)
        or row.get("date_of_harvesting")
        or ""
    ).strip()
    latitude_raw = row.get(ea_pipeline.LAT_HEADER, row.get("latitude"))
    longitude_raw = row.get(ea_pipeline.LON_HEADER, row.get("longitude"))
    latitude = float(latitude_raw)
    longitude = float(longitude_raw)
    pixel_id, _, _ = resolve_chc_pixel_metadata(latitude, longitude)
    return pixel_id, planting_value, harvesting_value


def serialize_climate_series_key(series_key: tuple[str, str, str]) -> str:
    return "|".join(series_key)


def load_climate_feature_cache(path: Path) -> dict[str, dict[str, object]]:
    raw_payload = ea_pipeline.load_json_file(path, default={})
    if not isinstance(raw_payload, dict):
        return {}
    cache: dict[str, dict[str, object]] = {}
    for key, value in raw_payload.items():
        if not isinstance(key, str) or not isinstance(value, dict):
            continue
        cache[key] = value
    return cache


def save_climate_feature_cache(path: Path, cache: dict[str, dict[str, object]]) -> None:
    ea_pipeline.save_json_file(path, cache)


def _resolve_raster_request(dataset: str, current_date: date, cache_dir: Path) -> tuple[Path, str]:
    dataset_dir = cache_dir / dataset / str(current_date.year)
    if dataset == 'chirps':
        filename = f'chirps-v3.0.rnl.{current_date.year}.{current_date.month:02d}.{current_date.day:02d}.tif'
        url = CHIRPS_DAILY_URL_TEMPLATE.format(year=current_date.year, month=current_date.month, day=current_date.day)
    elif dataset == 'chirts_tmax':
        filename = f'CHIRTS-ERA5.daily_Tmax.{current_date.year}.{current_date.month:02d}.{current_date.day:02d}.tif'
        url = CHIRTS_ERA5_TMAX_URL_TEMPLATE.format(year=current_date.year, month=current_date.month, day=current_date.day)
    elif dataset == 'chirts_tmin':
        filename = f'CHIRTS-ERA5.daily_Tmin.{current_date.year}.{current_date.month:02d}.{current_date.day:02d}.tif'
        url = CHIRTS_ERA5_TMIN_URL_TEMPLATE.format(year=current_date.year, month=current_date.month, day=current_date.day)
    else:
        raise ValueError(f'Unsupported raster dataset: {dataset}')
    return dataset_dir / filename, url


def _build_ssl_context() -> ssl.SSLContext:
    return ssl.create_default_context(cafile=certifi.where())


def _download_with_retries(url: str, target_path: Path) -> None:
    last_error: Exception | None = None
    request = Request(url, headers={"User-Agent": "cimmyt_app ce_pipeline climate"})
    ssl_context = _build_ssl_context()
    for attempt in range(1, ea_pipeline.MAX_RETRIES + 1):
        try:
            with urlopen(request, timeout=ea_pipeline.HTTP_TIMEOUT_SECONDS, context=ssl_context) as response:
                payload = response.read()
            target_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = target_path.with_suffix(target_path.suffix + '.tmp')
            temp_path.write_bytes(payload)
            temp_path.replace(target_path)
            return
        except Exception as exc:  # pragma: no cover - network dependent
            last_error = exc
            if attempt == ea_pipeline.MAX_RETRIES:
                break
            sleep_seconds = min(
                ea_pipeline.RETRY_SLEEP_SECONDS * (2 ** (attempt - 1)),
                ea_pipeline.MAX_RETRY_SLEEP_SECONDS,
            )
            import time
            time.sleep(sleep_seconds)
    raise RuntimeError(f'Could not download climate raster: {url}') from last_error


def _resolve_raster_path(dataset: str, current_date: date, cache_dir: Path) -> tuple[Path, bool]:
    target_path, url = _resolve_raster_request(dataset, current_date, cache_dir)
    downloaded = False
    if not target_path.exists():
        _download_with_retries(url, target_path)
        downloaded = True
    return target_path, downloaded


def _resolve_prepared_raster_path(dataset: str, current_date: date, cache_dir: Path) -> Path:
    prepared = _CHC_PREPARED_RASTER_PATHS.get((dataset, current_date.isoformat()))
    if prepared is not None:
        return prepared
    target_path, _ = _resolve_raster_request(dataset, current_date, cache_dir)
    return target_path


def _get_raster_image(path: Path) -> Image.Image:
    with _RASTER_CACHE_LOCK:
        cached = _RASTER_IMAGE_CACHE.get(path)
        if cached is not None:
            _RASTER_IMAGE_CACHE.move_to_end(path)
            return cached
        image = Image.open(path)
        _RASTER_IMAGE_CACHE[path] = image
        _RASTER_IMAGE_CACHE.move_to_end(path)
        # During parallel climate processing, avoid evicting shared PIL handles
        # that may still be in use by another worker.
        if not _CHC_PARALLEL_PROGRESS_MODE:
            while len(_RASTER_IMAGE_CACHE) > MAX_OPEN_RASTERS:
                _, old_image = _RASTER_IMAGE_CACHE.popitem(last=False)
                old_image.close()
        return image


def _get_raster_metadata(path: Path) -> tuple[float, float, float, float, int, int]:
    with _RASTER_CACHE_LOCK:
        cached = _RASTER_METADATA_CACHE.get(path)
        if cached is not None:
            return cached
        image = _get_raster_image(path)
        tags = getattr(image, 'tag_v2', {})
        pixel_scale = tags.get(33550)
        tie_point = tags.get(33922)
        if not pixel_scale or not tie_point:
            raise RuntimeError(f'Missing GeoTIFF metadata in climate raster: {path}')
        x_scale = float(pixel_scale[0])
        y_scale = float(pixel_scale[1])
        origin_x = float(tie_point[3])
        origin_y = float(tie_point[4])
        metadata = (origin_x, origin_y, x_scale, y_scale, int(image.size[0]), int(image.size[1]))
        _RASTER_METADATA_CACHE[path] = metadata
        return metadata


def _sample_raster_value(
    path: Path,
    *,
    latitude: float,
    longitude: float,
    fill_value: float,
    latitude_min: float,
    latitude_max: float,
) -> float | None:
    if latitude < latitude_min or latitude > latitude_max:
        return None
    origin_x, origin_y, x_scale, y_scale, width, height = _get_raster_metadata(path)
    col = int(math.floor((longitude - origin_x) / x_scale))
    row = int(math.floor((origin_y - latitude) / y_scale))
    if col < 0 or row < 0 or col >= width or row >= height:
        return None
    with _RASTER_CACHE_LOCK:
        image = _get_raster_image(path)
        value = image.getpixel((col, row))
    numeric = float(value)
    if numeric == fill_value or math.isnan(numeric):
        return None
    return numeric


def build_chc_series_aggregation_cache(
    nasa_series: dict[str, dict[str, float | None]],
) -> dict[str, object]:
    cache_key = id(nasa_series)
    cached = _CHC_SERIES_AGGREGATION_CACHE.get(cache_key)
    if cached is not None:
        return cached

    keys = sorted(set(nasa_series.get("T2M", {}).keys()) | set(nasa_series.get("PRECTOTCORR", {}).keys()))
    key_to_index = {key: index for index, key in enumerate(keys)}
    temperature_prefix_sum = [0.0]
    temperature_prefix_count = [0]
    precipitation_prefix_sum = [0.0]

    running_temperature_sum = 0.0
    running_temperature_count = 0
    running_precipitation_sum = 0.0
    for key in keys:
        temperature = nasa_series.get("T2M", {}).get(key)
        precipitation = nasa_series.get("PRECTOTCORR", {}).get(key)
        if temperature is not None:
            running_temperature_sum += temperature
            running_temperature_count += 1
        if precipitation is not None:
            running_precipitation_sum += precipitation
        temperature_prefix_sum.append(running_temperature_sum)
        temperature_prefix_count.append(running_temperature_count)
        precipitation_prefix_sum.append(running_precipitation_sum)

    prepared = {
        "key_to_index": key_to_index,
        "temperature_prefix_sum": temperature_prefix_sum,
        "temperature_prefix_count": temperature_prefix_count,
        "precipitation_prefix_sum": precipitation_prefix_sum,
    }
    _CHC_SERIES_AGGREGATION_CACHE[cache_key] = prepared
    return prepared


def aggregate_metrics_fast(
    nasa_series: dict[str, dict[str, float | None]],
    start_date: date,
    end_date: date,
) -> dict[str, float | None]:
    if end_date < start_date:
        return {"avg_t2m": None, "total_prectotcorr": None}

    window_cache_key = (
        id(nasa_series),
        start_date.isoformat(),
        end_date.isoformat(),
    )
    cached_window_metrics = _CHC_WINDOW_METRICS_CACHE.get(window_cache_key)
    if cached_window_metrics is not None:
        return cached_window_metrics

    prepared = build_chc_series_aggregation_cache(nasa_series)
    key_to_index = prepared["key_to_index"]
    start_key = ea_pipeline.format_nasa_date(start_date)
    end_key = ea_pipeline.format_nasa_date(end_date)
    start_index = key_to_index.get(start_key)
    end_index = key_to_index.get(end_key)
    if start_index is None or end_index is None or end_index < start_index:
        fallback_metrics = ea_pipeline.aggregate_metrics(nasa_series, start_date, end_date)
        _CHC_WINDOW_METRICS_CACHE[window_cache_key] = fallback_metrics
        return fallback_metrics

    temperature_prefix_sum = prepared["temperature_prefix_sum"]
    temperature_prefix_count = prepared["temperature_prefix_count"]
    precipitation_prefix_sum = prepared["precipitation_prefix_sum"]
    temperature_sum = temperature_prefix_sum[end_index + 1] - temperature_prefix_sum[start_index]
    temperature_count = temperature_prefix_count[end_index + 1] - temperature_prefix_count[start_index]
    precipitation_sum = precipitation_prefix_sum[end_index + 1] - precipitation_prefix_sum[start_index]

    metrics = {
        "avg_t2m": (temperature_sum / temperature_count) if temperature_count else None,
        "total_prectotcorr": precipitation_sum,
    }
    _CHC_WINDOW_METRICS_CACHE[window_cache_key] = metrics
    return metrics


def _iter_dates_inclusive(start_date: date, end_date: date):
    current_date = start_date
    while current_date <= end_date:
        yield current_date
        current_date += timedelta(days=1)


def collect_required_chc_dates(
    records: list[dict[str, object]],
    climate_override: dict[str, object] | None = None,
) -> list[date]:
    unique_dates: set[date] = set()

    def add_pair(planting_date: date, harvesting_date: date) -> None:
        planting_week_1, planting_week_2, harvest_back_windows, intermediate_window = ea_pipeline.build_climate_windows(
            planting_date,
            harvesting_date,
        )
        windows = [planting_week_1, planting_week_2]
        windows.extend((window_start, window_end) for _, window_start, window_end in harvest_back_windows)
        if intermediate_window is not None:
            windows.append(intermediate_window)
        start_date = min(window_start for window_start, _ in windows)
        end_date = max(window_end for _, window_end in windows)
        for current_date in _iter_dates_inclusive(start_date, end_date):
            unique_dates.add(current_date)

    if climate_override and climate_override.get("forecast_planting_date") and climate_override.get("forecast_harvesting_date"):
        reference_pairs = ea_pipeline.resolve_forecast_reference_dates(
            str(climate_override["forecast_planting_date"]),
            str(climate_override["forecast_harvesting_date"]),
            int((climate_override or {}).get("forecast_years_back") or 5),
        )
        for planting_date, harvesting_date in reference_pairs:
            add_pair(planting_date, harvesting_date)
        return sorted(unique_dates)

    for record in records:
        planting_value = str(record.get("date_of_planting") or "").strip()
        harvesting_value = str(record.get("date_of_harvesting") or "").strip()
        if not planting_value or not harvesting_value:
            continue
        add_pair(ea_pipeline.parse_iso_date(planting_value), ea_pipeline.parse_iso_date(harvesting_value))
    return sorted(unique_dates)


def prefetch_chc_rasters(
    required_dates: list[date],
    *,
    progress_file: Path | None = None,
    progress_callback: ProgressCallback | None = None,
    skip_soil_enrichment: bool = False,
    max_workers: int = 6,
) -> dict[str, int]:
    if not required_dates:
        return {"task_total": 0, "downloaded": 0, "cached": 0, "prepared_raster_paths": {}}

    cache_dir = resolve_shared_chc_cache_dir()
    task_specs: list[tuple[str, date]] = []
    for current_date in required_dates:
        task_specs.append(("chirps", current_date))
        task_specs.append(("chirts_tmax", current_date))
        task_specs.append(("chirts_tmin", current_date))

    total_tasks = len(task_specs)
    completed_tasks = 0
    downloaded_tasks = 0
    prepared_raster_paths: dict[tuple[str, str], Path] = {}

    def resolve_task(dataset: str, current_date: date) -> tuple[Path, bool]:
        target_path, url = _resolve_raster_request(dataset, current_date, cache_dir)
        if target_path.exists():
            return target_path, False
        _download_with_retries(url, target_path)
        return target_path, True

    configured_workers = resolve_phase03_worker_limit("prefetch", total_tasks)
    worker_count = max(1, min(max_workers, configured_workers, total_tasks))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_map = {executor.submit(resolve_task, dataset, current_date): (dataset, current_date) for dataset, current_date in task_specs}
        for future in as_completed(future_map):
            dataset, current_date = future_map[future]
            target_path, downloaded = future.result()
            prepared_raster_paths[(dataset, current_date.isoformat())] = target_path
            completed_tasks += 1
            if downloaded:
                downloaded_tasks += 1
            overall_fraction = completed_tasks / total_tasks
            overall_percent = round(15 + (overall_fraction * 17), 1)
            cached_tasks = completed_tasks - downloaded_tasks
            message = (
                f"Preparing CHIRPS/CHIRTS-daily rasters for phase03: {completed_tasks}/{total_tasks} files checked "
                f"({round(overall_fraction * 100)}%). Downloaded now: {downloaded_tasks}. Already cached: {cached_tasks}."
            )
            write_progress(
                progress_file,
                percent=overall_percent,
                stage="Preparing climate rasters",
                message=message,
                details={
                    "phase": "phase03",
                    "climate_prefetch_tasks_completed": completed_tasks,
                    "climate_prefetch_tasks_total": total_tasks,
                    "climate_prefetch_downloaded": downloaded_tasks,
                    "climate_prefetch_cached": cached_tasks,
                    "soil_skipped": skip_soil_enrichment,
                },
            )
            if progress_callback:
                progress_callback(
                    overall_percent,
                    "Preparing climate rasters",
                    message,
                    {
                        "phase": "phase03",
                        "climate_prefetch_tasks_completed": completed_tasks,
                        "climate_prefetch_tasks_total": total_tasks,
                        "climate_prefetch_downloaded": downloaded_tasks,
                        "climate_prefetch_cached": cached_tasks,
                        "soil_skipped": skip_soil_enrichment,
                    },
                )

    return {
        "task_total": total_tasks,
        "downloaded": downloaded_tasks,
        "cached": total_tasks - downloaded_tasks,
        "prepared_raster_paths": prepared_raster_paths,
    }


def serialize_prefetch_metadata(prefetch_metadata: dict[str, object]) -> dict[str, object]:
    serialized = dict(prefetch_metadata)
    raw_paths = prefetch_metadata.get("prepared_raster_paths", {})
    if isinstance(raw_paths, dict):
        serialized["prepared_raster_paths"] = {
            (
                f"{str(key[0])}:{str(key[1])}"
                if isinstance(key, tuple) and len(key) == 2
                else str(key)
            ): str(value)
            for key, value in raw_paths.items()
        }
    return serialized


def fetch_chc_series(
    latitude: str,
    longitude: str,
    start_date: date,
    end_date: date,
    cache: dict[tuple[str, str, str, str], dict[str, dict[str, float | None]]],
    cache_path: Path | None = None,
    stats: dict[str, int] | None = None,
) -> dict[str, dict[str, float | None]]:
    lat_value = float(latitude)
    lon_value = float(longitude)
    pixel_id, pixel_center_latitude, pixel_center_longitude = resolve_chc_pixel_metadata(lat_value, lon_value)
    cache_key = (
        f"{pixel_center_latitude:.5f}",
        f"{pixel_center_longitude:.5f}",
        start_date.isoformat(),
        end_date.isoformat(),
    )
    series_identifier = "|".join(cache_key)
    total_days = max((end_date - start_date).days + 1, 1)
    if cache_key in cache:
        if _CHC_PARALLEL_PROGRESS_MODE:
            report_parallel_series_progress(series_identifier, total_days, total_days, completed=True, force=True)
        if _CHC_DOWNLOAD_PROGRESS_HOOK is not None and not _CHC_PARALLEL_PROGRESS_MODE:
            _CHC_DOWNLOAD_PROGRESS_HOOK("compute", max(1, min(7, total_days)), total_days, False)
            _CHC_DOWNLOAD_PROGRESS_HOOK("compute", total_days, total_days, True)
        if stats is not None:
            stats['cache_hits'] = stats.get('cache_hits', 0) + 1
        return cache[cache_key]

    cache_dir = resolve_shared_chc_cache_dir()
    result = {'T2M': {}, 'PRECTOTCORR': {}}
    current_date = start_date
    processed_days = 0
    while current_date <= end_date:
        if _CHC_PREPARED_RASTER_PATHS:
            chirps_path = _resolve_prepared_raster_path('chirps', current_date, cache_dir)
            tmax_path = _resolve_prepared_raster_path('chirts_tmax', current_date, cache_dir)
            tmin_path = _resolve_prepared_raster_path('chirts_tmin', current_date, cache_dir)
            chirps_downloaded = False
            tmax_downloaded = False
            tmin_downloaded = False
        else:
            chirps_path, chirps_downloaded = _resolve_raster_path('chirps', current_date, cache_dir)
            tmax_path, tmax_downloaded = _resolve_raster_path('chirts_tmax', current_date, cache_dir)
            tmin_path, tmin_downloaded = _resolve_raster_path('chirts_tmin', current_date, cache_dir)
        precip = _sample_raster_value(
            chirps_path,
            latitude=lat_value,
            longitude=lon_value,
            fill_value=CHIRPS_FILL_VALUE,
            latitude_min=CHIRPS_MIN_LATITUDE,
            latitude_max=CHIRPS_MAX_LATITUDE,
        )
        tmax = _sample_raster_value(
            tmax_path,
            latitude=lat_value,
            longitude=lon_value,
            fill_value=CHIRTS_FILL_VALUE,
            latitude_min=CHIRTS_MIN_LATITUDE,
            latitude_max=CHIRTS_MAX_LATITUDE,
        )
        tmin = _sample_raster_value(
            tmin_path,
            latitude=lat_value,
            longitude=lon_value,
            fill_value=CHIRTS_FILL_VALUE,
            latitude_min=CHIRTS_MIN_LATITUDE,
            latitude_max=CHIRTS_MAX_LATITUDE,
        )
        key = ea_pipeline.format_nasa_date(current_date)
        temperature = None
        if tmax is not None and tmin is not None:
            temperature = (tmax + tmin) / 2.0
        elif tmax is not None:
            temperature = tmax
        elif tmin is not None:
            temperature = tmin
        result['T2M'][key] = temperature
        result['PRECTOTCORR'][key] = precip
        processed_days += 1
        if _CHC_PARALLEL_PROGRESS_MODE and (processed_days == 1 or processed_days % 7 == 0 or processed_days == total_days):
            report_parallel_series_progress(series_identifier, processed_days, total_days, completed=False)
        if (
            _CHC_DOWNLOAD_PROGRESS_HOOK is not None
            and not _CHC_PARALLEL_PROGRESS_MODE
            and (processed_days == 1 or processed_days % 7 == 0 or processed_days == total_days)
        ):
            downloaded_today = chirps_downloaded or tmax_downloaded or tmin_downloaded
            if downloaded_today:
                _CHC_DOWNLOAD_PROGRESS_HOOK("download", processed_days, total_days, False)
            else:
                _CHC_DOWNLOAD_PROGRESS_HOOK("compute", processed_days, total_days, False)
        current_date += timedelta(days=1)

    if _CHC_PARALLEL_PROGRESS_MODE:
        report_parallel_series_progress(series_identifier, total_days, total_days, completed=True, force=True)
    elif _CHC_DOWNLOAD_PROGRESS_HOOK is not None:
        _CHC_DOWNLOAD_PROGRESS_HOOK("compute", total_days, total_days, True)

    cache[cache_key] = result
    if stats is not None:
        stats['cache_misses'] = stats.get('cache_misses', 0) + 1
    if cache_path is not None:
        ea_pipeline.save_nasa_cache(cache_path, cache)
    return result


def load_phase01_module():
    spec = importlib.util.spec_from_file_location("ce_phase01", PHASE01_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"The ce_pipeline phase01 script could not be loaded: {PHASE01_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def patched_phase02_output_dir(output_dir: Path):
    original_dir = ea_pipeline.PHASE_DIRS["phase02"]
    ea_pipeline.PHASE_DIRS["phase02"] = output_dir
    try:
        yield
    finally:
        ea_pipeline.PHASE_DIRS["phase02"] = original_dir


def normalize_excel_date(value: object) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value or "").strip()
    if not text:
        return ""
    for parser in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, parser).date().isoformat()
        except ValueError:
            continue
    try:
        serial = float(text.replace(",", "."))
    except ValueError:
        return ""
    base_date = date(1899, 12, 30)
    normalized_date = base_date + timedelta(days=int(serial))
    return normalized_date.isoformat()


def normalize_phase02_dates(
    records: list[dict[str, object]],
    initial_settings: dict[str, object],
) -> tuple[list[dict[str, object]], dict[str, int]]:
    planting_date_column = str(initial_settings.get("planting_date_column", "")).strip()
    harvesting_date_column = str(initial_settings.get("harvesting_date_column", "")).strip()
    if not planting_date_column and not harvesting_date_column:
        return records, {"dropped_missing_or_invalid_date_rows": 0}
    output_records: list[dict[str, object]] = []
    dropped_rows = 0
    for record in records:
        updated = dict(record)
        planting_value = normalize_excel_date(updated.get(planting_date_column, "")) if planting_date_column else ""
        harvesting_value = normalize_excel_date(updated.get(harvesting_date_column, "")) if harvesting_date_column else ""
        if planting_date_column and not planting_value:
            dropped_rows += 1
            continue
        if harvesting_date_column and not harvesting_value:
            dropped_rows += 1
            continue
        if planting_value and harvesting_value and harvesting_value < planting_value:
            dropped_rows += 1
            continue
        if planting_date_column:
            updated[planting_date_column] = planting_value
        if harvesting_date_column:
            updated[harvesting_date_column] = harvesting_value
        output_records.append(updated)
    return output_records, {"dropped_missing_or_invalid_date_rows": dropped_rows}


def enrich_soils(
    records: list[dict[str, object]],
    cache_path: Path,
    *,
    progress_callback: ProgressCallback | None = None,
) -> tuple[list[dict[str, object]], dict[str, int]]:
    enriched_rows = 0
    cache_hit_cells = 0
    service_success_cells = 0
    fallback_cells = 0
    resolved_points: dict[str, dict[str, object]] = {}
    output_records: list[dict[str, object]] = []
    total_rows = len(records)
    soil_cache_payload = soil_enrichment.normalize_cache_payload(soil_enrichment.load_cache_payload(cache_path))
    cache_changed = False
    pending_cache_writes = 0
    flush_every_new_points = 25

    for index, record in enumerate(records, start=1):
        updated = dict(record)
        latitude = soil_enrichment.parse_float(updated.get(LAT_HEADER))
        longitude = soil_enrichment.parse_float(updated.get(LON_HEADER))
        if latitude is None or longitude is None:
            output_records.append(updated)
            if progress_callback:
                percent = 94 + round((index / total_rows) * 3) if total_rows else 94
                progress_callback(
                    percent,
                    "Enriching soils",
                    f"Resolving soil data for {index}/{total_rows} prediction rows.",
                    {
                        "phase": "phase03",
                        "soil_processed_rows": index,
                        "soil_total_rows": total_rows,
                        "soil_cache_hits": cache_hit_cells,
                        "soil_service_success_cells": service_success_cells,
                        "soil_fallback_cells": fallback_cells,
                    },
                )
            continue
        cell_id = soil_enrichment.cache_key(latitude, longitude)
        if cell_id not in resolved_points:
            soil_record, resolved_source, point_cache_changed = soil_enrichment.resolve_soil_record_from_payload(
                latitude,
                longitude,
                payload=soil_cache_payload,
            )
            resolved_points[cell_id] = soil_record
            cache_changed = cache_changed or point_cache_changed
            if point_cache_changed:
                pending_cache_writes += 1
                if pending_cache_writes >= flush_every_new_points:
                    soil_enrichment.write_cache_payload(cache_path, soil_cache_payload)
                    pending_cache_writes = 0
            if resolved_source == "cache_hit":
                cache_hit_cells += 1
            elif resolved_source == "soilgrids":
                service_success_cells += 1
            if soil_record.get("soil_source") == "fallback_default":
                fallback_cells += 1
        soil_record = resolved_points[cell_id]
        updated[SOIL_TEXTURE_HEADER] = soil_record[SOIL_TEXTURE_HEADER]
        updated[SOIL_DEPTH_HEADER] = soil_record[SOIL_DEPTH_HEADER]
        updated["soil_source"] = soil_record.get("soil_source", "")
        updated["soil_texture_usda_class"] = soil_record.get("soil_texture_usda_class", "")
        output_records.append(updated)
        enriched_rows += 1
        if progress_callback:
            percent = 94 + round((index / total_rows) * 3) if total_rows else 94
            progress_callback(
                percent,
                "Enriching soils",
                f"Resolving soil data for {index}/{total_rows} prediction rows.",
                {
                    "phase": "phase03",
                    "soil_processed_rows": index,
                    "soil_total_rows": total_rows,
                    "soil_cache_hits": cache_hit_cells,
                    "soil_service_success_cells": service_success_cells,
                    "soil_fallback_cells": fallback_cells,
                },
            )

    if cache_changed:
        soil_enrichment.write_cache_payload(cache_path, soil_cache_payload)

    return output_records, {
        "soil_enriched_rows": enriched_rows,
        "soil_enriched_cells": len(resolved_points),
        "soil_fallback_cells": fallback_cells,
        "soil_cache_hits": cache_hit_cells,
        "soil_service_queries": max(len(resolved_points) - cache_hit_cells, 0),
        "soil_service_success_cells": service_success_cells,
    }


def write_progress(
    progress_file: Path | None,
    *,
    percent: int,
    stage: str,
    message: str,
    details: dict[str, object] | None = None,
) -> None:
    if progress_file is None:
        return
    payload: dict[str, object] = {
        "status": "running",
        "percent": max(0, min(100, int(percent))),
        "stage": stage,
        "message": message,
        "updated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
    }
    if details:
        payload["details"] = details
    progress_file.parent.mkdir(parents=True, exist_ok=True)
    progress_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def configure_parallel_progress_context(
    *,
    progress_file: Path | None,
    progress_callback: ProgressCallback | None,
    skip_soil_enrichment: bool,
    worker_count: int,
    series_total: int,
) -> None:
    with _CHC_PARALLEL_PROGRESS_LOCK:
        _CHC_PARALLEL_PROGRESS_CONTEXT["progress_file"] = progress_file
        _CHC_PARALLEL_PROGRESS_CONTEXT["progress_callback"] = progress_callback
        _CHC_PARALLEL_PROGRESS_CONTEXT["skip_soil_enrichment"] = skip_soil_enrichment
        _CHC_PARALLEL_PROGRESS_CONTEXT["worker_count"] = worker_count
        _CHC_PARALLEL_PROGRESS_CONTEXT["series_total"] = series_total
        _CHC_PARALLEL_PROGRESS_CONTEXT["series_progress"] = {}
        _CHC_PARALLEL_PROGRESS_CONTEXT["last_report_at"] = 0.0


def reset_parallel_progress_context() -> None:
    with _CHC_PARALLEL_PROGRESS_LOCK:
        _CHC_PARALLEL_PROGRESS_CONTEXT["progress_file"] = None
        _CHC_PARALLEL_PROGRESS_CONTEXT["progress_callback"] = None
        _CHC_PARALLEL_PROGRESS_CONTEXT["skip_soil_enrichment"] = True
        _CHC_PARALLEL_PROGRESS_CONTEXT["worker_count"] = 0
        _CHC_PARALLEL_PROGRESS_CONTEXT["series_total"] = 0
        _CHC_PARALLEL_PROGRESS_CONTEXT["series_progress"] = {}
        _CHC_PARALLEL_PROGRESS_CONTEXT["last_report_at"] = 0.0


def report_parallel_series_progress(
    series_identifier: str,
    processed_days: int,
    total_days: int,
    *,
    completed: bool = False,
    force: bool = False,
) -> None:
    with _CHC_PARALLEL_PROGRESS_LOCK:
        progress_file = _CHC_PARALLEL_PROGRESS_CONTEXT.get("progress_file")
        progress_callback = _CHC_PARALLEL_PROGRESS_CONTEXT.get("progress_callback")
        skip_soil_enrichment = bool(_CHC_PARALLEL_PROGRESS_CONTEXT.get("skip_soil_enrichment", True))
        worker_count = int(_CHC_PARALLEL_PROGRESS_CONTEXT.get("worker_count", 0) or 0)
        series_total = int(_CHC_PARALLEL_PROGRESS_CONTEXT.get("series_total", 0) or 0)
        series_progress = _CHC_PARALLEL_PROGRESS_CONTEXT.get("series_progress")
        if not isinstance(series_progress, dict) or series_total <= 0:
            return

        previous = series_progress.get(series_identifier, {"processed_days": 0, "total_days": total_days, "completed": False})
        normalized_processed_days = min(max(processed_days, int(previous.get("processed_days", 0) or 0)), max(total_days, 1))
        normalized_total_days = max(total_days, int(previous.get("total_days", total_days) or total_days), 1)
        normalized_completed = bool(completed or previous.get("completed"))
        if normalized_completed:
            normalized_processed_days = normalized_total_days
        series_progress[series_identifier] = {
            "processed_days": normalized_processed_days,
            "total_days": normalized_total_days,
            "completed": normalized_completed,
        }

        now = time.monotonic()
        last_report_at = float(_CHC_PARALLEL_PROGRESS_CONTEXT.get("last_report_at", 0.0) or 0.0)
        visible_series_progress = {
            key: item
            for key, item in series_progress.items()
            if not str(key).startswith("__")
        }
        effective_series_total = max(series_total, 1)
        completed_series = min(
            sum(1 for item in visible_series_progress.values() if bool(item.get("completed"))),
            effective_series_total,
        )
        overall_fraction = 0.0
        for item in visible_series_progress.values():
            item_total_days = max(int(item.get("total_days", 1) or 1), 1)
            item_processed_days = min(max(int(item.get("processed_days", 0) or 0), 0), item_total_days)
            overall_fraction += item_processed_days / item_total_days
        overall_fraction = min(overall_fraction / max(effective_series_total, 1), 1.0)

        if not force and not normalized_completed and now - last_report_at < 2.0:
            return
        _CHC_PARALLEL_PROGRESS_CONTEXT["last_report_at"] = now

    overall_percent = round(33 + (overall_fraction * 17), 1) if overall_fraction > 0 else 33.0
    active_workers = min(max(effective_series_total - completed_series, 0), worker_count)
    if completed:
        message = (
            f"Computing climate windows from prepared rasters: completed {completed_series}/{effective_series_total} climate series. "
            f"Phase03 climate workload progress {overall_fraction * 100:.1f}%."
        )
    else:
        message = (
            f"Computing climate windows in parallel: {completed_series}/{effective_series_total} climate series completed. "
            f"{active_workers} worker{'s' if active_workers != 1 else ''} active. "
            f"Phase03 climate workload progress {overall_fraction * 100:.1f}%."
        )

    write_progress(
        progress_file,
        percent=overall_percent,
        stage="Computing climate windows",
        message=message,
        details={
            "phase": "phase03",
            "climate_progress_stage": "compute",
            "climate_series_completed": completed_series,
            "climate_series_total": effective_series_total,
            "climate_parallel_workers": worker_count,
            "soil_skipped": skip_soil_enrichment,
        },
    )
    if progress_callback:
        progress_callback(
            overall_percent,
            "Computing climate windows",
            message,
            {
                "phase": "phase03",
                "climate_progress_stage": "compute",
                "climate_series_completed": completed_series,
                "climate_series_total": effective_series_total,
                "climate_parallel_workers": worker_count,
                "soil_skipped": skip_soil_enrichment,
            },
        )


def build_phase02_records_parallel_workspace(
    headers: list[str],
    records: list[dict[str, object]],
    *,
    progress_file: Path | None,
    progress_callback: ProgressCallback | None,
    skip_soil_enrichment: bool,
    climate_override: dict[str, object] | None = None,
) -> tuple[list[str], list[dict[str, object]], dict[str, object]]:
    output_dir = ea_pipeline.PHASE_DIRS["phase02"]
    locality_metadata: dict[str, object] = {}
    locality_mode = bool(climate_override) and str((climate_override or {}).get("climate_scope", "")).strip() in {
        "country_localities",
        "regional_manual",
    }
    source_records = records
    if locality_mode:
        if str((climate_override or {}).get("climate_scope", "")).strip() == "country_localities":
            source_records, data_input_rows, locality_metadata = ea_pipeline.expand_records_for_country_localities(
                records,
                climate_override or {},
            )
        else:
            source_records, data_input_rows, locality_metadata = ea_pipeline.expand_records_for_manual_bbox_localities(
                records,
                climate_override or {},
            )
        skipped_rows = 0
    else:
        data_input_rows, skipped_rows = ea_pipeline.build_data_input_rows(records)
    if not data_input_rows:
        raise ValueError("No hay filas exportables para la fase climatica.")

    ea_pipeline.write_csv(output_dir / "dataInput.csv", ea_pipeline.CLIMATE_INPUT_COLUMNS, data_input_rows)

    cache_path = output_dir / "nasa_power_cache.json"
    cache = ea_pipeline.load_nasa_cache(cache_path)
    feature_cache_path = resolve_shared_climate_feature_cache_path()
    feature_cache_path.parent.mkdir(parents=True, exist_ok=True)
    persistent_feature_cache = load_climate_feature_cache(feature_cache_path)
    initial_cache_size = len(cache)
    output_columns = ea_pipeline.build_output_columns()

    grouped_row_indexes: dict[tuple[str, str, str], list[int]] = {}
    representative_rows: dict[tuple[str, str, str], dict[str, str]] = {}
    for index, row in enumerate(data_input_rows):
        series_key = build_climate_series_key(row)
        grouped_row_indexes.setdefault(series_key, []).append(index)
        representative_rows.setdefault(series_key, row)

    unique_series_items = list(representative_rows.items())
    total_unique_series = len(unique_series_items)
    progress_series_total = total_unique_series
    if climate_override:
        forecast_planting_date = str(climate_override.get("forecast_planting_date") or "").strip()
        forecast_harvesting_date = str(climate_override.get("forecast_harvesting_date") or "").strip()
        use_source_row_dates = bool(climate_override.get("use_source_row_dates"))
        if forecast_planting_date and forecast_harvesting_date and not use_source_row_dates:
            try:
                reference_pairs = ea_pipeline.resolve_forecast_reference_dates(
                    forecast_planting_date,
                    forecast_harvesting_date,
                    int(climate_override.get("forecast_years_back", 5) or 5),
                )
                progress_series_total = max(total_unique_series * len(reference_pairs), total_unique_series, 1)
            except Exception:
                progress_series_total = max(total_unique_series, 1)
    completed_unique_series = 0
    aggregate_cache_hits = 0
    aggregate_cache_misses = 0
    aggregate_feature_cache_hits = 0
    aggregate_feature_cache_misses = 0
    representative_results: dict[tuple[str, str, str], tuple[dict[str, str], dict[str, str]]] = {}
    computed_feature_payloads: dict[str, dict[str, object]] = {}

    def process_series(item: tuple[tuple[str, str, str], dict[str, str]]) -> tuple[
        tuple[str, str, str],
        dict[str, str],
        dict[str, str],
        dict[str, int],
    ]:
        series_key, row = item
        serialized_series_key = serialize_climate_series_key(series_key)
        cached_feature_payload = persistent_feature_cache.get(serialized_series_key)
        if isinstance(cached_feature_payload, dict):
            cached_output_row = cached_feature_payload.get("output_row")
            cached_audit_row = cached_feature_payload.get("audit_row")
            if isinstance(cached_output_row, dict) and isinstance(cached_audit_row, dict):
                return series_key, dict(cached_output_row), dict(cached_audit_row), {
                    "cache_hits": 0,
                    "cache_misses": 0,
                    "feature_cache_hits": 1,
                    "feature_cache_misses": 0,
                }
        local_stats = {"cache_hits": 0, "cache_misses": 0}
        effective_climate_override = dict(climate_override or {})
        if locality_mode:
            effective_climate_override["climate_scope"] = "point"
        output_row, audit_row = ea_pipeline.build_output_row(
            row,
            cache,
            cache_path=None,
            climate_override=effective_climate_override,
            cache_stats=local_stats,
        )
        local_stats["feature_cache_hits"] = 0
        local_stats["feature_cache_misses"] = 1
        local_stats["feature_cache_payload"] = {
            "output_row": dict(output_row),
            "audit_row": dict(audit_row),
        }
        return series_key, output_row, audit_row, local_stats

    worker_count = resolve_phase03_worker_limit("compute", total_unique_series) if total_unique_series > 1 else 1
    configure_parallel_progress_context(
        progress_file=progress_file,
        progress_callback=progress_callback,
        skip_soil_enrichment=skip_soil_enrichment,
        worker_count=worker_count,
        series_total=progress_series_total,
    )
    report_parallel_series_progress("__bootstrap__", 0, 1, completed=False, force=True)

    global _CHC_PARALLEL_PROGRESS_MODE
    original_parallel_progress_mode = _CHC_PARALLEL_PROGRESS_MODE
    _CHC_PARALLEL_PROGRESS_MODE = worker_count > 1
    try:
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            pending_futures = {
                executor.submit(process_series, item): item[0]
                for item in unique_series_items
            }
            while pending_futures:
                done_futures, pending_set = wait(
                    pending_futures.keys(),
                    timeout=5,
                    return_when=FIRST_COMPLETED,
                )
                if not done_futures:
                    continue

                for future in done_futures:
                    series_key, output_row, audit_row, local_stats = future.result()
                    representative_results[series_key] = (output_row, audit_row)
                    completed_unique_series += 1
                    aggregate_cache_hits += int(local_stats.get("cache_hits", 0) or 0)
                    aggregate_cache_misses += int(local_stats.get("cache_misses", 0) or 0)
                    aggregate_feature_cache_hits += int(local_stats.get("feature_cache_hits", 0) or 0)
                    aggregate_feature_cache_misses += int(local_stats.get("feature_cache_misses", 0) or 0)
                    feature_cache_payload = local_stats.get("feature_cache_payload")
                    if isinstance(feature_cache_payload, dict):
                        computed_feature_payloads[serialize_climate_series_key(series_key)] = feature_cache_payload
                    del pending_futures[future]
    finally:
        _CHC_PARALLEL_PROGRESS_MODE = original_parallel_progress_mode
        reset_parallel_progress_context()

    ea_pipeline.save_nasa_cache(cache_path, cache)
    if computed_feature_payloads:
        persistent_feature_cache.update(computed_feature_payloads)
        save_climate_feature_cache(feature_cache_path, persistent_feature_cache)

    output_rows: list[dict[str, str]] = []
    audit_rows: list[dict[str, str]] = []
    for row in data_input_rows:
        series_key = build_climate_series_key(row)
        template_output, template_audit = representative_results[series_key]
        output_row = {column: row[column] for column in ea_pipeline.CLIMATE_ID_COLUMNS}
        for header in output_columns:
            if header in ea_pipeline.CLIMATE_ID_COLUMNS:
                continue
            output_row[header] = template_output.get(header, "")
        audit_row = dict(template_audit)
        for column in ea_pipeline.CLIMATE_ID_COLUMNS:
            audit_row[column] = row[column]
        audit_row["latitude"] = row.get("latitude", "")
        audit_row["longitude"] = row.get("longitude", "")
        audit_row["date_of_planting"] = row.get("date_of_planting", "")
        audit_row["date_of_harvesting"] = row.get("date_of_harvesting", "")
        audit_row["forecast_locality"] = row.get("forecast_locality", "")
        audit_row["forecast_locality_geonameid"] = row.get("forecast_locality_geonameid", "")
        audit_row["forecast_locality_population"] = row.get("forecast_locality_population", "")
        audit_row["forecast_country"] = row.get("forecast_country", "")
        audit_row["forecast_country_code"] = row.get("forecast_country_code", "")
        audit_row["forecast_grid_cell_id"] = row.get("forecast_grid_cell_id", "")
        audit_row["forecast_grid_cell_index"] = row.get("forecast_grid_cell_index", "")
        audit_row["selected_model_id"] = row.get("selected_model_id", "")
        output_rows.append(output_row)
        audit_rows.append(audit_row)

    ea_pipeline.write_csv(output_dir / "output.csv", output_columns, output_rows)
    ea_pipeline.write_csv(output_dir / "weekly_windows_audit.csv", ea_pipeline.CLIMATE_AUDIT_COLUMNS, audit_rows)

    climate_by_key = {
        tuple(ea_pipeline.normalize_key_value(row[column]) for column in ea_pipeline.CLIMATE_ID_COLUMNS): row
        for row in output_rows
    }

    phase02_headers = (
        ea_pipeline.build_country_locality_phase02_headers(headers)
        if locality_mode
        else ea_pipeline.build_phase02_headers(headers)
    )
    phase02_records: list[dict[str, object]] = []
    matched_rows = 0
    unmatched_rows = 0
    if locality_mode:
        matched_rows = len(source_records)
        for record, climate_row in zip(source_records, output_rows):
            enriched = dict(record)
            for header in output_columns:
                if header in ea_pipeline.CLIMATE_ID_COLUMNS:
                    continue
                enriched[ea_pipeline.climate_header_to_label(header)] = climate_row.get(header, "")
            phase02_records.append(enriched)
    else:
        for record in source_records:
            key = (
                ea_pipeline.normalize_key_value(record.get(ea_pipeline.TRIAL_SERIES_HEADER)),
                ea_pipeline.normalize_key_value(record.get("Site Number")),
                ea_pipeline.normalize_key_value(record.get("Plot")),
                ea_pipeline.normalize_key_value(record.get("EntryCode")),
            )
            climate_row = climate_by_key.get(key, {})
            if climate_row:
                matched_rows += 1
            else:
                unmatched_rows += 1

            enriched = dict(record)
            for header in output_columns:
                if header in ea_pipeline.CLIMATE_ID_COLUMNS:
                    continue
                enriched[ea_pipeline.climate_header_to_label(header)] = climate_row.get(header, "")
            phase02_records.append(enriched)

    ea_pipeline.write_workbook(
        output_dir / "phase02_climate_enriched.xlsx",
        "phase02_climate",
        phase02_headers,
        phase02_records,
    )

    metadata = {
        "phase": "phase02_climate_enriched",
        "input_row_count": len(records),
        "phase02_source_row_count": len(source_records),
        "climate_input_row_count": len(data_input_rows),
        "skipped_rows_missing_climate_fields": skipped_rows,
        "matched_rows": matched_rows,
        "unmatched_rows": unmatched_rows,
        "nasa_unique_queries": len(cache),
        "nasa_cache_initial_entries": initial_cache_size,
        "nasa_cache_final_entries": len(cache),
        "nasa_cache_fresh_queries_this_run": aggregate_cache_misses,
        "nasa_cache_hits": aggregate_cache_hits,
        "nasa_cache_misses": aggregate_cache_misses,
        "nasa_cache_file": str(cache_path),
        "climate_feature_cache_file": str(feature_cache_path),
        "climate_feature_cache_hits": aggregate_feature_cache_hits,
        "climate_feature_cache_misses": aggregate_feature_cache_misses,
        "header_count": len(phase02_headers),
        "climate_headers_with_units": ea_pipeline.CLIMATE_HEADERS_WITH_UNITS,
        "climate_override": climate_override or {},
        "parallel_unique_climate_series": total_unique_series,
        "parallel_progress_series_total": progress_series_total,
        "parallel_workers": worker_count,
        **locality_metadata,
    }
    ea_pipeline.write_metadata(output_dir / "metadata.json", metadata)
    return phase02_headers, phase02_records, metadata



def load_cache_payload(cache_path: Path) -> dict[str, object]:
    if not cache_path.exists():
        return {}
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def merge_cache_payload_files(source_cache: Path, destination_cache: Path) -> None:
    source_payload = load_cache_payload(source_cache)
    if not source_payload:
        return
    destination_payload = load_cache_payload(destination_cache)
    if isinstance(destination_payload.get("points"), dict) and isinstance(source_payload.get("points"), dict):
        merged_payload = dict(destination_payload)
        merged_points = dict(destination_payload.get("points", {}))
        merged_points.update(source_payload.get("points", {}))
        merged_payload.update(source_payload)
        merged_payload["points"] = merged_points
    else:
        merged_payload = dict(destination_payload)
        merged_payload.update(source_payload)
    destination_cache.parent.mkdir(parents=True, exist_ok=True)
    destination_cache.write_text(json.dumps(merged_payload, ensure_ascii=False, indent=2), encoding="utf-8")


class BufferedNasaCacheWriter:
    def __init__(self, original_save, flush_every: int = 25):
        self.original_save = original_save
        self.flush_every = max(1, int(flush_every))
        self.pending_writes = 0
        self.last_cache_path: Path | None = None
        self.last_cache: dict[tuple[str, str, str, str], dict[str, dict[str, float | None]]] | None = None

    def save(self, cache_path: Path, cache: dict[tuple[str, str, str, str], dict[str, dict[str, float | None]]]) -> None:
        self.last_cache_path = cache_path
        self.last_cache = cache
        self.pending_writes += 1
        if self.pending_writes >= self.flush_every:
            self.flush()

    def flush(self) -> None:
        if self.last_cache_path is None or self.last_cache is None or self.pending_writes <= 0:
            return
        self.original_save(self.last_cache_path, self.last_cache)
        self.pending_writes = 0


def apply_initial_settings_aliases(
    headers: list[str],
    records: list[dict[str, object]],
    initial_settings: dict[str, object],
) -> tuple[list[str], list[dict[str, object]]]:
    alias_pairs = [
        (ea_pipeline.LAT_HEADER, str(initial_settings.get("latitude_column", "")).strip()),
        (ea_pipeline.LON_HEADER, str(initial_settings.get("longitude_column", "")).strip()),
        (ea_pipeline.DATE_PLANTING_HEADER, str(initial_settings.get("planting_date_column", "")).strip()),
        (ea_pipeline.DATE_HARVESTING_HEADER, str(initial_settings.get("harvesting_date_column", "")).strip()),
        (SOIL_TEXTURE_HEADER, str(initial_settings.get("soil_texture_column", "")).strip()),
        (SOIL_DEPTH_HEADER, str(initial_settings.get("soil_depth_column", "")).strip()),
    ]
    normalized_headers = list(headers)
    normalized_records: list[dict[str, object]] = []
    for record in records:
        updated = dict(record)
        for canonical_header, selected_header in alias_pairs:
            if not selected_header:
                continue
            if canonical_header not in normalized_headers:
                normalized_headers.append(canonical_header)
            if canonical_header == selected_header:
                continue
            updated[canonical_header] = record.get(selected_header, "")
        normalized_records.append(updated)
    return normalized_headers, normalized_records


def create_phase03_workbook(
    phase02_workbook: Path,
    definition_file: Path,
    output_file: Path,
    log_file: Path,
    *,
    progress_file: Path | None = None,
    skip_soil_enrichment: bool = False,
    climate_override: dict[str, object] | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, object]:
    phase01 = load_phase01_module()
    definition = phase01.read_definition(definition_file)
    initial_settings = definition.get("initial_settings", {})
    headers, records = phase01.read_sheet_headers_and_rows(phase02_workbook)
    if not headers:
        raise ValueError("The phase02 workbook is empty.")
    original_input_row_count = len(records)
    records, normalized_date_stats = normalize_phase02_dates(records, initial_settings)
    headers, records = apply_initial_settings_aliases(headers, records, initial_settings)
    headers, records, merge_cleanup_metadata = prepare_ce_row_merge_keys(headers, records)

    output_dir = output_file.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    local_nasa_cache_path = output_dir / "nasa_power_cache.json"
    shared_nasa_cache_path = resolve_shared_nasa_cache_path()
    shared_nasa_cache_path.parent.mkdir(parents=True, exist_ok=True)

    def climate_progress_callback(_phase_percent: int, _stage: str, _message: str, details: dict[str, object] | None) -> None:
        resolved_details = details if isinstance(details, dict) else {}
        processed_rows = int(resolved_details.get("processed_rows", 0) or 0)
        total_rows = int(resolved_details.get("total_rows", len(records)) or len(records) or 0)
        row_percent = round((processed_rows / total_rows) * 100) if total_rows else 0
        cached_rows = int(resolved_details.get("cached_rows_served", 0) or 0)
        fresh_queries = int(resolved_details.get("fresh_queries_this_run", 0) or 0)
        overall_percent = round(33 + ((processed_rows / total_rows) * 17), 1) if total_rows else 33.0
        write_progress(
            progress_file,
            percent=overall_percent,
            stage="Executing phase03",
            message=(
                f"Downloading CHIRPS/CHIRTS-daily data for {processed_rows}/{total_rows} records "
                f"({row_percent}%). New queries this run: {fresh_queries}. Cached records served: {cached_rows}."
            ),
            details={
                "phase": "phase03",
                "nasa_processed_rows": processed_rows,
                "nasa_total_rows": total_rows,
                "nasa_row_percent": row_percent,
                "nasa_cached_rows": cached_rows,
                "nasa_fresh_queries": fresh_queries,
                "soil_skipped": skip_soil_enrichment,
            },
        )
        if progress_callback:
            progress_callback(
                overall_percent,
                "Downloading CHIRPS/CHIRTS-daily data",
                (
                    f"Downloading CHIRPS/CHIRTS-daily data for {processed_rows}/{total_rows} records "
                    f"({row_percent}%). New queries this run: {fresh_queries}. Cached records served: {cached_rows}."
                ),
                {
                    "phase": "phase03",
                    "nasa_processed_rows": processed_rows,
                    "nasa_total_rows": total_rows,
                    "nasa_row_percent": row_percent,
                    "nasa_cached_rows": cached_rows,
                    "nasa_fresh_queries": fresh_queries,
                    "soil_skipped": skip_soil_enrichment,
                },
            )

    def chc_download_progress_callback(stage_name: str, processed_days: int, total_days: int, series_completed: bool) -> None:
        total_series = max(int(_CHC_DOWNLOAD_PROGRESS_STATE.get("series_total", 0) or 0), 1)
        completed_series = int(_CHC_DOWNLOAD_PROGRESS_STATE.get("series_completed", 0) or 0)
        state_total_days = int(_CHC_DOWNLOAD_PROGRESS_STATE.get("series_total_days", 0) or 0)
        if state_total_days != total_days:
            _CHC_DOWNLOAD_PROGRESS_STATE["series_total_days"] = total_days
            _CHC_DOWNLOAD_PROGRESS_STATE["download_max_processed_days"] = 0
            _CHC_DOWNLOAD_PROGRESS_STATE["compute_max_processed_days"] = 0

        safe_completed_series = min(completed_series, total_series)
        if stage_name == "download":
            state_key = "download_max_processed_days"
            stage = "Preparing climate rasters"
            series_progress = processed_days / max(total_days, 1)
            active_completed_series = min(safe_completed_series, max(total_series - 1, 0))
            overall_fraction = min((active_completed_series + series_progress) / total_series, 1.0)
            overall_percent = round(15 + (overall_fraction * 17), 1) if overall_fraction > 0 else 15.0
            current_series_index = min(active_completed_series + 1, total_series)
            message = (
                f"Downloading CHIRPS/CHIRTS-daily rasters for phase03: series {current_series_index}/{total_series}, "
                f"{processed_days}/{total_days} days prepared ({round(series_progress * 100)}%). "
                f"Phase03 climate workload progress {overall_fraction * 100:.1f}%."
            )
            completed_series = active_completed_series
        else:
            state_key = "compute_max_processed_days"
            if series_completed and safe_completed_series < total_series:
                safe_completed_series += 1
                _CHC_DOWNLOAD_PROGRESS_STATE["series_completed"] = safe_completed_series
            stage = "Computing climate windows"
            series_progress = processed_days / max(total_days, 1)
            if series_completed:
                current_series_index = min(safe_completed_series, total_series)
                overall_fraction = min(safe_completed_series / total_series, 1.0)
            else:
                active_completed_series = min(safe_completed_series, max(total_series - 1, 0))
                current_series_index = min(active_completed_series + 1, total_series)
                overall_fraction = min((active_completed_series + series_progress) / total_series, 1.0)
                safe_completed_series = active_completed_series
            overall_percent = round(33 + (overall_fraction * 17), 1) if overall_fraction > 0 else 33.0
            message = (
                f"Computing climate windows from prepared rasters: series {current_series_index}/{total_series}, "
                f"{processed_days}/{total_days} days evaluated for the current series ({round(series_progress * 100)}%). "
                f"Phase03 climate workload progress {overall_fraction * 100:.1f}%."
            )
            if series_completed:
                message = (
                    f"Computing climate windows from prepared rasters: completed {safe_completed_series}/{total_series} climate series. "
                    f"Phase03 climate workload progress {overall_fraction * 100:.1f}%."
                )
            completed_series = safe_completed_series

        state_max_processed_days = int(_CHC_DOWNLOAD_PROGRESS_STATE.get(state_key, 0) or 0)
        if processed_days < state_max_processed_days:
            state_max_processed_days = 0
            _CHC_DOWNLOAD_PROGRESS_STATE[state_key] = 0
        if processed_days <= state_max_processed_days and not series_completed:
            return
        _CHC_DOWNLOAD_PROGRESS_STATE[state_key] = processed_days

        write_progress(
            progress_file,
            percent=overall_percent,
            stage=stage,
            message=message,
            details={
                "phase": "phase03",
                "climate_days_processed": processed_days,
                "climate_days_total": total_days,
                "climate_progress_stage": stage_name,
                "climate_series_completed": completed_series,
                "climate_series_total": total_series,
                "soil_skipped": skip_soil_enrichment,
            },
        )
        if progress_callback:
            progress_callback(
                overall_percent,
                stage,
                message,
                {
                    "phase": "phase03",
                    "climate_days_processed": processed_days,
                    "climate_days_total": total_days,
                    "climate_progress_stage": stage_name,
                    "climate_series_completed": completed_series,
                    "climate_series_total": total_series,
                    "soil_skipped": skip_soil_enrichment,
                },
            )


    buffered_cache_writer = BufferedNasaCacheWriter(ea_pipeline.save_nasa_cache, flush_every=10)
    estimated_series_total = estimate_unique_climate_series_total(records)
    manual_grid_pixel_map: dict[str, str] = {}
    manual_grid_unique_pixel_ids: set[str] = set()
    manual_grid_duplicate_pixel_rows = 0
    unique_source_date_pairs: set[tuple[str, str]] = set()
    if climate_override and str(climate_override.get("climate_scope", "")).strip() == "regional_manual":
        try:
            grid_cells = build_manual_grid_cells(
                float(climate_override.get("regional_bounds_latitude_min")),
                float(climate_override.get("regional_bounds_latitude_max")),
                float(climate_override.get("regional_bounds_longitude_min")),
                float(climate_override.get("regional_bounds_longitude_max")),
                label=str(climate_override.get("regional_bounds_label") or "Manual bounds").strip() or "Manual bounds",
                cell_size_km=float(climate_override.get("nasa_grid_resolution_km") or 10),
            )
            for grid_cell in grid_cells:
                pixel_id, _, _ = resolve_chc_pixel_metadata(
                    float(grid_cell["center_latitude"]),
                    float(grid_cell["center_longitude"]),
                )
                manual_grid_pixel_map[str(grid_cell["grid_cell_id"])] = pixel_id
                manual_grid_unique_pixel_ids.add(pixel_id)
            manual_grid_duplicate_pixel_rows = max(0, len(grid_cells) - len(manual_grid_unique_pixel_ids))

            use_source_row_dates = bool((climate_override or {}).get("use_source_row_dates"))
            if use_source_row_dates:
                for record in records:
                    planting_value = str(record.get("date_of_planting") or "").strip()
                    harvesting_value = str(record.get("date_of_harvesting") or "").strip()
                    if planting_value and harvesting_value:
                        unique_source_date_pairs.add((planting_value, harvesting_value))
                estimated_series_total = max(
                    1,
                    max(1, len(manual_grid_unique_pixel_ids)) * max(1, len(unique_source_date_pairs)),
                )
            else:
                estimated_series_total = max(
                    1,
                    len(records) * max(1, len(manual_grid_unique_pixel_ids)) * int(climate_override.get("forecast_years_back") or 5),
                )
        except Exception:
            estimated_series_total = max(
                estimate_unique_climate_series_total(records),
                len(records) * int((climate_override or {}).get("forecast_years_back") or 5),
            )

    required_chc_dates = collect_required_chc_dates(records, climate_override)
    prefetch_metadata = prefetch_chc_rasters(
        required_chc_dates,
        progress_file=progress_file,
        progress_callback=progress_callback,
        skip_soil_enrichment=skip_soil_enrichment,
    )

    original_load_nasa_cache = ea_pipeline.load_nasa_cache
    original_save_nasa_cache = ea_pipeline.save_nasa_cache
    original_fetch_nasa_series = ea_pipeline.fetch_nasa_series
    original_aggregate_metrics = ea_pipeline.aggregate_metrics
    global _CHC_DOWNLOAD_PROGRESS_HOOK
    global _CHC_DOWNLOAD_PROGRESS_STATE
    global _CHC_SERIES_AGGREGATION_CACHE
    global _CHC_WINDOW_METRICS_CACHE
    global _CHC_PREPARED_RASTER_PATHS
    original_chc_download_progress_hook = _CHC_DOWNLOAD_PROGRESS_HOOK
    original_chc_download_progress_state = dict(_CHC_DOWNLOAD_PROGRESS_STATE)
    original_prepared_raster_paths = dict(_CHC_PREPARED_RASTER_PATHS)
    _CHC_PREPARED_RASTER_PATHS = dict(prefetch_metadata.get("prepared_raster_paths", {}))
    _CHC_DOWNLOAD_PROGRESS_STATE = {"series_total": estimated_series_total, "series_completed": 0, "series_total_days": 0, "download_max_processed_days": 0, "compute_max_processed_days": 0}

    use_ephemeral_chc_series_cache = bool(climate_override) and str(
        (climate_override or {}).get("climate_scope", "")
    ).strip() == "regional_manual"

    def load_shared_nasa_cache(_cache_path: Path):
        if use_ephemeral_chc_series_cache:
            return {}
        return original_load_nasa_cache(shared_nasa_cache_path)

    def save_shared_nasa_cache(_cache_path: Path, cache):
        if use_ephemeral_chc_series_cache:
            return
        buffered_cache_writer.save(shared_nasa_cache_path, cache)

    ea_pipeline.load_nasa_cache = load_shared_nasa_cache
    ea_pipeline.save_nasa_cache = save_shared_nasa_cache
    ea_pipeline.fetch_nasa_series = fetch_chc_series
    ea_pipeline.aggregate_metrics = aggregate_metrics_fast
    _CHC_SERIES_AGGREGATION_CACHE = {}
    _CHC_WINDOW_METRICS_CACHE = {}
    _CHC_DOWNLOAD_PROGRESS_HOOK = chc_download_progress_callback
    try:
        with patched_phase02_output_dir(output_dir):
            phase03_headers, phase03_records, climate_metadata = build_phase02_records_parallel_workspace(
                headers,
                records,
                progress_file=progress_file,
                progress_callback=progress_callback,
                skip_soil_enrichment=skip_soil_enrichment,
                climate_override=climate_override,
            )
    finally:
        ea_pipeline.load_nasa_cache = original_load_nasa_cache
        ea_pipeline.save_nasa_cache = original_save_nasa_cache
        ea_pipeline.fetch_nasa_series = original_fetch_nasa_series
        ea_pipeline.aggregate_metrics = original_aggregate_metrics
        _CHC_DOWNLOAD_PROGRESS_HOOK = original_chc_download_progress_hook
        _CHC_DOWNLOAD_PROGRESS_STATE = original_chc_download_progress_state
        _CHC_PREPARED_RASTER_PATHS = original_prepared_raster_paths
        _CHC_SERIES_AGGREGATION_CACHE = {}
        _CHC_WINDOW_METRICS_CACHE = {}
        buffered_cache_writer.flush()

    write_progress(
        progress_file,
        percent=92,
        stage="Finalizing climate outputs",
        message="Climate windows finished. Preparing manual-grid metadata and shared cache artifacts before soil enrichment.",
        details={
            "phase": "phase03",
            "climate_progress_stage": "finalize",
            "climate_series_completed": climate_metadata.get("parallel_unique_climate_series", 0),
            "soil_skipped": skip_soil_enrichment,
        },
    )
    if progress_callback:
        progress_callback(
            92,
            "Finalizing climate outputs",
            "Climate windows finished. Preparing manual-grid metadata and shared cache artifacts before soil enrichment.",
            {
                "phase": "phase03",
                "climate_progress_stage": "finalize",
                "climate_series_completed": climate_metadata.get("parallel_unique_climate_series", 0),
                "soil_skipped": skip_soil_enrichment,
            },
        )

    if shared_nasa_cache_path.exists() and not use_ephemeral_chc_series_cache:
        shutil.copy2(shared_nasa_cache_path, local_nasa_cache_path)

    if manual_grid_pixel_map:
        if CLIMATE_PIXEL_ID_HEADER not in phase03_headers:
            phase03_headers.append(CLIMATE_PIXEL_ID_HEADER)
        for record in phase03_records:
            grid_cell_id = str(record.get("forecast_grid_cell_id") or "").strip()
            if not grid_cell_id:
                continue
            record[CLIMATE_PIXEL_ID_HEADER] = manual_grid_pixel_map.get(grid_cell_id, "")

    soil_cache_path = output_dir / "soilgrids_cache.json"
    shared_soil_cache_path = resolve_shared_soil_cache_path()
    shared_soil_cache_path.parent.mkdir(parents=True, exist_ok=True)
    if shared_soil_cache_path.exists() and not soil_cache_path.exists():
        shutil.copy2(shared_soil_cache_path, soil_cache_path)
    if skip_soil_enrichment:
        soil_metadata: dict[str, object] = {
            "soil_enrichment_skipped": True,
            "soil_skip_reason": "Base ce_pipeline uses the soil columns already selected in Initial Settings.",
        }
    else:
        if progress_callback:
            progress_callback(
                94,
                "Enriching soils",
                "Querying the soil service for the manual bounding-box grid and filling soil texture and depth.",
                {"phase": "phase03", "soil_total_rows": len(phase03_records)},
            )
        phase03_records, soil_metadata = enrich_soils(
            phase03_records,
            soil_cache_path,
            progress_callback=progress_callback,
        )
        if soil_cache_path.exists():
            merge_cache_payload_files(soil_cache_path, shared_soil_cache_path)

    phase03_headers, phase03_records = restore_ce_row_merge_keys(
        phase03_headers,
        phase03_records,
        merge_cleanup_metadata,
    )

    if climate_override and str(climate_override.get("climate_scope", "")).strip() == "regional_manual":
        phase01.write_xlsx_rows(
            output_file,
            phase03_headers,
            ([record.get(header, "") for header in phase03_headers] for record in phase03_records),
            len(phase03_records),
        )
    else:
        phase01.write_xlsx(output_file, phase03_headers, phase03_records)
    if progress_callback:
        progress_callback(
            97,
            "Writing phase03prediction",
            "Saving the climate and soil enriched workbook for the prediction flow.",
            {"phase": "phase03", "output_workbook": str(output_file)},
        )

    log_payload = {
        "phase": "phase03",
        "source_workbook": str(phase02_workbook),
        "output_workbook": str(output_file),
        "definition_file": str(definition_file),
        "original_input_row_count": original_input_row_count,
        "input_row_count": len(records),
        "output_row_count": len(phase03_records),
        "date_validation": normalized_date_stats,
        "header_count": len(phase03_headers),
        "initial_settings": definition.get("initial_settings", {}),
        "divisions": definition.get("divisions", {}),
        "nasa": climate_metadata,
        "climate_provider": "chirps_chirts_daily",
        "climate_override": climate_override or {},
        "climate_prefetch": {
            "required_unique_dates": len(required_chc_dates),
            **serialize_prefetch_metadata(prefetch_metadata),
        },
        "climate_pixel_dedup": {
            "pixel_resolution_degrees": CHC_GRID_STEP_DEGREES,
            "manual_grid_unique_pixels": len(manual_grid_unique_pixel_ids),
            "manual_grid_duplicate_cells": manual_grid_duplicate_pixel_rows,
            "unique_source_date_pairs": len(unique_source_date_pairs),
            "traceability_header": CLIMATE_PIXEL_ID_HEADER,
        },
        "soil": soil_metadata,
        "ce_row_id_header": CE_ROW_ID_HEADER,
        "nasa_cache_identity": ["climate_pixel_center_latitude", "climate_pixel_center_longitude", "date_of_planting", "date_of_harvesting"],
        "artifacts": {
            "nasa_cache_file": str(local_nasa_cache_path),
            "nasa_cache_shared_file": str(shared_nasa_cache_path),
            "soil_cache_file": str(soil_cache_path),
            "phase02_workbook_generated_by_preprocess_logic": str(output_dir / "phase02_climate_enriched.xlsx"),
            "weekly_windows_audit": str(output_dir / "weekly_windows_audit.csv"),
            "data_input_csv": str(output_dir / "dataInput.csv"),
            "output_csv": str(output_dir / "output.csv"),
        },
    }
    log_file.parent.mkdir(parents=True, exist_ok=True)
    log_file.write_text(json.dumps(log_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return log_payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create ce_pipeline phase03 workbook with NASA POWER enrichment.")
    parser.add_argument("--phase02-workbook", required=True, help="Path to the generated phase02 workbook.")
    parser.add_argument("--definition-file", required=True, help="Path to the selection summary JSON definition.")
    parser.add_argument("--output-file", required=True, help="Path to the generated phase03 workbook.")
    parser.add_argument("--log-file", required=True, help="Path to the generated phase03 log JSON file.")
    parser.add_argument("--progress-file", default="", help="Optional JSON progress file updated while NASA POWER rows are processed.")
    parser.add_argument("--skip-soil-enrichment", default="0", help="Skip SoilGrids enrichment when the workbook already includes soil columns.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    progress_file = Path(args.progress_file).expanduser().resolve() if str(args.progress_file).strip() else None
    result = create_phase03_workbook(
        phase02_workbook=Path(args.phase02_workbook).expanduser().resolve(),
        definition_file=Path(args.definition_file).expanduser().resolve(),
        output_file=Path(args.output_file).expanduser().resolve(),
        log_file=Path(args.log_file).expanduser().resolve(),
        progress_file=progress_file,
        skip_soil_enrichment=str(args.skip_soil_enrichment).strip().lower() in {"1", "true", "yes", "on"},
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
