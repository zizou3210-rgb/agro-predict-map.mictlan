from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Iterable


MAX_REGION_LAT_SPAN = 10.0
MAX_REGION_LON_SPAN = 10.0
NASA_GRID_CELL_SIZE_KM = 25.0
KM_PER_DEGREE_LATITUDE = 111.32


@dataclass(frozen=True)
class CountryBounds:
    country: str
    latitude_min: float
    latitude_max: float
    longitude_min: float
    longitude_max: float


@dataclass(frozen=True)
class RegionalBounds:
    label: str
    latitude_min: float
    latitude_max: float
    longitude_min: float
    longitude_max: float


COUNTRY_BOUNDS = {
    "KENYA": CountryBounds(
        country="Kenya",
        latitude_min=-5.5,
        latitude_max=5.5,
        longitude_min=33.0,
        longitude_max=42.5,
    ),
    "TANZANIA": CountryBounds(
        country="Tanzania",
        latitude_min=-12.5,
        latitude_max=-0.5,
        longitude_min=28.0,
        longitude_max=41.5,
    ),
    "UGANDA": CountryBounds(
        country="Uganda",
        latitude_min=-2.0,
        latitude_max=5.0,
        longitude_min=29.0,
        longitude_max=35.5,
    ),
}


def normalize_country_key(country: str) -> str:
    return str(country or "").strip().upper()


def get_country_bounds(country: str) -> CountryBounds:
    normalized = normalize_country_key(country)
    if normalized not in COUNTRY_BOUNDS:
        available = ", ".join(bounds.country for bounds in sorted(COUNTRY_BOUNDS.values(), key=lambda item: item.country))
        raise ValueError(f"Unsupported regional country '{country}'. Supported countries: {available}.")
    return COUNTRY_BOUNDS[normalized]


def _build_axis_tiles(start: float, end: float, max_span: float) -> list[tuple[float, float]]:
    tiles: list[tuple[float, float]] = []
    cursor = float(start)
    safe_end = float(end)
    while cursor < safe_end:
        tile_end = min(cursor + max_span, safe_end)
        tiles.append((round(cursor, 6), round(tile_end, 6)))
        cursor = tile_end
    return tiles


def validate_regional_bounds(
    latitude_min: float,
    latitude_max: float,
    longitude_min: float,
    longitude_max: float,
    *,
    label: str = "Manual bounds",
) -> RegionalBounds:
    normalized = RegionalBounds(
        label=str(label or "Manual bounds").strip() or "Manual bounds",
        latitude_min=round(float(latitude_min), 6),
        latitude_max=round(float(latitude_max), 6),
        longitude_min=round(float(longitude_min), 6),
        longitude_max=round(float(longitude_max), 6),
    )
    if normalized.latitude_min >= normalized.latitude_max:
        raise ValueError("The regional bounding box requires latitude_min < latitude_max.")
    if normalized.longitude_min >= normalized.longitude_max:
        raise ValueError("The regional bounding box requires longitude_min < longitude_max.")
    if normalized.latitude_min < -90 or normalized.latitude_max > 90:
        raise ValueError("Latitude bounds must stay inside [-90, 90].")
    if normalized.longitude_min < -180 or normalized.longitude_max > 180:
        raise ValueError("Longitude bounds must stay inside [-180, 180].")
    return normalized


def build_country_tiles(
    country: str,
    *,
    max_lat_span: float = MAX_REGION_LAT_SPAN,
    max_lon_span: float = MAX_REGION_LON_SPAN,
) -> list[dict[str, float | int | str]]:
    bounds = get_country_bounds(country)
    lat_tiles = _build_axis_tiles(bounds.latitude_min, bounds.latitude_max, max_lat_span)
    lon_tiles = _build_axis_tiles(bounds.longitude_min, bounds.longitude_max, max_lon_span)
    tiles: list[dict[str, float | int | str]] = []
    tile_index = 1
    for lat_min, lat_max in lat_tiles:
        for lon_min, lon_max in lon_tiles:
            tiles.append(
                {
                    "tile_index": tile_index,
                    "country": bounds.country,
                    "latitude_min": lat_min,
                    "latitude_max": lat_max,
                    "longitude_min": lon_min,
                    "longitude_max": lon_max,
                }
            )
            tile_index += 1
    return tiles


def build_regional_tiles(
    bounds: RegionalBounds,
    *,
    max_lat_span: float = MAX_REGION_LAT_SPAN,
    max_lon_span: float = MAX_REGION_LON_SPAN,
) -> list[dict[str, float | int | str]]:
    lat_tiles = _build_axis_tiles(bounds.latitude_min, bounds.latitude_max, max_lat_span)
    lon_tiles = _build_axis_tiles(bounds.longitude_min, bounds.longitude_max, max_lon_span)
    tiles: list[dict[str, float | int | str]] = []
    tile_index = 1
    for lat_min, lat_max in lat_tiles:
        for lon_min, lon_max in lon_tiles:
            tiles.append(
                {
                    "tile_index": tile_index,
                    "label": bounds.label,
                    "latitude_min": lat_min,
                    "latitude_max": lat_max,
                    "longitude_min": lon_min,
                    "longitude_max": lon_max,
                }
            )
            tile_index += 1
    return tiles


def build_country_bounds_payload(country: str) -> dict[str, object]:
    bounds = get_country_bounds(country)
    tiles = build_country_tiles(country)
    return {
        "country": bounds.country,
        "bounds": asdict(bounds),
        "tiles": tiles,
        "tile_count": len(tiles),
        "constraints": {
            "max_region_lat_span": MAX_REGION_LAT_SPAN,
            "max_region_lon_span": MAX_REGION_LON_SPAN,
        },
    }


def list_supported_country_bounds() -> list[dict[str, object]]:
    return [build_country_bounds_payload(bounds.country) for bounds in sorted(COUNTRY_BOUNDS.values(), key=lambda item: item.country)]


def iter_country_tile_bounds(country: str) -> Iterable[tuple[float, float, float, float]]:
    for tile in build_country_tiles(country):
        yield (
            float(tile["latitude_min"]),
            float(tile["latitude_max"]),
            float(tile["longitude_min"]),
            float(tile["longitude_max"]),
        )


def build_manual_bounds_payload(
    latitude_min: float,
    latitude_max: float,
    longitude_min: float,
    longitude_max: float,
    *,
    label: str = "Manual bounds",
) -> dict[str, object]:
    bounds = validate_regional_bounds(
        latitude_min,
        latitude_max,
        longitude_min,
        longitude_max,
        label=label,
    )
    tiles = build_regional_tiles(bounds)
    return {
        "label": bounds.label,
        "bounds": asdict(bounds),
        "tiles": tiles,
        "tile_count": len(tiles),
        "constraints": {
            "max_region_lat_span": MAX_REGION_LAT_SPAN,
            "max_region_lon_span": MAX_REGION_LON_SPAN,
        },
    }


def _build_manual_grid_steps(bounds: RegionalBounds, cell_size_km: float) -> tuple[float, float]:
    if cell_size_km <= 0:
        raise ValueError("The NASA grid cell size must be greater than zero.")
    latitude_step = cell_size_km / KM_PER_DEGREE_LATITUDE
    mean_latitude = (bounds.latitude_min + bounds.latitude_max) / 2
    cosine = math.cos(math.radians(mean_latitude))
    safe_cosine = max(abs(cosine), 0.1)
    longitude_step = cell_size_km / (KM_PER_DEGREE_LATITUDE * safe_cosine)
    return latitude_step, longitude_step


def build_manual_grid_cells(
    latitude_min: float,
    latitude_max: float,
    longitude_min: float,
    longitude_max: float,
    *,
    label: str = "Manual bounds",
    cell_size_km: float = NASA_GRID_CELL_SIZE_KM,
) -> list[dict[str, float | int | str]]:
    bounds = validate_regional_bounds(
        latitude_min,
        latitude_max,
        longitude_min,
        longitude_max,
        label=label,
    )
    latitude_step, longitude_step = _build_manual_grid_steps(bounds, cell_size_km)
    cells: list[dict[str, float | int | str]] = []
    row_index = 0
    latitude_cursor = bounds.latitude_min
    grid_cell_index = 1
    while latitude_cursor < bounds.latitude_max:
        cell_latitude_min = latitude_cursor
        cell_latitude_max = min(latitude_cursor + latitude_step, bounds.latitude_max)
        row_index += 1
        column_index = 0
        longitude_cursor = bounds.longitude_min
        while longitude_cursor < bounds.longitude_max:
            cell_longitude_min = longitude_cursor
            cell_longitude_max = min(longitude_cursor + longitude_step, bounds.longitude_max)
            column_index += 1
            center_latitude = round((cell_latitude_min + cell_latitude_max) / 2, 6)
            center_longitude = round((cell_longitude_min + cell_longitude_max) / 2, 6)
            cells.append(
                {
                    "grid_cell_index": grid_cell_index,
                    "grid_cell_id": f"{bounds.label}:R{row_index}C{column_index}",
                    "grid_row_index": row_index,
                    "grid_column_index": column_index,
                    "label": bounds.label,
                    "latitude_min": round(cell_latitude_min, 6),
                    "latitude_max": round(cell_latitude_max, 6),
                    "longitude_min": round(cell_longitude_min, 6),
                    "longitude_max": round(cell_longitude_max, 6),
                    "center_latitude": center_latitude,
                    "center_longitude": center_longitude,
                }
            )
            grid_cell_index += 1
            longitude_cursor = cell_longitude_max
        latitude_cursor = cell_latitude_max
    return cells


def build_manual_grid_payload(
    latitude_min: float,
    latitude_max: float,
    longitude_min: float,
    longitude_max: float,
    *,
    label: str = "Manual bounds",
    cell_size_km: float = NASA_GRID_CELL_SIZE_KM,
) -> dict[str, object]:
    bounds = validate_regional_bounds(
        latitude_min,
        latitude_max,
        longitude_min,
        longitude_max,
        label=label,
    )
    cells = build_manual_grid_cells(
        bounds.latitude_min,
        bounds.latitude_max,
        bounds.longitude_min,
        bounds.longitude_max,
        label=bounds.label,
        cell_size_km=cell_size_km,
    )
    return {
        "label": bounds.label,
        "bounds": asdict(bounds),
        "grid_resolution_km": cell_size_km,
        "grid_cell_count": len(cells),
        "cells": cells,
    }


def iter_manual_tile_bounds(
    latitude_min: float,
    latitude_max: float,
    longitude_min: float,
    longitude_max: float,
    *,
    label: str = "Manual bounds",
) -> Iterable[tuple[float, float, float, float]]:
    bounds = validate_regional_bounds(
        latitude_min,
        latitude_max,
        longitude_min,
        longitude_max,
        label=label,
    )
    for tile in build_regional_tiles(bounds):
        yield (
            float(tile["latitude_min"]),
            float(tile["latitude_max"]),
            float(tile["longitude_min"]),
            float(tile["longitude_max"]),
        )
