#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable, Sequence
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile
import xml.etree.ElementTree as ET


XML_NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_NS = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}
WORKBOOK_REL_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
INITIAL_SETTING_KEYS = (
    "target_column",
    "longitude_column",
    "latitude_column",
    "planting_date_column",
    "harvesting_date_column",
    "soil_texture_column",
    "soil_depth_column",
)
DIVISION_KEYS = (
    "germplams_identifiers",
    "DG",
    "categorical_data",
    "cuantitative_data",
)


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


def _column_letter(index: int) -> str:
    value = index + 1
    letters = []
    while value > 0:
        value, remainder = divmod(value - 1, 26)
        letters.append(chr(ord("A") + remainder))
    return "".join(reversed(letters))


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


def read_sheet_headers_and_rows(workbook_path: Path) -> tuple[list[str], list[dict[str, str]]]:
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

    ordered_headers = [header for _, header in sorted(header_map.items())]
    records: list[dict[str, str]] = []
    for row in rows[1:]:
        row_cells = {}
        for cell in row.findall("x:c", XML_NS):
            reference = cell.get("r", "").strip()
            if not reference:
                continue
            row_cells[_column_index_from_reference(reference)] = _extract_cell_value(cell, shared_strings)
        records.append({header: row_cells.get(index, "").strip() for index, header in sorted(header_map.items())})
    return ordered_headers, records


def build_column_order(definition: dict) -> list[str]:
    initial_settings = definition.get("initial_settings", {})
    divisions = definition.get("divisions", {})
    ordered_columns: list[str] = []
    seen: set[str] = set()

    def append_column(value: object) -> None:
        column = str(value or "").strip()
        if not column or column in seen:
            return
        seen.add(column)
        ordered_columns.append(column)

    for key in INITIAL_SETTING_KEYS:
        append_column(initial_settings.get(key))

    for key in DIVISION_KEYS:
        for value in divisions.get(key, []):
            append_column(value)

    return ordered_columns


def read_definition(definition_file: Path) -> dict:
    payload = json.loads(definition_file.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("The selection definition must be a JSON object.")
    return payload


def build_sheet_xml(headers: list[str], records: list[dict[str, str]]) -> str:
    rows_xml = []

    def build_row(row_index: int, values: list[str]) -> str:
        cells = []
        for column_index, value in enumerate(values):
            reference = f"{_column_letter(column_index)}{row_index}"
            escaped_value = escape(str(value or ""))
            cells.append(
                f'<c r="{reference}" t="inlineStr"><is><t xml:space="preserve">{escaped_value}</t></is></c>'
            )
        return f'<row r="{row_index}">{"".join(cells)}</row>'

    rows_xml.append(build_row(1, headers))
    for row_index, record in enumerate(records, start=2):
        rows_xml.append(build_row(row_index, [record.get(header, "") for header in headers]))

    dimension_ref = f"A1:{_column_letter(max(len(headers) - 1, 0))}{max(len(records) + 1, 1)}"
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<dimension ref="{dimension_ref}"/>'
        '<sheetViews><sheetView workbookViewId="0"/></sheetViews>'
        '<sheetFormatPr defaultRowHeight="15"/>'
        f'<sheetData>{"".join(rows_xml)}</sheetData>'
        '</worksheet>'
    )


def _build_row_xml(row_index: int, values: Sequence[object]) -> str:
    cells = []
    for column_index, value in enumerate(values):
        reference = f"{_column_letter(column_index)}{row_index}"
        escaped_value = escape(str(value or ""))
        cells.append(
            f'<c r="{reference}" t="inlineStr"><is><t xml:space="preserve">{escaped_value}</t></is></c>'
        )
    return f'<row r="{row_index}">{"".join(cells)}</row>'


def _write_xlsx_static_parts(archive: ZipFile) -> None:
    archive.writestr(
        '[Content_Types].xml',
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
        '</Types>'
    )
    archive.writestr(
        '_rels/.rels',
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
        '</Relationships>'
    )
    archive.writestr(
        'docProps/core.xml',
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:dcmitype="http://purl.org/dc/dcmitype/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        '<dc:title>phase1</dc:title><dc:creator>ce_pipeline</dc:creator>'
        '</cp:coreProperties>'
    )
    archive.writestr(
        'docProps/app.xml',
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
        'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
        '<Application>ce_pipeline</Application>'
        '</Properties>'
    )
    archive.writestr(
        'xl/workbook.xml',
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="phase1" sheetId="1" r:id="rId1"/></sheets>'
        '</workbook>'
    )
    archive.writestr(
        'xl/_rels/workbook.xml.rels',
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        '</Relationships>'
    )
    archive.writestr(
        'xl/styles.xml',
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>'
        '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>'
        '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>'
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        '</styleSheet>'
    )


def write_xlsx_rows(
    output_file: Path,
    headers: list[str],
    rows: Iterable[Sequence[object]],
    data_row_count: int,
) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    dimension_ref = f"A1:{_column_letter(max(len(headers) - 1, 0))}{max(data_row_count + 1, 1)}"
    with ZipFile(output_file, "w", compression=ZIP_DEFLATED) as archive:
        _write_xlsx_static_parts(archive)
        with archive.open("xl/worksheets/sheet1.xml", "w") as sheet_handle:
            sheet_handle.write(
                (
                    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                    '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                    f'<dimension ref="{dimension_ref}"/>'
                    '<sheetViews><sheetView workbookViewId="0"/></sheetViews>'
                    '<sheetFormatPr defaultRowHeight="15"/>'
                    '<sheetData>'
                ).encode("utf-8")
            )
            sheet_handle.write(_build_row_xml(1, headers).encode("utf-8"))
            for row_index, row in enumerate(rows, start=2):
                sheet_handle.write(_build_row_xml(row_index, tuple(row)).encode("utf-8"))
            sheet_handle.write(b"</sheetData></worksheet>")


def write_xlsx(output_file: Path, headers: list[str], records: list[dict[str, str]]) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    sheet_xml = build_sheet_xml(headers, records)
    with ZipFile(output_file, "w", compression=ZIP_DEFLATED) as archive:
        _write_xlsx_static_parts(archive)
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)


def create_phase1_workbook(source_workbook: Path, definition_file: Path, output_file: Path) -> dict[str, object]:
    definition = read_definition(definition_file)
    selected_columns = build_column_order(definition)
    if not selected_columns:
        raise ValueError("The selection definition does not contain any columns.")

    headers, records = read_sheet_headers_and_rows(source_workbook)
    if not headers:
        raise ValueError("The uploaded workbook is empty.")

    missing_columns = [column for column in selected_columns if column not in headers]
    if missing_columns:
        raise ValueError(
            f"The uploaded workbook is missing columns required by the definition: {', '.join(missing_columns)}"
        )

    selected_records = [
        {column: record.get(column, "") for column in selected_columns}
        for record in records
    ]
    write_xlsx(output_file, selected_columns, selected_records)
    return {
        "output_file": str(output_file),
        "row_count": len(selected_records),
        "column_count": len(selected_columns),
        "columns": selected_columns,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create ce_pipeline phase1 workbook from the uploaded workbook and selection definition."
    )
    parser.add_argument("--source-workbook", required=True, help="Path to the uploaded workbook.")
    parser.add_argument("--definition-file", required=True, help="Path to the selection summary JSON definition.")
    parser.add_argument("--output-file", required=True, help="Path to the generated phase1 workbook.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    result = create_phase1_workbook(
        source_workbook=Path(args.source_workbook).expanduser().resolve(),
        definition_file=Path(args.definition_file).expanduser().resolve(),
        output_file=Path(args.output_file).expanduser().resolve(),
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
