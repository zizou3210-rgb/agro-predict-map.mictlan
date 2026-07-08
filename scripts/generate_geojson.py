#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile


APP_DIR = Path(__file__).resolve().parents[1]
SOURCE_XLSX = APP_DIR / "source" / "phase1.xlsx"
OUTPUT_GEOJSON = APP_DIR / "data" / "phase1_points.geojson"

XML_NS = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
COLUMN_LAT = "_GPS coordinates_latitude"
COLUMN_LON = "_GPS coordinates_longitude"


def column_letters_to_index(cell_reference: str) -> int:
    letters = "".join(character for character in cell_reference if character.isalpha())
    index = 0
    for character in letters:
        index = (index * 26) + (ord(character.upper()) - ord("A") + 1)
    return index - 1


def normalize_value(text: str) -> str | int | float:
    stripped = text.strip()
    if stripped == "":
        return ""
    if re.fullmatch(r"-?\d+", stripped):
        return int(stripped)
    if re.fullmatch(r"-?\d+\.\d+", stripped):
        return float(stripped)
    return stripped


def cell_value(cell: ET.Element) -> str | int | float:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(".//main:t", XML_NS))

    value_node = cell.find("main:v", XML_NS)
    if value_node is None or value_node.text is None:
        return ""
    return normalize_value(value_node.text)


def parse_sheet_rows(xlsx_path: Path) -> tuple[list[str], list[list[str | int | float]]]:
    with ZipFile(xlsx_path) as archive:
        root = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))

    sheet_data = root.find("main:sheetData", XML_NS)
    if sheet_data is None:
        raise ValueError("No se encontro sheetData en el archivo XLSX")

    parsed_rows: list[list[str | int | float]] = []
    max_width = 0

    for row in sheet_data.findall("main:row", XML_NS):
        values_by_index: dict[int, str | int | float] = {}
        for cell in row.findall("main:c", XML_NS):
            ref = cell.attrib.get("r", "")
            if not ref:
                continue
            values_by_index[column_letters_to_index(ref)] = cell_value(cell)

        if not values_by_index:
            continue

        row_width = max(values_by_index) + 1
        max_width = max(max_width, row_width)
        parsed_row = [values_by_index.get(index, "") for index in range(row_width)]
        parsed_rows.append(parsed_row)

    if not parsed_rows:
        raise ValueError("La hoja no contiene filas")

    normalized_rows: list[list[str | int | float]] = []
    for row in parsed_rows:
        if len(row) < max_width:
            row = row + [""] * (max_width - len(row))
        normalized_rows.append(row)

    headers = [str(value) for value in normalized_rows[0]]
    return headers, normalized_rows[1:]


def as_float(value: object) -> float | None:
    if value in ("", None):
        return None
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(numeric_value):
        return None
    return numeric_value


def build_feature_collection() -> dict[str, object]:
    headers, rows = parse_sheet_rows(SOURCE_XLSX)
    header_index = {header: index for index, header in enumerate(headers)}

    missing = [name for name in (COLUMN_LAT, COLUMN_LON) if name not in header_index]
    if missing:
        raise ValueError(f"Faltan columnas requeridas: {', '.join(missing)}")

    lat_index = header_index[COLUMN_LAT]
    lon_index = header_index[COLUMN_LON]

    features: list[dict[str, object]] = []
    skipped_rows = 0

    for row_number, row in enumerate(rows, start=2):
        latitude = as_float(row[lat_index] if lat_index < len(row) else None)
        longitude = as_float(row[lon_index] if lon_index < len(row) else None)
        if latitude is None or longitude is None:
            skipped_rows += 1
            continue

        properties = {"row_number": row_number}
        for index, header_name in enumerate(headers):
            if header_name in ("", COLUMN_LAT, COLUMN_LON):
                continue
            if index >= len(row):
                continue
            value = row[index]
            if value in ("", None):
                continue
            properties[header_name] = value

        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [longitude, latitude]},
                "properties": properties,
            }
        )

    return {
        "type": "FeatureCollection",
        "name": "phase1_gps_points",
        "metadata": {
            "source_file": str(SOURCE_XLSX.relative_to(APP_DIR)),
            "latitude_column": COLUMN_LAT,
            "longitude_column": COLUMN_LON,
            "attribute_count": len(headers) - 2,
            "total_features": len(features),
            "skipped_rows_without_coordinates": skipped_rows,
        },
        "features": features,
    }


def main() -> None:
    feature_collection = build_feature_collection()
    OUTPUT_GEOJSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_GEOJSON.write_text(
        json.dumps(feature_collection, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    print(
        f"GeoJSON generado en {OUTPUT_GEOJSON} con "
        f"{feature_collection['metadata']['total_features']} puntos"
    )


if __name__ == "__main__":
    main()
