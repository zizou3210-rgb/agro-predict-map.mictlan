"""Download aligned SoilGrids WCS subsets and classify local pixel samples.

The current SoilGrids release supplies texture, not depth to bedrock. Depth
therefore keeps the existing default unless a valid legacy depth is available.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
import time
import xml.etree.ElementTree as ET
from collections import defaultdict
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from config_env import resolve_shared_cache_dir
from preprocess import soil_enrichment as soils

try:
    import rasterio
    from rasterio.crs import CRS
    from rasterio.warp import transform
    from rasterio.windows import Window
except ImportError:
    rasterio = None

PROPERTIES = ("sand", "silt", "clay")
DEPTH = "0-5cm"
NATIVE_CRS = "+proj=igh +datum=WGS84 +units=m +no_defs"
CRS_URL = "http://www.opengis.net/def/crs/EPSG/0/152160"
GML = "{http://www.opengis.net/gml/3.2}"
WCS = "{http://www.opengis.net/wcs/2.0}"


@dataclass(frozen=True)
class RasterConfig:
    endpoint: str = "https://maps.isric.org/mapserv"
    revision: str = "soilgrids2-mean-v1"
    tile_pixels: int = 512
    download_workers: int = 2
    timeout: int = 60

    @classmethod
    def from_env(cls):
        config = cls(
            endpoint=os.environ.get("APP_SOIL_WCS_ENDPOINT", cls.endpoint).strip(),
            revision=os.environ.get("APP_SOIL_DATA_VERSION", cls.revision).strip(),
            tile_pixels=int(os.environ.get("APP_SOIL_RASTER_TILE_PIXELS", "512")),
            download_workers=int(os.environ.get("APP_SOIL_DOWNLOAD_MAX_WORKERS", "2")),
            timeout=int(os.environ.get("APP_SOIL_DOWNLOAD_TIMEOUT_SECONDS", "60")),
        )
        if not config.endpoint or not config.revision or not 16 <= config.tile_pixels <= 1024:
            raise ValueError("Invalid soil raster endpoint/version/tile size.")
        if not 1 <= config.download_workers <= 8 or not 1 <= config.timeout <= 300:
            raise ValueError("Invalid soil raster download workers or timeout.")
        return config

    @property
    def signature(self):
        # Tile size only changes the download partition, not the sampled values.
        payload = [self.endpoint, self.revision, DEPTH, "mean", NATIVE_CRS, "g/kg", "classification-v1"]
        return hashlib.sha256(json.dumps(payload).encode()).hexdigest()[:24]

    def point_key(self, point_id):
        return f"soil-raster-v1|{self.signature}|{point_id}"


@dataclass(frozen=True)
class CoverageGrid:
    left: float
    top: float
    step: float
    width: int
    height: int

    def tile_bounds(self, tile_id, tile_pixels):
        tile_row, tile_col = tile_id
        row, col = tile_row * tile_pixels, tile_col * tile_pixels
        width = min(tile_pixels, self.width - col)
        height = min(tile_pixels, self.height - row)
        if width <= 0 or height <= 0:
            raise ValueError("Soil tile outside coverage.")
        left, top = self.left + col * self.step, self.top - row * self.step
        return left, top - height * self.step, left + width * self.step, top


def parse_coverage_description(raw, property_name):
    try:
        document = ET.fromstring(raw)
        coverage_id = document.findtext(f".//{WCS}CoverageId")
        envelope = document.find(f".//{GML}Envelope")
        grid = document.find(f".//{GML}RectifiedGrid")
        origin = [float(value) for value in grid.findtext(f".//{GML}pos").split()]
        offsets = [[float(value) for value in item.text.split()] for item in grid.findall(f"{GML}offsetVector")]
        low = [int(value) for value in grid.findtext(f".//{GML}low").split()]
        high = [int(value) for value in grid.findtext(f".//{GML}high").split()]
        if coverage_id != f"{property_name}_{DEPTH}_mean" or envelope.get("srsName") != CRS_URL:
            raise ValueError("Unexpected soil coverage or projection.")
        if low != [0, 0] or offsets != [[250.0, 0.0], [0.0, -250.0]]:
            raise ValueError("Soil source must retain its native aligned 250m grid.")
        return CoverageGrid(origin[0] - 125, origin[1] + 125, 250, high[0] + 1, high[1] + 1)
    except (ET.ParseError, AttributeError, TypeError, IndexError) as error:
        raise ValueError(f"Invalid WCS description for {property_name}.") from error


def wcs_url(config, property_name, request_name, *, bounds=None):
    params = [
        ("map", f"/map/{property_name}.map"), ("SERVICE", "WCS"),
        ("VERSION", "2.0.1"), ("REQUEST", request_name),
        ("COVERAGEID", f"{property_name}_{DEPTH}_mean"),
    ]
    if bounds is not None:
        left, bottom, right, top = bounds
        params.extend([
            ("FORMAT", "GEOTIFF_INT16"), ("SUBSETTINGCRS", CRS_URL), ("OUTPUTCRS", CRS_URL),
            ("SUBSET", f"X({left:.3f},{right:.3f})"),
            ("SUBSET", f"Y({bottom:.3f},{top:.3f})"),
        ])
    return config.endpoint + ("&" if "?" in config.endpoint else "?") + urlencode(params)


def _download(url, destination, timeout, *, max_bytes):
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = Request(url, headers={"User-Agent": "AgroPredictMap SoilGrids regional raster reader"})
    size = 0
    with urlopen(request, timeout=timeout) as response, destination.open("wb") as output:
        while chunk := response.read(128 * 1024):
            size += len(chunk)
            if size > max_bytes:
                raise ValueError("Soil download exceeds the maximum subset size.")
            output.write(chunk)
    if size == 0:
        raise ValueError("Empty soil response.")


def _temporary_path(directory):
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=directory, suffix=".part", delete=False) as temporary:
        return Path(temporary.name)


def load_coverage_grid(config, property_name, cache_dir):
    path = cache_dir / f"{property_name}_{DEPTH}_mean.xml"
    if path.exists():
        try:
            return parse_coverage_description(path.read_bytes(), property_name)
        except (OSError, ValueError):
            pass
    temporary = _temporary_path(cache_dir)
    try:
        _download(wcs_url(config, property_name, "DescribeCoverage"), temporary, config.timeout, max_bytes=2 * 1024 * 1024)
        grid = parse_coverage_description(temporary.read_bytes(), property_name)
        os.replace(temporary, path)
        return grid
    finally:
        temporary.unlink(missing_ok=True)


def validate_tile(path, grid, tile_id, tile_pixels, *, annotate=False, property_name=None):
    left, bottom, right, top = grid.tile_bounds(tile_id, tile_pixels)
    expected_width = round((right - left) / grid.step)
    expected_height = round((top - bottom) / grid.step)
    with rasterio.open(path, "r+" if annotate else "r") as raster:
        expected = (grid.step, 0, left, 0, -grid.step, top)
        if raster.count != 1 or (raster.width, raster.height) != (expected_width, expected_height):
            raise ValueError("Unexpected soil subset dimensions or bands.")
        if any(abs(actual - wanted) > 0.01 for actual, wanted in zip(tuple(raster.transform)[:6], expected)):
            raise ValueError("Soil subset is shifted or resampled.")
        native = CRS.from_string(NATIVE_CRS)
        if raster.crs is None and annotate:
            # MapServer can omit the custom CRS. Geometry was verified above
            # against the WCS description before attaching its declared CRS.
            raster.crs = native
        if raster.crs != native:
            raise ValueError("Unexpected or missing soil subset CRS.")
        if raster.scales != (1.0,) or raster.offsets != (0.0,):
            raise ValueError("Unexpected scale/offset in soil fractions.")
        raster.read(1)  # Decode the full bounded subset to catch truncated blocks.
        if annotate:
            raster.update_tags(soil_property=property_name, soil_depth=DEPTH, soil_statistic="mean", soil_units="g/kg")


def prepare_tile(config, grid, property_name, tile_id, cache_dir):
    path = cache_dir / f"tiles-{config.tile_pixels}" / f"{property_name}_R{tile_id[0]}C{tile_id[1]}.tif"
    if path.exists():
        try:
            validate_tile(path, grid, tile_id, config.tile_pixels)
            return path, False
        except (OSError, ValueError, rasterio.errors.RasterioError):
            pass
    path.parent.mkdir(parents=True, exist_ok=True)
    last_error = None
    for attempt in range(2):
        temporary = _temporary_path(path.parent)
        try:
            _download(wcs_url(config, property_name, "GetCoverage", bounds=grid.tile_bounds(tile_id, config.tile_pixels)),
                      temporary, config.timeout, max_bytes=32 * 1024 * 1024)
            validate_tile(temporary, grid, tile_id, config.tile_pixels, annotate=True, property_name=property_name)
            os.replace(temporary, path)
            return path, True
        except (OSError, ValueError, rasterio.errors.RasterioError) as error:
            last_error = error
        finally:
            temporary.unlink(missing_ok=True)
        if attempt == 0:
            time.sleep(1)
    raise RuntimeError(f"Could not prepare SoilGrids {property_name} tile {tile_id}: {last_error}") from last_error


def bounded_results(items, function, workers):
    """Only two tasks per worker are submitted; heartbeat results keep UI alive."""
    with ThreadPoolExecutor(max_workers=workers) as executor:
        queue = iter(items)
        pending = set()
        exhausted = False
        while pending or not exhausted:
            while len(pending) < workers * 2 and not exhausted:
                item = next(queue, None)
                if item is None:
                    exhausted = True
                else:
                    pending.add(executor.submit(function, item))
            if not pending:
                break
            done, _ = wait(pending, timeout=2, return_when=FIRST_COMPLETED)
            if not done:
                yield None
            for future in done:
                pending.remove(future)
                yield future.result()


def plan_tiles(point_tasks, grid, tile_pixels):
    groups = defaultdict(list)
    outside = []
    batch_size = 4096
    for start in range(0, len(point_tasks), batch_size):
        batch = point_tasks[start:start + batch_size]
        xs, ys = transform("EPSG:4326", NATIVE_CRS, [p[2] for p in batch], [p[1] for p in batch])
        for task, x, y in zip(batch, xs, ys):
            if not math.isfinite(x) or not math.isfinite(y):
                outside.append(task[0])
                continue
            col, row = math.floor((x - grid.left) / grid.step), math.floor((grid.top - y) / grid.step)
            if not 0 <= col < grid.width or not 0 <= row < grid.height:
                outside.append(task[0])
            else:
                groups[(row // tile_pixels, col // tile_pixels)].append((task[0], row % tile_pixels, col % tile_pixels))
    return dict(groups), outside


def sample_tile(tile_id, points, paths, legacy_depths):
    result = {}
    block_reads = 0
    with ExitStack() as stack:
        layers = {prop: stack.enter_context(rasterio.open(paths[(prop, tile_id)])) for prop in PROPERTIES}
        first = layers["sand"]
        block_height, block_width = first.block_shapes[0]
        blocks = defaultdict(list)
        for point_id, row, col in points:
            blocks[(row // block_height, col // block_width)].append((point_id, row, col))
        for block_points in blocks.values():
            row_min = min(p[1] for p in block_points)
            row_max = max(p[1] for p in block_points)
            col_min = min(p[2] for p in block_points)
            col_max = max(p[2] for p in block_points)
            window = Window(col_min, row_min, col_max - col_min + 1, row_max - row_min + 1)
            samples = {prop: raster.read(1, window=window, masked=True) for prop, raster in layers.items()}
            block_reads += len(layers)
            for point_id, row, col in block_points:
                values = {}
                for prop, data in samples.items():
                    value = data[row - row_min, col - col_min]
                    numeric = float(value) if not bool(getattr(value, "mask", False)) else float("nan")
                    values[prop] = numeric if math.isfinite(numeric) and 0 <= numeric <= 1000 else None
                valid = all(value is not None for value in values.values()) and sum(value or 0 for value in values.values()) > 0
                depth = legacy_depths.get(point_id)
                record = soils.build_soil_record(
                    sand_gkg=values["sand"] if valid else None,
                    silt_gkg=values["silt"] if valid else None,
                    clay_gkg=values["clay"] if valid else None,
                    depth_to_bedrock_cm=depth,
                    source="soilgrids_wcs" if valid else "fallback_default",
                )
                record.update(soil_texture_depth=DEPTH, soil_texture_statistic="mean",
                              soil_texture_status="valid" if valid else "nodata",
                              soil_depth_source="legacy_cache" if depth is not None else "fallback_default")
                result[point_id] = record
    return result, block_reads


def enrich_records(records, cache_path, *, progress_callback=None, worker_count=4, config=None):
    if rasterio is None:
        raise RuntimeError("Rasterio is required for regional soil rasters; no per-point REST fallback was started.")
    config = config or RasterConfig.from_env()
    cache_path = Path(cache_path)
    cache_dir = resolve_shared_cache_dir() / "soil_rasters" / config.signature
    point_coordinates = {}
    for record in records:
        lat, lon = soils.parse_float(record.get(soils.LAT_HEADER)), soils.parse_float(record.get(soils.LON_HEADER))
        if lat is not None and lon is not None and math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180:
            point_coordinates.setdefault(soils.cache_key(lat, lon), (lat, lon))
    tasks = [(key, *coordinates) for key, coordinates in point_coordinates.items()]
    stage_started = time.monotonic()
    last_stage = None
    last_report = 0.0

    def report(percent, stage, completed, total, unit, message, **extra):
        nonlocal stage_started, last_stage, last_report
        now = time.monotonic()
        changed = stage != last_stage
        if changed:
            stage_started, last_stage = now, stage
        if not progress_callback or (not changed and completed != total and now - last_report < 1):
            return
        last_report = now
        elapsed = now - stage_started
        rate = completed / elapsed if elapsed > 0 else 0
        progress_callback(percent, stage, message, {
            "phase": "phase03", "soil_provider": "rasters", "stage_completed": completed,
            "stage_total": total, "stage_unit": unit, "stage_percent": round(completed / total * 100, 3) if total else 100,
            "stage_elapsed_seconds": round(elapsed, 1), "stage_rate_per_second": round(rate, 3),
            "stage_eta_seconds": round((total - completed) / rate, 1) if rate and completed >= 5 else None,
            **extra,
        })

    report(94, "Checking soil raster cache", 0, len(tasks), "points", "Checking soil samples from the regional raster provider.")
    payload = soils.normalize_cache_payload(soils.load_cache_payload(cache_path))
    keys = {point_id: config.point_key(point_id) for point_id in point_coordinates}
    missing_cache_keys = [key for key in keys.values() if key not in payload["points"]]
    payload["points"].update(soils.get_soil_cache_entries(missing_cache_keys))
    resolved = {}
    for point_id, key in keys.items():
        cached = payload["points"].get(key)
        if isinstance(cached, dict) and cached.get("soil_raster_signature") == config.signature:
            resolved[point_id] = cached
    cached_count = len(resolved)
    missing = [task for task in tasks if task[0] not in resolved]
    report(94, "Checking soil raster cache", len(tasks), len(tasks), "points",
           f"Reused {cached_count}/{len(tasks)} regional soil samples.", soil_cache_hits=cached_count)
    downloaded = reused_files = read_blocks = persisted = 0
    fallback_count = sum(record.get("soil_source") == "fallback_default" for record in resolved.values())
    depth_defaults = sum(record.get("soil_depth_source") == "fallback_default" for record in resolved.values())
    paths = {}
    pending_samples = {}
    flush_at = time.monotonic()

    def persist(force=False):
        nonlocal persisted, flush_at
        if pending_samples and (force or len(pending_samples) >= 512 or time.monotonic() - flush_at >= 5):
            soils.upsert_soil_cache_entries(pending_samples)
            persisted += len(pending_samples)
            pending_samples.clear()
            flush_at = time.monotonic()

    try:
        if missing:
            grids = []
            report(94, "Planning soil raster downloads", 0, 3, "layers", "Checking native grids for sand, silt and clay at 0–5 cm (mean).")
            for prop in PROPERTIES:
                grids.append(load_coverage_grid(config, prop, cache_dir))
                report(94, "Planning soil raster downloads", len(grids), 3, "layers", f"Verified {len(grids)}/3 soil layer grids.")
            if any(grid != grids[0] for grid in grids[1:]):
                raise ValueError("Soil property grids are not aligned; cannot combine texture fractions.")
            grid = grids[0]
            groups, outside = plan_tiles(missing, grid, config.tile_pixels)
            jobs = [(prop, tile_id) for tile_id in sorted(groups) for prop in PROPERTIES]
            report(94, "Downloading soil rasters", 0, len(jobs), "files",
                   f"Preparing {len(jobs)} regional soil files with {config.download_workers} download workers.",
                   soil_download_workers=config.download_workers, soil_raster_files_total=len(jobs))

            def download_job(job):
                prop, tile_id = job
                path, fresh = prepare_tile(config, grid, prop, tile_id, cache_dir)
                return prop, tile_id, path, fresh

            finished = 0
            for result in bounded_results(jobs, download_job, config.download_workers):
                if result is not None:
                    prop, tile_id, path, fresh = result
                    paths[(prop, tile_id)] = path
                    downloaded += int(fresh)
                    reused_files += int(not fresh)
                    finished += 1
                report(round(94 + (finished / len(jobs) if jobs else 1), 2), "Downloading soil rasters", finished, len(jobs), "files",
                       f"Soil files ready: {finished}/{len(jobs)}. Downloaded: {downloaded}; cached: {reused_files}.",
                       soil_raster_files_downloaded=downloaded, soil_raster_files_cached=reused_files,
                       soil_download_workers=config.download_workers)

            # Reuse a known depth only when it was a real legacy measurement.
            legacy = soils.get_soil_cache_entries([task[0] for task in missing])
            legacy_depths = {}
            for point_id, _, _ in missing:
                previous = payload["points"].get(point_id) or legacy.get(point_id) or {}
                depth = soils.parse_float(previous.get("depth_to_bedrock_cm"))
                if previous.get("soil_source") != "fallback_default" and depth is not None and math.isfinite(depth) and depth >= 0:
                    legacy_depths[point_id] = depth

            def accept(batch):
                nonlocal fallback_count, depth_defaults
                for point_id, record in batch.items():
                    record["soil_raster_signature"] = config.signature
                    resolved[point_id] = record
                    pending_samples[keys[point_id]] = record
                    fallback_count += int(record.get("soil_source") == "fallback_default")
                    depth_defaults += int(record.get("soil_depth_source") == "fallback_default")
                persist()

            if outside:
                accept({key: {**soils.build_soil_record(sand_gkg=None, silt_gkg=None, clay_gkg=None,
                            depth_to_bedrock_cm=legacy_depths.get(key), source="fallback_default"),
                              "soil_texture_status": "outside_coverage", "soil_depth_source": "fallback_default"} for key in outside})

            def sample_job(item):
                tile_id, points = item
                return sample_tile(tile_id, points, paths, legacy_depths)

            report(95, "Sampling soil raster blocks", len(resolved), len(tasks), "points",
                   "Sampling local soil pixels; no per-point REST requests.", soil_parallel_workers=worker_count)
            for result in bounded_results(groups.items(), sample_job, max(1, worker_count)):
                if result is not None:
                    batch, blocks = result
                    read_blocks += blocks
                    accept(batch)
                fraction = len(resolved) / len(tasks) if tasks else 1
                report(round(95 + fraction * 1.5, 2), "Sampling soil raster blocks", len(resolved), len(tasks), "points",
                       f"Soil points sampled: {len(resolved)}/{len(tasks)}. Texture NoData/defaults: {fallback_count}; depth defaults: {depth_defaults}.",
                       soil_parallel_workers=worker_count, soil_cache_hits=cached_count, soil_fallback_cells=fallback_count,
                       soil_depth_default_cells=depth_defaults, soil_raster_blocks_read=read_blocks, soil_persisted_points=persisted)
    finally:
        persist(force=True)

    report(96.5, "Saving soil raster results", len(resolved), len(tasks), "points", "Saving classified soil samples and their data provenance.")
    if persisted:
        payload["points"].update({keys[key]: value for key, value in resolved.items()})
        soils.write_cache_payload(cache_path, payload)
    output = []
    enriched_rows = 0
    for source in records:
        updated = dict(source)
        lat, lon = soils.parse_float(source.get(soils.LAT_HEADER)), soils.parse_float(source.get(soils.LON_HEADER))
        record = resolved.get(soils.cache_key(lat, lon)) if lat is not None and lon is not None else None
        if record is not None:
            for field in (soils.SOIL_TEXTURE_HEADER, soils.SOIL_DEPTH_HEADER, "soil_source", "soil_texture_usda_class"):
                updated[field] = record[field]
            enriched_rows += 1
        output.append(updated)
    report(97, "Soil enrichment complete", len(resolved), len(tasks), "points",
           f"Soil enrichment finished. Texture defaults: {fallback_count}; depth defaults: {depth_defaults}.",
           soil_fallback_cells=fallback_count, soil_depth_default_cells=depth_defaults, soil_persisted_points=persisted)
    return output, {
        "soil_provider": "rasters", "soil_enriched_rows": enriched_rows, "soil_enriched_cells": len(resolved),
        "soil_unique_points_total": len(tasks), "soil_cache_hits": cached_count,
        "soil_service_queries": 0, "soil_service_success_cells": 0,
        "soil_raster_valid_cells": len(resolved) - fallback_count, "soil_fallback_cells": fallback_count,
        "soil_depth_default_cells": depth_defaults, "soil_parallel_workers": worker_count,
        "soil_download_workers": config.download_workers, "soil_raster_files_downloaded": downloaded,
        "soil_raster_files_cached": reused_files, "soil_raster_blocks_read": read_blocks,
        "soil_persisted_points": persisted, "soil_texture_depth": DEPTH, "soil_texture_statistic": "mean",
        "soil_data_version": config.revision, "soil_raster_signature": config.signature,
        "soil_depth_note": "SoilGrids 2 supplies texture; depth to bedrock uses valid legacy cache or the existing default.",
    }
