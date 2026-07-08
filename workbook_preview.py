from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re
from zipfile import ZipFile
import json
import xml.etree.ElementTree as ET


XML_NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_NS = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}
WORKBOOK_REL_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
LATITUDE_HEADER = "_GPS coordinates_latitude"
LONGITUDE_HEADER = "_GPS coordinates_longitude"
RANK_FALLBACK_HEADERS = ("Rank", "rank1", "rank2", "rank3", "rank4")


def _column_index_from_reference(reference: str) -> int:
    letters = []
    for character in reference:
        if character.isalpha():
            letters.append(character.upper())
        else:
            break
    if not letters:
        raise ValueError(f"Invalid cell reference: {reference}")

    index = 0
    for letter in letters:
        index = (index * 26) + (ord(letter) - ord("A") + 1)
    return index - 1


def _read_shared_strings(workbook_archive: ZipFile) -> list[str]:
    try:
        with workbook_archive.open("xl/sharedStrings.xml") as handle:
            tree = ET.parse(handle)
    except KeyError:
        return []

    values: list[str] = []
    for item in tree.getroot().findall("x:si", XML_NS):
        values.append("".join(node.text or "" for node in item.findall(".//x:t", XML_NS)))
    return values


def _resolve_first_sheet_path(workbook_archive: ZipFile) -> str:
    with workbook_archive.open("xl/workbook.xml") as handle:
        workbook_tree = ET.parse(handle)
    sheet = workbook_tree.getroot().find("x:sheets/x:sheet", XML_NS)
    if sheet is None:
        raise ValueError("The workbook does not contain any worksheets.")

    relationship_id = sheet.get(WORKBOOK_REL_ID, "").strip()
    if not relationship_id:
        raise ValueError("The workbook worksheet relationship could not be resolved.")

    with workbook_archive.open("xl/_rels/workbook.xml.rels") as handle:
        rel_tree = ET.parse(handle)
    for relation in rel_tree.getroot().findall("r:Relationship", REL_NS):
        if relation.get("Id", "").strip() != relationship_id:
            continue
        target = relation.get("Target", "").strip().lstrip("/")
        if not target:
            break
        if target.startswith("xl/"):
            return target
        return f"xl/{target}"
    raise ValueError("The first worksheet path could not be resolved from the workbook.")


def _extract_cell_value(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = (cell.get("t") or "").strip()
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(".//x:t", XML_NS)).strip()

    value_node = cell.find("x:v", XML_NS)
    raw_value = "" if value_node is None or value_node.text is None else value_node.text
    if cell_type == "s":
        if not raw_value.strip():
            return ""
        shared_index = int(raw_value)
        if 0 <= shared_index < len(shared_strings):
            return shared_strings[shared_index].strip()
        return ""
    return raw_value.strip()


def _read_sheet_headers_and_rows(workbook_path: Path) -> tuple[list[str], list[dict[str, str]]]:
    workbook_path = Path(workbook_path)
    with ZipFile(workbook_path) as workbook_archive:
        shared_strings = _read_shared_strings(workbook_archive)
        sheet_path = _resolve_first_sheet_path(workbook_archive)
        with workbook_archive.open(sheet_path) as handle:
            sheet_tree = ET.parse(handle)

    rows = sheet_tree.getroot().findall("x:sheetData/x:row", XML_NS)
    if not rows:
        return [], []

    header_map: dict[int, str] = {}
    for cell in rows[0].findall("x:c", XML_NS):
        reference = cell.get("r", "").strip()
        if not reference:
            continue
        header_map[_column_index_from_reference(reference)] = _extract_cell_value(cell, shared_strings)

    headers = [header for _, header in sorted(header_map.items())]
    records: list[dict[str, str]] = []
    for row in rows[1:]:
        row_cells = {}
        for cell in row.findall("x:c", XML_NS):
            reference = cell.get("r", "").strip()
            if not reference:
                continue
            row_cells[_column_index_from_reference(reference)] = _extract_cell_value(
                cell, shared_strings
            )
        records.append({header: row_cells.get(index, "").strip() for index, header in sorted(header_map.items())})
    return headers, records


def _looks_like_numeric(value: str) -> bool:
    normalized = str(value or "").strip().replace(",", ".")
    if not normalized:
        return False
    try:
        float(normalized)
    except ValueError:
        return False
    return True


def _looks_like_decimal_numeric(value: str) -> bool:
    normalized = str(value or "").strip()
    if not normalized:
        return False
    if not _looks_like_numeric(normalized):
        return False
    return bool(re.search(r"[\.,]\d+$", normalized))


_DATE_VALUE_PATTERNS = (
    re.compile(r"^\d{4}-\d{2}-\d{2}$"),
    re.compile(r"^\d{4}/\d{2}/\d{2}$"),
    re.compile(r"^\d{2}/\d{2}/\d{4}$"),
    re.compile(r"^\d{2}-\d{2}-\d{4}$"),
)


def _looks_like_date(value: str) -> bool:
    normalized = str(value or "").strip()
    if not normalized:
        return False
    return any(pattern.match(normalized) for pattern in _DATE_VALUE_PATTERNS)


_QUANTITATIVE_HEADER_HINTS = (
    "yield",
    "number",
    "count",
    "percentage",
    "percent",
    "total",
    "avg",
    "average",
    "height",
    "depth",
    "area",
    "stand",
    "moisture",
    "week",
    "mm",
    "cm",
    "age",
    "precision",
    "altitude",
    "temperature",
    "t/ha",
)

_CATEGORICAL_HEADER_HINTS = (
    "country",
    "location",
    "locality",
    "region",
    "state",
    "county",
    "village",
    "texture",
    "soil",
    "class",
    "type",
    "group",
    "status",
    "season",
    "management",
    "rank",
    "blight",
    "susceptible",
    "resistant",
    "severity",
    "score",
)


def _recommend_column_classification(header: str, values: list[str]) -> str:
    non_empty_values = [str(value or "").strip() for value in values if str(value or "").strip()]
    if not non_empty_values:
        return "no_defined"

    normalized_header = str(header or "").strip().lower()
    unique_values = {value.casefold() for value in non_empty_values}
    numeric_count = sum(1 for value in non_empty_values if _looks_like_numeric(value))
    decimal_count = sum(1 for value in non_empty_values if _looks_like_decimal_numeric(value))
    date_count = sum(1 for value in non_empty_values if _looks_like_date(value))
    unique_ratio = len(unique_values) / max(len(non_empty_values), 1)
    numeric_ratio = numeric_count / max(len(non_empty_values), 1)
    date_ratio = date_count / max(len(non_empty_values), 1)

    if decimal_count > 0:
        return "quantitative"
    if date_ratio >= 0.85:
        return "no_defined"
    if len(unique_values) <= 1:
        return "no_defined"
    if len(unique_values) <= 12:
        return "categorical"
    if any(token in normalized_header for token in _CATEGORICAL_HEADER_HINTS):
        return "categorical"
    if numeric_ratio >= 0.85 and len(unique_values) > 12:
        return "quantitative"
    if any(token in normalized_header for token in _QUANTITATIVE_HEADER_HINTS) and numeric_ratio >= 0.45 and len(unique_values) > 12:
        return "quantitative"
    if len(unique_values) <= 24 and unique_ratio <= 0.6:
        return "categorical"
    if unique_ratio >= 0.85:
        return "no_defined"
    return "categorical"



def _build_column_profiles(headers: list[str], records: list[dict[str, str]]) -> dict[str, dict[str, object]]:
    profiles: dict[str, dict[str, object]] = {}
    for header in headers:
        values = [str(record.get(header, "") or "").strip() for record in records]
        non_empty_values = [value for value in values if value]
        unique_values = []
        seen: set[str] = set()
        for value in non_empty_values:
            key = value.casefold()
            if key in seen:
                continue
            seen.add(key)
            unique_values.append(value)
        numeric_count = sum(1 for value in non_empty_values if _looks_like_numeric(value))
        decimal_count = sum(1 for value in non_empty_values if _looks_like_decimal_numeric(value))
        date_count = sum(1 for value in non_empty_values if _looks_like_date(value))
        recommendation = _recommend_column_classification(header, non_empty_values)
        profiles[header] = {
            "non_empty_count": len(non_empty_values),
            "empty_count": max(len(values) - len(non_empty_values), 0),
            "unique_count": len(unique_values),
            "sample_values": unique_values[:5],
            "numeric_ratio": round(numeric_count / max(len(non_empty_values), 1), 4) if non_empty_values else 0.0,
            "decimal_count": decimal_count,
            "date_ratio": round(date_count / max(len(non_empty_values), 1), 4) if non_empty_values else 0.0,
            "recommended_classification": recommendation,
        }
    return profiles


GERMPLASM_PROFILE_EXCLUDED_HEADERS = {
    "idPK",
    "GPS coordinates",
    "_GPS coordinates_latitude",
    "_GPS coordinates_longitude",
    "_GPS coordinates_altitude",
    "_GPS coordinates_precision",
    "Date of planting",
    "Date_of_harvesting",
}

ID_FIELD_EXCLUDED_PREFIX_PATTERNS = (
    re.compile(r"^DG\d+", re.IGNORECASE),
    re.compile(r"^D01\d+", re.IGNORECASE),
)
PREDICTION_INTERNAL_ROW_ID_HEADER = "Prediction Internal Row Id"
PREDICTION_GROUP_KEY_HEADER = "Prediction Group Key"
PREDICTION_GROUP_LABEL_HEADER = "Prediction Group Label"
PREDICTION_GROUP_REP_HEADER = "Prediction Group Rep"
CLEAR_SELECTION_ID_SENTINEL = "__clear_selection__"


def _collect_distinct_display_values(records: list[dict[str, str]], header: str) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for record in records:
        value = str(record.get(header, "") or "").strip()
        if not value:
            continue
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        values.append(value)
    return values


def _is_excluded_id_field(header: str) -> bool:
    normalized = str(header or "").strip()
    if not normalized:
        return True
    return any(pattern.match(normalized) for pattern in ID_FIELD_EXCLUDED_PREFIX_PATTERNS)


def _resolve_existing_header(headers: list[str], expected_header: str) -> str:
    normalized_expected = re.sub(
        r"\s+",
        " ",
        str(expected_header or "").replace("\u00a0", " "),
    ).strip()
    if not normalized_expected:
        return ""
    for header in headers:
        normalized_header = re.sub(
            r"\s+",
            " ",
            str(header or "").replace("\u00a0", " "),
        ).strip()
        if normalized_header.casefold() == normalized_expected.casefold():
            return str(header or "").strip()
    return ""


def _is_missing_selected_id_value(value: object) -> bool:
    normalized = str(value or "").strip()
    return normalized.casefold() in {"", "null", "none", "nan"}


def _apply_selected_id_fallbacks(
    records: list[dict[str, str]],
    selected_id_header: str,
) -> list[dict[str, str]]:
    normalized_header = str(selected_id_header or "").strip()
    if not normalized_header:
        return records

    grouped_records: dict[str, list[dict[str, str]]] = {}
    for record in records:
        name = str(record.get("Name", "")).strip()
        grouped_records.setdefault(name, []).append(dict(record))

    output_records: list[dict[str, str]] = []
    for _, name_records in grouped_records.items():
        if len(name_records) <= 1:
            output_records.extend(name_records)
            continue

        used_values: set[str] = set()
        for record in name_records:
            raw_value = str(record.get(normalized_header, "") or "").strip()
            if not _is_missing_selected_id_value(raw_value):
                used_values.add(raw_value)

        next_fallback = 1
        for record in name_records:
            raw_value = str(record.get(normalized_header, "") or "").strip()
            if _is_missing_selected_id_value(raw_value):
                while str(next_fallback) in used_values:
                    next_fallback += 1
                raw_value = str(next_fallback)
                next_fallback += 1
                record[normalized_header] = raw_value
                used_values.add(raw_value)
        output_records.extend(name_records)
    return output_records


def _build_prediction_internal_row_id(row_number: int) -> str:
    return f"source-row-{int(row_number)}"


def _annotate_prediction_internal_row_ids(records: list[dict[str, str]]) -> list[dict[str, str]]:
    annotated: list[dict[str, str]] = []
    for row_number, record in enumerate(records, start=2):
        updated = dict(record)
        updated[PREDICTION_INTERNAL_ROW_ID_HEADER] = _build_prediction_internal_row_id(row_number)
        annotated.append(updated)
    return annotated


def _build_prediction_group_label(name: str, selected_id_value: str) -> str:
    normalized_name = str(name or "").strip()
    normalized_id_value = str(selected_id_value or "").strip()
    if normalized_name and normalized_id_value:
        return f"{normalized_name} - {normalized_id_value}"
    return normalized_name or normalized_id_value


def _is_clear_selection_id_header(value: object) -> bool:
    return str(value or "").strip() == CLEAR_SELECTION_ID_SENTINEL


def _build_prediction_group_metadata(
    grouped_records: list[dict[str, str]],
    *,
    selected_id_header: str,
) -> dict[str, object]:
    sample_record = grouped_records[0] if grouped_records else {}
    name = str(sample_record.get("Name", "") or "").strip()
    selected_id_value = str(sample_record.get(selected_id_header, "") or "").strip() if selected_id_header else ""
    display_label = _build_prediction_group_label(name, selected_id_value)
    candidate_headers = [
        header
        for header in grouped_records[0].keys()
        if header
        and header not in {
            "Name",
            selected_id_header,
            PREDICTION_INTERNAL_ROW_ID_HEADER,
            PREDICTION_GROUP_KEY_HEADER,
            PREDICTION_GROUP_LABEL_HEADER,
            PREDICTION_GROUP_REP_HEADER,
        }
        and header not in GERMPLASM_PROFILE_EXCLUDED_HEADERS
        and not re.match(r"^DG\d+$", header or "")
    ] if grouped_records else []

    varying_columns: list[dict[str, object]] = []
    profile_groups: dict[str, int] = {}
    profile_key_headers: list[str] = []
    for header in candidate_headers:
        distinct_values = _collect_distinct_display_values(grouped_records, header)
        if len(distinct_values) <= 1:
            continue
        varying_columns.append(
            {
                "header": header,
                "values": distinct_values[:8],
                "unique_count": len(distinct_values),
            }
        )
        profile_key_headers.append(header)

    if selected_id_header and profile_key_headers:
        for record in grouped_records:
            profile_key = " || ".join(
                f"{header}={str(record.get(header, '') or '').strip() or 'Blank'}"
                for header in profile_key_headers
            )
            profile_groups[profile_key] = profile_groups.get(profile_key, 0) + 1

    return {
        "name": name,
        "id_value": selected_id_value,
        "display_label": display_label,
        "row_count": len(grouped_records),
        "rep_count": len(grouped_records),
        "multi_record": len(grouped_records) > 1,
        "profile_count": max(len(profile_groups), 1) if selected_id_header else 1,
        "multi_profile_mode": len(profile_groups) > 1 if selected_id_header else False,
        "varying_columns": varying_columns,
        "internal_row_ids": [
            str(record.get(PREDICTION_INTERNAL_ROW_ID_HEADER, "") or "").strip()
            for record in grouped_records
            if str(record.get(PREDICTION_INTERNAL_ROW_ID_HEADER, "") or "").strip()
        ],
    }


def _build_selected_id_values_for_name(
    name_records: list[dict[str, str]],
    selected_id_header: str,
) -> list[str]:
    normalized_header = str(selected_id_header or "").strip()
    if not normalized_header:
        return []
    row_count = len(name_records)
    if row_count <= 1:
        raw_value = str(name_records[0].get(normalized_header, "") or "").strip() if row_count else ""
        return [raw_value] if raw_value and not _is_missing_selected_id_value(raw_value) else []

    assigned_values: list[str] = []
    used_values: set[str] = set()
    next_fallback = 1
    for record in name_records:
        raw_value = str(record.get(normalized_header, "") or "").strip()
        if _is_missing_selected_id_value(raw_value):
            while str(next_fallback) in used_values:
                next_fallback += 1
            raw_value = str(next_fallback)
            next_fallback += 1
        assigned_values.append(raw_value)
        used_values.add(raw_value)
    return _collect_distinct_display_values(
        [{normalized_header: value} for value in assigned_values],
        normalized_header,
    )


def describe_distinct_germplasm_names_from_xlsx(
    workbook_path: Path,
    *,
    selected_id_header: str = "",
    require_farm_column: bool = False,
) -> dict[str, object]:
    headers, records = _read_sheet_headers_and_rows(workbook_path)
    if "Name" not in headers:
        raise ValueError("The uploaded workbook does not contain the required Name column.")
    annotated_records = _annotate_prediction_internal_row_ids(records)
    clear_selected_id = _is_clear_selection_id_header(selected_id_header)
    normalized_selected_id_header = (
        ""
        if clear_selected_id
        else _resolve_existing_header(headers, str(selected_id_header or "").strip())
    )
    resolved_farm_header = _resolve_existing_header(headers, "Farm")
    if require_farm_column and not resolved_farm_header:
        raise ValueError("The uploaded workbook must contain the required Farm column.")
    if require_farm_column and not clear_selected_id:
        normalized_selected_id_header = resolved_farm_header
    has_selected_id_header = normalized_selected_id_header in headers

    if has_selected_id_header:
        annotated_records = [
            {
                **record,
                normalized_selected_id_header: str(record.get(normalized_selected_id_header, "") or "").strip(),
            }
            for record in _apply_selected_id_fallbacks(annotated_records, normalized_selected_id_header)
        ]

    id_field_candidates = [
        header
        for header in headers
        if header
        and header != "Name"
        and not _is_excluded_id_field(header)
    ]

    grouped_by_label: dict[str, list[dict[str, str]]] = {}
    for record in annotated_records:
        name = str(record.get("Name", "") or "").strip()
        if not name:
            continue
        selected_id_value = (
            str(record.get(normalized_selected_id_header, "") or "").strip()
            if has_selected_id_header
            else ""
        )
        display_label = _build_prediction_group_label(name, selected_id_value)
        grouped_by_label.setdefault(display_label, []).append(record)

    ordered_labels = sorted(grouped_by_label.keys())
    profiles_by_label: dict[str, dict[str, object]] = {}
    group_payload: list[dict[str, object]] = []
    id_values_by_label: dict[str, list[str]] = {}
    for label in ordered_labels:
        grouped_records = grouped_by_label.get(label, [])
        metadata = _build_prediction_group_metadata(
            grouped_records,
            selected_id_header=normalized_selected_id_header,
        )
        profiles_by_label[label] = metadata
        group_payload.append(
            {
                "key": label,
                **metadata,
            }
        )
        if has_selected_id_header:
            id_values_by_label[label] = [str(metadata.get("id_value", "") or "").strip()] if str(metadata.get("id_value", "") or "").strip() else []

    payload: dict[str, object] = {
        "headers": headers,
        "id_field_candidates": id_field_candidates,
        "germplasm_names": ordered_labels,
        "germplasm_profiles_by_name": profiles_by_label,
        "germplasm_groups": group_payload,
        "count": len(ordered_labels),
        "default_selected_id_header": resolved_farm_header if require_farm_column and resolved_farm_header else "",
        "clear_selection_available": bool(resolved_farm_header) if require_farm_column else True,
    }
    if has_selected_id_header:
        payload["selected_id_header"] = normalized_selected_id_header
        payload["germplasm_id_values_by_name"] = id_values_by_label
    return payload


def list_distinct_germplasm_names_from_xlsx(workbook_path: Path) -> list[str]:
    description = describe_distinct_germplasm_names_from_xlsx(workbook_path)
    names = description.get("germplasm_names", [])
    return list(names) if isinstance(names, list) else []


def describe_workbook_columns(workbook_path: Path) -> dict[str, object]:
    headers, records = _read_sheet_headers_and_rows(workbook_path)
    return {
        "headers": headers,
        "row_count": len(records),
        "attribute_count": len(headers),
        "column_profiles": _build_column_profiles(headers, records),
    }


def validate_required_workbook_headers(
    workbook_path: Path,
    required_headers: list[str] | tuple[str, ...],
) -> dict[str, str]:
    headers, _ = _read_sheet_headers_and_rows(workbook_path)
    resolved_headers: dict[str, str] = {}
    missing_headers: list[str] = []
    for expected_header in required_headers:
        resolved_header = _resolve_existing_header(headers, expected_header)
        if not resolved_header:
            missing_headers.append(str(expected_header))
            continue
        resolved_headers[str(expected_header)] = resolved_header
    if missing_headers:
        if len(missing_headers) == 1:
            raise ValueError(
                f"The uploaded workbook must contain the required {missing_headers[0]} column."
            )
        raise ValueError(
            "The uploaded workbook must contain the required columns: "
            + ", ".join(missing_headers)
            + "."
        )
    return resolved_headers


def _parse_coordinate(value: str) -> float | None:
    raw_value = str(value or "").strip()
    if not raw_value:
        return None
    normalized = raw_value.replace(",", ".")
    try:
        return float(normalized)
    except ValueError:
        return None


def _point_in_ring(longitude: float, latitude: float, ring: list[list[float]]) -> bool:
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


def _point_in_polygon(longitude: float, latitude: float, polygon: list[list[list[float]]]) -> bool:
    if not polygon:
        return False
    if not _point_in_ring(longitude, latitude, polygon[0]):
        return False
    for hole in polygon[1:]:
        if _point_in_ring(longitude, latitude, hole):
            return False
    return True


@lru_cache(maxsize=1)
def _load_world_country_polygons() -> list[tuple[str, list[list[list[float]]]]]:
    world_geojson_path = Path(__file__).resolve().parent / 'data' / 'world.geojson'
    payload = json.loads(world_geojson_path.read_text(encoding='utf-8'))
    features = payload.get('features', []) if isinstance(payload, dict) else []
    polygons: list[tuple[str, list[list[list[float]]]]] = []
    for feature in features:
        if not isinstance(feature, dict):
            continue
        properties = feature.get('properties', {})
        geometry = feature.get('geometry', {})
        country_name = str((properties or {}).get('name') or '').strip()
        geometry_type = geometry.get('type')
        coordinates = geometry.get('coordinates', [])
        if not country_name:
            continue
        if geometry_type == 'Polygon':
            polygons.append((country_name, coordinates))
        elif geometry_type == 'MultiPolygon':
            for polygon in coordinates:
                polygons.append((country_name, polygon))
    return polygons


def _derive_country_from_coordinates(longitude: float, latitude: float) -> str:
    for country_name, polygon in _load_world_country_polygons():
        if _point_in_polygon(longitude, latitude, polygon):
            return country_name
    return ''


def build_original_feature_collection_from_xlsx(
    workbook_path: Path,
    *,
    latitude_header: str = LATITUDE_HEADER,
    longitude_header: str = LONGITUDE_HEADER,
    target_header: str | None = None,
) -> dict[str, object]:
    headers, records = _read_sheet_headers_and_rows(workbook_path)
    normalized_latitude_header = str(latitude_header or "").strip()
    normalized_longitude_header = str(longitude_header or "").strip()
    normalized_target_header = str(target_header or "").strip()
    if (
        normalized_latitude_header not in headers
        or normalized_longitude_header not in headers
    ):
        raise ValueError(
            "The uploaded workbook does not contain the required latitude and longitude columns."
        )

    features: list[dict[str, object]] = []
    skipped_without_coordinates = 0
    for index, record in enumerate(records, start=1):
        latitude = _parse_coordinate(record.get(normalized_latitude_header, ""))
        longitude = _parse_coordinate(record.get(normalized_longitude_header, ""))
        if latitude is None or longitude is None:
            skipped_without_coordinates += 1
            continue
        properties = dict(record)
        if not properties.get("Rank", "").strip():
            for header in RANK_FALLBACK_HEADERS:
                candidate = properties.get(header, "").strip()
                if candidate:
                    properties["Rank"] = candidate
                    break
        if not str(properties.get("Country", "")).strip():
            derived_country = _derive_country_from_coordinates(longitude, latitude)
            if derived_country:
                properties["Country"] = derived_country
                properties["Derived Country"] = derived_country
        properties["row_number"] = index
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [longitude, latitude],
                },
                "properties": properties,
            }
        )

    return {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {
            "attribute_count": len(headers),
            "row_count": len(records),
            "feature_count": len(features),
            "skipped_without_coordinates": skipped_without_coordinates,
            "latitude_column": normalized_latitude_header,
            "longitude_column": normalized_longitude_header,
            "target_column": normalized_target_header,
            "source": "original_workbook",
        },
    }
