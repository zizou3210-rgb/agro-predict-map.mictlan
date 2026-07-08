from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


SOIL_TEXTURE_HEADER = "Soil type/texture"
SOIL_DEPTH_HEADER = "Soil Depth (cm)-How deep do you expect maize roots to grow in this soil?"
LAT_HEADER = "_GPS coordinates_latitude"
LON_HEADER = "_GPS coordinates_longitude"
FORECAST_GRID_CELL_ID_HEADER = "Forecast grid cell id"
SOIL_CACHE_VERSION = 1
SOIL_HTTP_TIMEOUT_SECONDS = 30
SOIL_REQUEST_HEADERS = {"User-Agent": "app preprocess soil enrichment"}
DEFAULT_SOILGRIDS_ENDPOINT = os.environ.get(
    "APP_SOILGRIDS_ENDPOINT",
    "https://rest.isric.org/soilgrids/v2.0/properties/query",
).strip()
TEXTURE_DEPTH_PREFERENCE = (
    "0-5cm",
    "0-30cm",
    "5-15cm",
    "15-30cm",
    "30-60cm",
    "60-100cm",
    "100-200cm",
)
DEFAULT_TEXTURE_BUCKET = "Loam"
DEFAULT_DEPTH_BUCKET = "100cm o mas"


def is_blank(value: object) -> bool:
    return value is None or str(value).strip() == ""


def parse_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        numeric = float(value)
        if numeric != numeric:
            return None
        return numeric
    text = str(value).strip().replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def normalize_texture_fractions(
    sand_gkg: float,
    silt_gkg: float,
    clay_gkg: float,
) -> tuple[float, float, float]:
    sand = sand_gkg / 10.0
    silt = silt_gkg / 10.0
    clay = clay_gkg / 10.0
    total = sand + silt + clay
    if total <= 0:
        raise ValueError("Invalid sand/silt/clay totals.")
    return (
        sand * 100.0 / total,
        silt * 100.0 / total,
        clay * 100.0 / total,
    )


def usda_texture_class_from_fractions(
    sand_gkg: float,
    silt_gkg: float,
    clay_gkg: float,
) -> str:
    sand, silt, clay = normalize_texture_fractions(sand_gkg, silt_gkg, clay_gkg)

    if clay >= 40 and silt >= 40:
        return "Silty Clay"
    if clay >= 35 and sand >= 45:
        return "Sandy Clay"
    if clay >= 40:
        return "Clay"
    if 27 <= clay < 40 and silt >= 40:
        return "Silty Clay Loam"
    if 27 <= clay < 40 and 20 < sand < 45:
        return "Clay Loam"
    if 20 <= clay < 35 and sand >= 45:
        return "Sandy Clay Loam"
    if silt >= 80 and clay < 12:
        return "Silt"
    if silt >= 50 and clay < 27:
        return "Silt Loam"
    if sand >= 85 and clay < 10 and silt < 15:
        return "Sand"
    if sand >= 70 and clay < 15 and silt <= 30:
        return "Loamy Sand"
    if 43 <= sand < 85 and clay < 20:
        return "Sandy Loam"
    if 7 <= clay < 27 and 28 <= silt < 50 and sand <= 52:
        return "Loam"
    if clay < 7 and silt < 50 and sand < 52:
        return "Loam"
    return "Loam"


def pipeline_texture_bucket(texture_class: str) -> str:
    mapping = {
        "Clay": "Clay Loam",
        "Clay Loam": "Clay Loam",
        "Sandy Clay": "Clay Loam",
        "Sandy Clay Loam": "Sandy Loam",
        "Sandy Loam": "Sandy Loam",
        "Loamy Sand": "Sandy Loam",
        "Sand": "Sandy Loam",
        "Loam": "Loam",
        "Silt Loam": "Silty Loam",
        "Silt": "Silty Loam",
        "Silty Clay Loam": "Silty Loam",
        "Silty Clay": "Silty Loam",
    }
    return mapping.get(str(texture_class).strip(), DEFAULT_TEXTURE_BUCKET)


def pipeline_soil_depth_bucket(depth_to_bedrock_cm: float | None) -> str:
    if depth_to_bedrock_cm is None:
        return DEFAULT_DEPTH_BUCKET
    if depth_to_bedrock_cm < 62.5:
        return "50cm"
    if depth_to_bedrock_cm < 87.5:
        return "75cm"
    return "100cm o mas"


def cache_key(latitude: float, longitude: float) -> str:
    return f"{latitude:.6f},{longitude:.6f}"


def load_cache_payload(cache_path: Path) -> dict[str, Any]:
    if not cache_path.exists():
        return {}
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def write_cache_payload(cache_path: Path, payload: dict[str, Any]) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = cache_path.with_suffix(cache_path.suffix + ".tmp")
    temporary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary_path.replace(cache_path)


def _select_nested_depth_value(mapping: dict[str, Any]) -> float | None:
    direct = next(
        (
            parse_float(mapping.get(key))
            for key in ("mean", "median", "value", "val")
            if key in mapping and parse_float(mapping.get(key)) is not None
        ),
        None,
    )
    if direct is not None:
        return direct
    for key in TEXTURE_DEPTH_PREFERENCE:
        if key in mapping:
            nested = _extract_numeric_value(mapping[key])
            if nested is not None:
                return nested
    for value in mapping.values():
        nested = _extract_numeric_value(value)
        if nested is not None:
            return nested
    return None


def _extract_numeric_value(payload: Any) -> float | None:
    numeric = parse_float(payload)
    if numeric is not None:
        return numeric
    if isinstance(payload, dict):
        return _select_nested_depth_value(payload)
    if isinstance(payload, list):
        for item in payload:
            numeric = _extract_numeric_value(item)
            if numeric is not None:
                return numeric
    return None


def _extract_property(payload: dict[str, Any], property_name: str) -> float | None:
    if property_name in payload:
        return _extract_numeric_value(payload[property_name])
    properties = payload.get("properties")
    if isinstance(properties, dict) and property_name in properties:
        return _extract_numeric_value(properties[property_name])
    layers = payload.get("layers")
    if isinstance(layers, dict) and property_name in layers:
        return _extract_numeric_value(layers[property_name])
    for key, value in payload.items():
        if str(key).strip().lower() == property_name.lower():
            return _extract_numeric_value(value)
    return None


def _fetch_soilgrids_payload(latitude: float, longitude: float) -> dict[str, Any]:
    if not DEFAULT_SOILGRIDS_ENDPOINT:
        raise ValueError("No SoilGrids endpoint configured.")
    query = urlencode(
        {
            "lat": f"{latitude:.6f}",
            "lon": f"{longitude:.6f}",
            "property": ["sand", "silt", "clay", "depth_to_bedrock", "depth"],
            "value": ["mean"],
        },
        doseq=True,
    )
    url = f"{DEFAULT_SOILGRIDS_ENDPOINT}?{query}"
    request = Request(url, headers=SOIL_REQUEST_HEADERS)
    with urlopen(request, timeout=SOIL_HTTP_TIMEOUT_SECONDS) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Unexpected SoilGrids payload.")
    return payload


def build_soil_record(
    *,
    sand_gkg: float | None,
    silt_gkg: float | None,
    clay_gkg: float | None,
    depth_to_bedrock_cm: float | None,
    source: str,
) -> dict[str, object]:
    if sand_gkg is None or silt_gkg is None or clay_gkg is None:
        texture_bucket = DEFAULT_TEXTURE_BUCKET
        texture_class = DEFAULT_TEXTURE_BUCKET
    else:
        texture_class = usda_texture_class_from_fractions(sand_gkg, silt_gkg, clay_gkg)
        texture_bucket = pipeline_texture_bucket(texture_class)
    return {
        SOIL_TEXTURE_HEADER: texture_bucket,
        SOIL_DEPTH_HEADER: pipeline_soil_depth_bucket(depth_to_bedrock_cm),
        "soil_source": source,
        "soil_texture_usda_class": texture_class,
        "sand_gkg": sand_gkg,
        "silt_gkg": silt_gkg,
        "clay_gkg": clay_gkg,
        "depth_to_bedrock_cm": depth_to_bedrock_cm,
    }


def normalize_cache_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict) or payload.get("version") != SOIL_CACHE_VERSION:
        return {"version": SOIL_CACHE_VERSION, "points": {}}
    points = payload.get("points")
    if not isinstance(points, dict):
        payload = dict(payload)
        payload["points"] = {}
    return payload


def resolve_soil_record_from_payload(
    latitude: float,
    longitude: float,
    *,
    payload: dict[str, Any],
) -> tuple[dict[str, object], str, bool]:
    normalized_payload = normalize_cache_payload(payload)
    points = normalized_payload.setdefault("points", {})
    key = cache_key(latitude, longitude)
    cached = points.get(key)
    if isinstance(cached, dict):
        return cached, "cache_hit", False

    try:
        raw_payload = _fetch_soilgrids_payload(latitude, longitude)
        sand_gkg = _extract_property(raw_payload, "sand")
        silt_gkg = _extract_property(raw_payload, "silt")
        clay_gkg = _extract_property(raw_payload, "clay")
        depth_to_bedrock_cm = (
            _extract_property(raw_payload, "depth_to_bedrock")
            or _extract_property(raw_payload, "depth")
        )
        resolved = build_soil_record(
            sand_gkg=sand_gkg,
            silt_gkg=silt_gkg,
            clay_gkg=clay_gkg,
            depth_to_bedrock_cm=depth_to_bedrock_cm,
            source="soilgrids",
        )
        resolved_source = "soilgrids"
    except (HTTPError, URLError, TimeoutError, ValueError, OSError, json.JSONDecodeError):
        resolved = build_soil_record(
            sand_gkg=None,
            silt_gkg=None,
            clay_gkg=None,
            depth_to_bedrock_cm=None,
            source="fallback_default",
        )
        resolved_source = "fallback_default"

    points[key] = resolved
    return resolved, resolved_source, True


def resolve_soil_record(
    latitude: float,
    longitude: float,
    *,
    cache_path: Path,
) -> tuple[dict[str, object], str]:
    payload = load_cache_payload(cache_path)
    resolved, resolved_source, cache_changed = resolve_soil_record_from_payload(
        latitude,
        longitude,
        payload=payload,
    )
    if cache_changed:
        write_cache_payload(cache_path, normalize_cache_payload(payload))
    return resolved, resolved_source


def enrich_manual_bbox_prediction_soils(
    records: list[dict[str, object]],
    *,
    climate_scope: str,
    selected_model_id: str | None,
    cache_path: Path,
) -> tuple[list[dict[str, object]], dict[str, int]]:
    if climate_scope != "regional_manual" or not selected_model_id:
        return records, {
            "soil_enriched_rows": 0,
            "soil_enriched_cells": 0,
            "soil_fallback_cells": 0,
            "soil_cache_hits": 0,
            "soil_service_queries": 0,
            "soil_service_success_cells": 0,
        }

    enriched_rows = 0
    enriched_cells: set[str] = set()
    fallback_cells: set[str] = set()
    cache_hit_cells: set[str] = set()
    service_success_cells: set[str] = set()
    resolved_by_cell: dict[str, dict[str, object]] = {}
    output_records: list[dict[str, object]] = []

    for record in records:
        updated = dict(record)
        needs_texture = is_blank(updated.get(SOIL_TEXTURE_HEADER))
        needs_depth = is_blank(updated.get(SOIL_DEPTH_HEADER))
        if not needs_texture and not needs_depth:
            output_records.append(updated)
            continue

        latitude = parse_float(updated.get(LAT_HEADER))
        longitude = parse_float(updated.get(LON_HEADER))
        if latitude is None or longitude is None:
            if needs_texture:
                updated[SOIL_TEXTURE_HEADER] = DEFAULT_TEXTURE_BUCKET
            if needs_depth:
                updated[SOIL_DEPTH_HEADER] = DEFAULT_DEPTH_BUCKET
            output_records.append(updated)
            enriched_rows += 1
            continue

        cell_id = str(updated.get(FORECAST_GRID_CELL_ID_HEADER) or cache_key(latitude, longitude))
        if cell_id not in resolved_by_cell:
            resolved_by_cell[cell_id], resolved_source = resolve_soil_record(
                latitude,
                longitude,
                cache_path=cache_path,
            )
            enriched_cells.add(cell_id)
            if resolved_source == "cache_hit":
                cache_hit_cells.add(cell_id)
            elif resolved_source == "soilgrids":
                service_success_cells.add(cell_id)
            if resolved_by_cell[cell_id].get("soil_source") == "fallback_default":
                fallback_cells.add(cell_id)
        soil_record = resolved_by_cell[cell_id]

        if needs_texture:
            updated[SOIL_TEXTURE_HEADER] = soil_record[SOIL_TEXTURE_HEADER]
        if needs_depth:
            updated[SOIL_DEPTH_HEADER] = soil_record[SOIL_DEPTH_HEADER]
        output_records.append(updated)
        enriched_rows += 1

    return output_records, {
        "soil_enriched_rows": enriched_rows,
        "soil_enriched_cells": len(enriched_cells),
        "soil_fallback_cells": len(fallback_cells),
        "soil_cache_hits": len(cache_hit_cells),
        "soil_service_queries": len(enriched_cells - cache_hit_cells),
        "soil_service_success_cells": len(service_success_cells),
    }
