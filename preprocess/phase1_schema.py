#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from openpyxl import Workbook, load_workbook


BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent.parent

DEFAULT_REFERENCE_FILE = REPO_ROOT / "template" / "phase1.xlsx"
DEFAULT_OUTPUT_FILE = REPO_ROOT / "template" / "phase1_validation.xlsx"
DEFAULT_ARCHIVE_FILE = DEFAULT_REFERENCE_FILE
DEFAULT_GG_FILE = DEFAULT_REFERENCE_FILE
OUTPUT_SHEET_NAME = "phase1"

OUTPUT_HEADERS = [
    "idPK",
    "Local check, Name of variety provided by farmer",
    "Education/Training of the farmer",
    "Gender of the farmer (plot manager)",
    "Rank",
    "Age of the plot manager",
    "Country",
    "GPS coordinates",
    "_GPS coordinates_latitude",
    "_GPS coordinates_longitude",
    "_GPS coordinates_altitude",
    "_GPS coordinates_precision",
    "Date of planting",
    "Date_of_harvesting",
    "Farmers total land area (acres)",
    "Soil type/texture",
    "Soil Depth (cm)-How deep do you expect maize roots to grow in this soil?",
    "Cropping practices",
    "Plant stand ; plot 1",
    "is_fertilizer",
    "Weed control practices",
    "Number_of_times_fertilizer_was_applied",
    "is_Trial_management_by_action_herbicide",
    "Plant_height_Plot_1",
    "Ear_height_Plot_1",
    "Grey_Leaf_Spot_GLS_5_very_susceptible_header",
    "Turcicum_leaf_blight_5_very_susceptible_header",
    "Puccinia_sorghi_Com_5_very_susceptible_header",
    "Maize_Streak_Virus_S_5_very_susceptible_header",
    "Plant_Aspect_1_5_1_h_high_ear_placement_header",
    "Plant_harvest_stand_t_harvesting_Plot_1",
    "Percentage_Plant_harvest_stand_t_harvesting_Plot_1",
    "Number_of_plants_wit_root_lodging_Plot_1",
    "Percentage_Number_of_plants_wit_root_lodging_Plot_1",
    "Number_of_plants_wit_stem_lodging_Plot_1",
    "Percentage_Number_of_plants_wit_stem_lodging_Plot_1",
    "Poor_husk_cover_Plot_1",
    "Percentage_Poor_husk_cover_Plot_1",
    "Number_of_ears_harvested_Plot_1",
    "Percentage_Number_of_ears_harvested_Plot_1",
    "Count_number_of_rotten_ears_Plot_1",
    "Percentage_Count_number_of_rotten_ears_Plot_1",
    "Ear_aspect_1_5_1_n_undesirable_texture_header",
    "Grain_moisture_Plot_1",
    "is_Trial_management_by_action_Insecticide",
    "_8_1_BM_Who_in_your_h_e_on_farm_experiment",
    "_8_2_BM_Who_in_your_h_e_on_farm_experiment",
    "Plot Area",
    "Ear Position",
    "Root Lodging (%)",
    "Stem Logding (%)",
    "Bad Husk Cover (%)",
    "Ears/Plant (#)",
    "Rotten Ears (%)",
    "Grain Yield (T/Ha)",
    "planting_week_1_total_prectotcorr (mm)",
    "planting_week_2_total_prectotcorr (mm)",
    "planting_week_2_avg_t2m (C)",
    "intermediate_period_total_prectotcorr (mm)",
    "intermediate_period_avg_t2m (C)",
    "harvest_back_week_1_total_prectotcorr (mm)",
    "harvest_back_week_1_avg_t2m (C)",
    "harvest_back_week_2_total_prectotcorr (mm)",
    "harvest_back_week_2_avg_t2m (C)",
    "harvest_back_week_3_total_prectotcorr (mm)",
    "harvest_back_week_3_avg_t2m (C)",
    "harvest_back_week_4_total_prectotcorr (mm)",
    "harvest_back_week_4_avg_t2m (C)",
    "harvest_back_week_5_total_prectotcorr (mm)",
    "harvest_back_week_5_avg_t2m (C)",
    "harvest_back_week_6_total_prectotcorr (mm)",
    "harvest_back_week_6_avg_t2m (C)",
    "harvest_back_week_7_total_prectotcorr (mm)",
    "harvest_back_week_7_avg_t2m (C)",
    "harvest_back_week_8_total_prectotcorr (mm)",
    "harvest_back_week_8_avg_t2m (C)",
]


def build_row_dict(header_row: tuple[object, ...], row_values: tuple[object, ...]) -> dict[str, object]:
    result: dict[str, object] = {}
    for idx, header in enumerate(header_row):
        if header is None:
            continue
        header_name = str(header).strip()
        if not header_name:
            continue
        result[header_name] = row_values[idx] if idx < len(row_values) else None
    return result


def build_output_row(row_dict: dict[str, object]) -> list[object]:
    return [row_dict.get(header_name) for header_name in OUTPUT_HEADERS]


def append_source_rows(output_ws, source_file: Path) -> int:
    workbook = load_workbook(source_file, read_only=True, data_only=True)
    try:
        worksheet = workbook.worksheets[0]
        rows_iter = worksheet.iter_rows(values_only=True)
        header_row = next(rows_iter)
        appended_rows = 0
        for row_values in rows_iter:
            row_dict = build_row_dict(header_row, row_values)
            output_ws.append(build_output_row(row_dict))
            appended_rows += 1
        return appended_rows
    finally:
        workbook.close()


def load_rows(path: Path) -> list[tuple[object, ...]]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        worksheet = workbook[workbook.sheetnames[0]]
        return list(worksheet.iter_rows(values_only=True))
    finally:
        workbook.close()


def build_phase1_validation_workbook(
    archive_file: Path = DEFAULT_ARCHIVE_FILE,
    gg_file: Path = DEFAULT_GG_FILE,
    output_file: Path = DEFAULT_OUTPUT_FILE,
) -> dict[str, int]:
    if not archive_file.exists():
        raise FileNotFoundError(f"No existe el archivo fuente: {archive_file}")
    if not gg_file.exists():
        raise FileNotFoundError(f"No existe el archivo fuente: {gg_file}")

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_wb = Workbook(write_only=True)
    output_ws = output_wb.create_sheet(title=OUTPUT_SHEET_NAME)
    output_ws.append(OUTPUT_HEADERS)

    archive_rows = append_source_rows(output_ws, archive_file)
    gg_rows = append_source_rows(output_ws, gg_file)
    output_wb.save(output_file)

    return {
        "archive_rows": archive_rows,
        "gg_rows": gg_rows,
        "total_rows": archive_rows + gg_rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Construye el workbook de validacion phase1 dentro de app."
    )
    parser.add_argument(
        "--archive-file",
        default=str(DEFAULT_ARCHIVE_FILE),
        help="Ruta al phase15 historico del archive.",
    )
    parser.add_argument(
        "--gg-file",
        default=str(DEFAULT_GG_FILE),
        help="Ruta al phase11 historico de GG.",
    )
    parser.add_argument(
        "--output-file",
        default=str(DEFAULT_OUTPUT_FILE),
        help="Ruta del workbook de salida generado.",
    )
    parser.add_argument(
        "--compare-reference",
        action="store_true",
        help="Compara la salida generada con cimmyt_app/template/phase1.xlsx.",
    )
    args = parser.parse_args()

    stats = build_phase1_validation_workbook(
        archive_file=Path(args.archive_file),
        gg_file=Path(args.gg_file),
        output_file=Path(args.output_file),
    )
    print(f"Archivo creado: {args.output_file}")
    print(f"Filas archive: {stats['archive_rows']}")
    print(f"Filas gg: {stats['gg_rows']}")
    print(f"Total filas: {stats['total_rows']}")

    if args.compare_reference:
        if load_rows(Path(args.output_file)) == load_rows(DEFAULT_REFERENCE_FILE):
            print("Comparacion con referencia: OK")
        else:
            print("Comparacion con referencia: DIFFERENT")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
