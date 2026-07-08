from __future__ import annotations

import json
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

import pandas as pd

from cimmyt_app.workbook_preview import _derive_country_from_coordinates


GEO_COLUMNS = [
    "Country",
    "GPS coordinates",
    "_GPS coordinates_latitude",
    "_GPS coordinates_longitude",
    "_GPS coordinates_altitude",
    "_GPS coordinates_precision",
]

GERMPLASM_COLUMNS = [
    "Trial series name",
    "Rep",
    "Farm",
    "Site Number",
    "Plot",
    "EntryCode",
    "Name",
    "Local check, Name of variety provided by farmer",
]

FORECAST_METADATA_COLUMNS = [
    "Date of planting",
    "Date of thinning",
    "Date_of_harvesting",
    "Soil type/texture",
    "Soil Depth (cm)-How deep do you expect maize roots to grow in this soil?",
    "Forecast locality",
    "Forecast locality geonameid",
    "Forecast locality population",
    "Forecast country",
    "Forecast country code",
    "Forecast grid cell id",
    "Forecast grid cell index",
    "Selected model id",
    "Original GPS coordinates",
    "Original _GPS coordinates_latitude",
    "Original _GPS coordinates_longitude",
]

DATE_HEADERS = {"Date of planting", "Date_of_harvesting"}


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def parse_numeric_value(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if pd.isna(value):
            return None
        return float(value)

    text = str(value).strip()
    if not text:
        return None

    text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def is_blank_value(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    text = str(value).strip()
    return text == "" or text.lower() == "null"


def excel_serial_to_datetime(value: float) -> datetime:
    return datetime(1899, 12, 30) + timedelta(days=value)


def normalize_excel_date_value(value: object) -> object:
    if isinstance(value, datetime):
        return value.strftime("%m/%Y")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if pd.isna(value):
            return ""
        if 20000 <= float(value) <= 60000:
            return excel_serial_to_datetime(float(value)).strftime("%m/%Y")
    return value


def normalize_phase2_dates(df: pd.DataFrame, date_headers: Iterable[str]) -> None:
    for header in date_headers:
        if header not in df.columns:
            continue
        df[header] = df[header].apply(normalize_excel_date_value)


def sanitize_value(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, float):
        if math.isnan(value):
            return None
        if value.is_integer():
            return int(value)
        return value
    if isinstance(value, (int, bool)):
        return value
    text = str(value).strip()
    if not text:
        return None
    return text


def dataframe_to_geojson(df: pd.DataFrame, output_file: Path) -> dict[str, object]:
    latitude_header = "_GPS coordinates_latitude"
    longitude_header = "_GPS coordinates_longitude"
    if latitude_header not in df.columns or longitude_header not in df.columns:
        raise KeyError(
            "The processed data does not contain the required geoinformation "
            "columns '_GPS coordinates_latitude' and '_GPS coordinates_longitude'."
        )

    features: list[dict[str, object]] = []
    for row_number, (_, row) in enumerate(df.iterrows(), start=2):
        latitude = parse_numeric_value(row.get(latitude_header))
        longitude = parse_numeric_value(row.get(longitude_header))
        if latitude is None or longitude is None:
            continue

        properties: dict[str, object] = {"row_number": row_number}
        for column in df.columns:
            if column in {latitude_header, longitude_header}:
                continue
            value = sanitize_value(row.get(column))
            if value is None:
                continue
            properties[column] = value

        country_value = str(properties.get("Country", "") or "").strip()
        if not country_value:
            derived_country = _derive_country_from_coordinates(longitude, latitude)
            if derived_country:
                properties["Country"] = derived_country
                properties["Derived Country"] = derived_country

        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [longitude, latitude]},
                "properties": properties,
            }
        )

    geojson = {
        "type": "FeatureCollection",
        "metadata": {
            "attribute_count": max(len(df.columns) - 2, 0),
            "total_features": len(features),
            "source_file_name": output_file.stem,
        },
        "features": features,
    }
    ensure_parent(output_file)
    output_file.write_text(json.dumps(geojson, ensure_ascii=False), encoding="utf-8")
    return geojson
