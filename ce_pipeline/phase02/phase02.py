#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
from datetime import date, datetime, timedelta
from pathlib import Path

PHASE01_SCRIPT = Path(__file__).resolve().parents[1] / "phase01" / "phase1.py"
WORLD_GEOJSON_FILE = Path(__file__).resolve().parents[2] / "data" / "world.geojson"
REQUIRED_INITIAL_SETTING_KEYS = (
    "target_column",
    "longitude_column",
    "latitude_column",
    "planting_date_column",
    "harvesting_date_column",
    "soil_texture_column",
    "soil_depth_column",
)


def load_phase01_module():
    spec = importlib.util.spec_from_file_location("ce_phase01", PHASE01_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"The ce_pipeline phase01 script could not be loaded: {PHASE01_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_coordinate(value: object) -> float | None:
    text = str(value or "").strip()
    if not text or text.lower() == "null":
        return None
    normalized = text.replace(",", ".")
    try:
        return float(normalized)
    except ValueError:
        return None



MIN_VALID_EXECUTION_DATE = date(1900, 1, 1)


def normalize_excel_date_text(value: object) -> str:
    if isinstance(value, datetime):
        resolved_date = value.date()
        return resolved_date.isoformat() if resolved_date >= MIN_VALID_EXECUTION_DATE else ""
    if isinstance(value, date):
        return value.isoformat() if value >= MIN_VALID_EXECUTION_DATE else ""
    text = str(value or "").strip()
    if not text or text.lower() == "null":
        return ""
    for parser in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            resolved_date = datetime.strptime(text, parser).date()
            return resolved_date.isoformat() if resolved_date >= MIN_VALID_EXECUTION_DATE else ""
        except ValueError:
            continue
    normalized = text.replace(",", ".")
    try:
        serial = float(normalized)
    except ValueError:
        return ""
    if serial <= 1:
        return ""
    base_date = date(1899, 12, 30)
    resolved_date = base_date + timedelta(days=int(serial))
    return resolved_date.isoformat() if resolved_date >= MIN_VALID_EXECUTION_DATE else ""


def point_in_ring(longitude: float, latitude: float, ring: list[list[float]]) -> bool:
    inside = False
    total = len(ring)
    if total < 3:
        return False
    for index in range(total):
        x1, y1 = ring[index]
        x2, y2 = ring[(index + 1) % total]
        intersects = ((y1 > latitude) != (y2 > latitude)) and (
            longitude < ((x2 - x1) * (latitude - y1) / ((y2 - y1) or 1e-12) + x1)
        )
        if intersects:
            inside = not inside
    return inside


def point_in_polygon(longitude: float, latitude: float, polygon: list[list[list[float]]]) -> bool:
    if not polygon:
        return False
    if not point_in_ring(longitude, latitude, polygon[0]):
        return False
    for hole in polygon[1:]:
        if point_in_ring(longitude, latitude, hole):
            return False
    return True


def load_land_geometries() -> list[list[list[list[float]]]]:
    payload = json.loads(WORLD_GEOJSON_FILE.read_text(encoding="utf-8"))
    features = payload.get("features", []) if isinstance(payload, dict) else []
    polygons: list[list[list[list[float]]]] = []
    for feature in features:
        geometry = feature.get("geometry", {}) if isinstance(feature, dict) else {}
        geometry_type = geometry.get("type")
        coordinates = geometry.get("coordinates", [])
        if geometry_type == "Polygon":
            polygons.append(coordinates)
        elif geometry_type == "MultiPolygon":
            polygons.extend(coordinates)
    return polygons


def point_is_on_land(longitude: float, latitude: float, land_geometries: list[list[list[list[float]]]]) -> bool:
    return any(point_in_polygon(longitude, latitude, polygon) for polygon in land_geometries)


def create_phase02_workbook(phase01_workbook: Path, definition_file: Path, output_file: Path, log_file: Path) -> dict[str, object]:
    phase01 = load_phase01_module()
    definition = phase01.read_definition(definition_file)
    initial_settings = definition.get("initial_settings", {})
    required_columns = []
    for key in REQUIRED_INITIAL_SETTING_KEYS:
        value = str(initial_settings.get(key, "")).strip()
        if value and value not in required_columns:
            required_columns.append(value)
    if not required_columns:
        raise ValueError("The selection definition does not contain the required Initial Settings columns.")

    target_column = str(initial_settings.get("target_column", "")).strip()
    longitude_column = str(initial_settings.get("longitude_column", "")).strip()
    latitude_column = str(initial_settings.get("latitude_column", "")).strip()
    planting_date_column = str(initial_settings.get("planting_date_column", "")).strip()
    harvesting_date_column = str(initial_settings.get("harvesting_date_column", "")).strip()
    if not longitude_column or not latitude_column:
        raise ValueError("The selection definition must include latitude and longitude columns.")
    if not planting_date_column or not harvesting_date_column:
        raise ValueError("The selection definition must include planting and harvesting date columns.")

    headers, records = phase01.read_sheet_headers_and_rows(phase01_workbook)
    if not headers:
        raise ValueError("The phase01 workbook is empty.")

    missing_columns = [column for column in required_columns if column not in headers]
    if missing_columns:
        raise ValueError(
            f"The phase01 workbook is missing required Initial Settings columns: {', '.join(missing_columns)}"
        )

    land_geometries = load_land_geometries()
    removed_rows = []
    kept_records = []
    removed_by_column = {column: 0 for column in required_columns}
    removed_by_reason = {
        "missing_required_initial_settings": 0,
        "invalid_target_value": 0,
        "invalid_initial_setting_dates": 0,
        "water_or_lake_point": 0,
    }
    for row_index, record in enumerate(records, start=2):
        missing_in_row = []
        for column in required_columns:
            value = str(record.get(column, "")).strip()
            if not value or value.lower() == "null":
                missing_in_row.append(column)
        if missing_in_row:
            for column in missing_in_row:
                removed_by_column[column] += 1
            removed_by_reason["missing_required_initial_settings"] += 1
            removed_rows.append({
                "row_number": row_index,
                "reason": "missing_required_initial_settings",
                "missing_columns": missing_in_row,
            })
            continue

        longitude_value = parse_coordinate(record.get(longitude_column, ""))
        latitude_value = parse_coordinate(record.get(latitude_column, ""))
        if longitude_value is None or latitude_value is None:
            removed_by_reason["missing_required_initial_settings"] += 1
            removed_rows.append({
                "row_number": row_index,
                "reason": "missing_required_initial_settings",
                "missing_columns": [column for column, value in ((longitude_column, longitude_value), (latitude_column, latitude_value)) if value is None],
            })
            continue

        target_value = parse_coordinate(record.get(target_column, "")) if target_column else None
        if target_value is None or target_value <= 0:
            removed_by_reason["invalid_target_value"] += 1
            removed_rows.append({
                "row_number": row_index,
                "reason": "invalid_target_value",
                "target_column": target_column,
                "target_value": str(record.get(target_column, "")).strip(),
            })
            continue

        planting_date_value = normalize_excel_date_text(record.get(planting_date_column, ""))
        harvesting_date_value = normalize_excel_date_text(record.get(harvesting_date_column, ""))
        if not planting_date_value or not harvesting_date_value or harvesting_date_value < planting_date_value:
            removed_by_reason["invalid_initial_setting_dates"] += 1
            removed_rows.append({
                "row_number": row_index,
                "reason": "invalid_initial_setting_dates",
                "planting_date": str(record.get(planting_date_column, "")).strip(),
                "harvesting_date": str(record.get(harvesting_date_column, "")).strip(),
                "normalized_planting_date": planting_date_value,
                "normalized_harvesting_date": harvesting_date_value,
            })
            continue

        if not point_is_on_land(longitude_value, latitude_value, land_geometries):
            removed_by_reason["water_or_lake_point"] += 1
            removed_rows.append({
                "row_number": row_index,
                "reason": "water_or_lake_point",
                "longitude": longitude_value,
                "latitude": latitude_value,
            })
            continue
        updated_record = dict(record)
        updated_record[planting_date_column] = planting_date_value
        updated_record[harvesting_date_column] = harvesting_date_value
        kept_records.append(updated_record)

    phase01.write_xlsx(output_file, headers, kept_records)
    log_payload = {
        "phase": "phase02",
        "source_workbook": str(phase01_workbook),
        "output_workbook": str(output_file),
        "world_geojson_file": str(WORLD_GEOJSON_FILE),
        "required_initial_setting_columns": required_columns,
        "coordinate_validation": {
            "longitude_column": longitude_column,
            "latitude_column": latitude_column,
            "require_land_point": True,
        },
        "input_row_count": len(records),
        "removed_row_count": len(removed_rows),
        "kept_row_count": len(kept_records),
        "removed_by_column": removed_by_column,
        "removed_by_reason": removed_by_reason,
        "removed_rows": removed_rows,
    }
    log_file.parent.mkdir(parents=True, exist_ok=True)
    log_file.write_text(json.dumps(log_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return log_payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create ce_pipeline phase02 workbook by filtering empty Initial Settings values and invalid coordinates.")
    parser.add_argument("--phase01-workbook", required=True, help="Path to the generated phase01 workbook.")
    parser.add_argument("--definition-file", required=True, help="Path to the selection summary JSON definition.")
    parser.add_argument("--output-file", required=True, help="Path to the generated phase02 workbook.")
    parser.add_argument("--log-file", required=True, help="Path to the generated phase02 log JSON file.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    result = create_phase02_workbook(
        phase01_workbook=Path(args.phase01_workbook).expanduser().resolve(),
        definition_file=Path(args.definition_file).expanduser().resolve(),
        output_file=Path(args.output_file).expanduser().resolve(),
        log_file=Path(args.log_file).expanduser().resolve(),
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
