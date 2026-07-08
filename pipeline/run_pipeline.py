from __future__ import annotations

if __package__ in {None, ""}:
    import sys
    from pathlib import Path

    APP_BOOT_DIR = Path(__file__).resolve().parents[1]
    PACKAGE_PARENT = APP_BOOT_DIR.parent
    if str(PACKAGE_PARENT) not in sys.path:
        sys.path.insert(0, str(PACKAGE_PARENT))

import argparse
import json
from pathlib import Path

from cimmyt_app.ce_pipeline.prediction.prediction import run_ce_saved_model_prediction, run_saved_model_prediction
from cimmyt_app.pipeline.progress import ProgressReporter
from cimmyt_app.pipeline.run_model_pipeline import run_model_pipeline
from cimmyt_app.preprocess.runner import run_preprocess_pipeline


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the full app pipeline from a test.xlsx workbook.")
    parser.add_argument("--input", type=Path, default=None, help="Input XLSX file uploaded from the app UI.")
    parser.add_argument("--run-dir", required=True, type=Path, help="Output run directory.")
    parser.add_argument("--progress-file", type=Path, default=None, help="Optional progress JSON file updated during execution.")
    parser.add_argument(
        "--selected-model-id",
        default="",
        help="Optional saved model id to reuse and skip rerunning FeatureHero.",
    )
    parser.add_argument(
        "--selected-germplasm-names-json",
        default="",
        help="Optional JSON array with the distinct Name values to keep from the uploaded workbook.",
    )
    parser.add_argument(
        "--selected-germplasm-row-ids-json",
        default="",
        help="Optional JSON array with the internal workbook row ids selected from Load Data to Predict.",
    )
    parser.add_argument(
        "--selected-germplasm-projection-mode",
        default="",
        help="Optional projection mode for selected germplasm values. Supported values: '', all_markers.",
    )
    parser.add_argument(
        "--selected-germplasm-selection-mode",
        default="all_matches",
        help="Optional selected germplasm row selection mode. Supported values: all_matches, first_match_only.",
    )
    parser.add_argument(
        "--projection-template-workbook",
        type=Path,
        default=None,
        help="Optional immutable workbook path used as the germplasm template source for all-markers projection modes.",
    )
    parser.add_argument(
        "--forecast-planting-date",
        default="",
        help="Optional YYYY-MM-DD planting date used to drive the 5-year NASA average forecast mode.",
    )
    parser.add_argument(
        "--forecast-harvesting-date",
        default="",
        help="Optional YYYY-MM-DD harvesting date used to drive the 5-year NASA average forecast mode.",
    )
    parser.add_argument(
        "--climate-scope",
        default="point",
        help="Climate retrieval mode. Supported values: point, country_localities, regional_country, regional_manual.",
    )
    parser.add_argument(
        "--regional-country",
        default="",
        help="Optional country name used when climate-scope=regional_country.",
    )
    parser.add_argument(
        "--regional-bounds-label",
        default="",
        help="Optional label used when climate-scope=regional_manual.",
    )
    parser.add_argument(
        "--regional-bounds-latitude-min",
        type=float,
        default=None,
        help="Manual regional latitude minimum used when climate-scope=regional_manual.",
    )
    parser.add_argument(
        "--regional-bounds-latitude-max",
        type=float,
        default=None,
        help="Manual regional latitude maximum used when climate-scope=regional_manual.",
    )
    parser.add_argument(
        "--regional-bounds-longitude-min",
        type=float,
        default=None,
        help="Manual regional longitude minimum used when climate-scope=regional_manual.",
    )
    parser.add_argument(
        "--regional-bounds-longitude-max",
        type=float,
        default=None,
        help="Manual regional longitude maximum used when climate-scope=regional_manual.",
    )
    parser.add_argument(
        "--nasa-grid-resolution-km",
        type=int,
        default=10,
        help="NASA POWER manual bounding-box grid resolution in kilometers.",
    )
    parser.add_argument(
        "--use-source-row-dates",
        default="1",
        help="Whether High-Potential Sites should build NASA windows from the workbook row dates (1) or the forecast dates captured in the UI (0).",
    )
    parser.add_argument(
        "--selected-id-header",
        default="",
        help="Optional workbook header selected by the user as the Id field for the High-Potential Sites report.",
    )
    parser.add_argument(
        "--pause-after-preprocess",
        action="store_true",
        help="Pause after preprocess phase06 generation and wait for manual validation before running the model pipeline.",
    )
    parser.add_argument(
        "--phase06-input",
        type=Path,
        default=None,
        help="Resume mode: existing phase06 workbook to use as the input of the model pipeline.",
    )
    return parser


def main() -> None:
    parser = build_argument_parser()
    args = parser.parse_args()

    run_dir = args.run_dir.resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    progress = ProgressReporter(args.progress_file.resolve() if args.progress_file else None)
    selected_model_id = args.selected_model_id.strip() or None
    selected_germplasm_names = (
        json.loads(args.selected_germplasm_names_json)
        if args.selected_germplasm_names_json
        else []
    )
    selected_germplasm_row_ids = (
        json.loads(args.selected_germplasm_row_ids_json)
        if args.selected_germplasm_row_ids_json
        else []
    )
    selected_germplasm_projection_mode = args.selected_germplasm_projection_mode.strip()
    selected_germplasm_selection_mode = args.selected_germplasm_selection_mode.strip() or "all_matches"
    selected_id_header = args.selected_id_header.strip()
    forecast_planting_date = args.forecast_planting_date.strip()
    forecast_harvesting_date = args.forecast_harvesting_date.strip()
    climate_scope = args.climate_scope.strip() or "point"
    regional_country = args.regional_country.strip()
    regional_bounds_label = args.regional_bounds_label.strip()
    use_source_row_dates = str(args.use_source_row_dates).strip().lower() not in {"0", "false", "no"}
    if args.pause_after_preprocess and selected_model_id and (
        not forecast_planting_date or not forecast_harvesting_date
    ):
        raise ValueError(
            "The saved-model forecast flow requires both --forecast-planting-date and --forecast-harvesting-date."
        )
    if climate_scope in {"country_localities", "regional_country"} and not regional_country:
        raise ValueError("The selected climate mode requires a country selection.")
    if climate_scope == "regional_manual" and any(
        value is None
        for value in (
            args.regional_bounds_latitude_min,
            args.regional_bounds_latitude_max,
            args.regional_bounds_longitude_min,
            args.regional_bounds_longitude_max,
        )
    ):
        raise ValueError("Regional manual climate mode requires latitude_min, latitude_max, longitude_min, and longitude_max.")
    progress_callback = (
        lambda percent, stage, message, details=None: progress.update(
            percent,
            stage,
            message,
            details=details,
        )
    )

    try:
        preprocess = None
        model = None
        phase06_input = args.phase06_input.resolve() if args.phase06_input else None
        projection_template_workbook = (
            args.projection_template_workbook.resolve()
            if args.projection_template_workbook
            else None
        )
        if phase06_input is None:
            if args.input is None:
                raise ValueError("An input workbook is required when --phase06-input is not provided.")
            if selected_model_id and not args.pause_after_preprocess:
                if climate_scope == "regional_manual":
                    ce_saved_prediction = run_ce_saved_model_prediction(
                        args.input.resolve(),
                        run_dir,
                        selected_model_id=selected_model_id,
                        forecast_planting_date=forecast_planting_date,
                        forecast_harvesting_date=forecast_harvesting_date,
                        selected_germplasm_names=selected_germplasm_names,
                        selected_germplasm_row_ids=selected_germplasm_row_ids,
                        selected_germplasm_selection_mode=selected_germplasm_selection_mode,
                        regional_bounds_label=regional_bounds_label or "Manual bounds",
                        regional_bounds_latitude_min=float(args.regional_bounds_latitude_min),
                        regional_bounds_latitude_max=float(args.regional_bounds_latitude_max),
                        regional_bounds_longitude_min=float(args.regional_bounds_longitude_min),
                        regional_bounds_longitude_max=float(args.regional_bounds_longitude_max),
                        nasa_grid_resolution_km=args.nasa_grid_resolution_km,
                        use_source_row_dates=use_source_row_dates,
                        selected_id_header=selected_id_header,
                        progress_callback=progress_callback,
                    )
                    progress.update(
                        100,
                        "Prediction complete",
                        "The saved-model manual bounding-box prediction finished successfully.",
                        details={
                            "phase06_xlsx": str(ce_saved_prediction.summary.get("phase06_xlsx", "")),
                            "preprocess_ready": True,
                        },
                    )
                    print(json.dumps(ce_saved_prediction.summary, ensure_ascii=False))
                    return
                saved_prediction = run_saved_model_prediction(
                    args.input.resolve(),
                    run_dir,
                    progress_callback=progress_callback,
                    selected_model_id=selected_model_id,
                    forecast_planting_date=forecast_planting_date or None,
                    forecast_harvesting_date=forecast_harvesting_date or None,
                    climate_scope=climate_scope,
                    regional_country=regional_country or None,
                    selected_germplasm_names=selected_germplasm_names or None,
                    selected_germplasm_projection_mode=selected_germplasm_projection_mode or None,
                    projection_template_workbook=projection_template_workbook,
                    regional_bounds_label=regional_bounds_label or None,
                    regional_bounds_latitude_min=args.regional_bounds_latitude_min,
                    regional_bounds_latitude_max=args.regional_bounds_latitude_max,
                    regional_bounds_longitude_min=args.regional_bounds_longitude_min,
                    regional_bounds_longitude_max=args.regional_bounds_longitude_max,
                    nasa_grid_resolution_km=args.nasa_grid_resolution_km,
                )
                preprocess = saved_prediction.preprocess
                model = saved_prediction.model
                phase06_input = preprocess.phase06_xlsx
            else:
                preprocess = run_preprocess_pipeline(
                    args.input.resolve(),
                    run_dir / "preprocess",
                    progress_callback=progress_callback,
                    forecast_planting_date=forecast_planting_date or None,
                    forecast_harvesting_date=forecast_harvesting_date or None,
                    climate_scope=climate_scope,
                    regional_country=regional_country or None,
                    selected_model_id=selected_model_id,
                    selected_germplasm_names=selected_germplasm_names or None,
                    selected_germplasm_projection_mode=selected_germplasm_projection_mode or None,
                    projection_template_workbook=projection_template_workbook,
                    regional_bounds_label=regional_bounds_label or None,
                    regional_bounds_latitude_min=args.regional_bounds_latitude_min,
                    regional_bounds_latitude_max=args.regional_bounds_latitude_max,
                    regional_bounds_longitude_min=args.regional_bounds_longitude_min,
                    regional_bounds_longitude_max=args.regional_bounds_longitude_max,
                    nasa_grid_resolution_km=args.nasa_grid_resolution_km,
                )
                phase06_input = preprocess.phase06_xlsx
                progress.update(
                    52,
                    "Preprocess output ready",
                    "The preprocess phase06 workbook is ready and Original Data can be mapped while the downstream pipeline continues.",
                    details={
                        "phase06_xlsx": str(preprocess.phase06_xlsx),
                        "preprocess_summary_file": str(preprocess.summary_file),
                        "preprocess_ready": True,
                    },
                )
                if args.pause_after_preprocess:
                    summary = {
                        "run_dir": str(run_dir),
                        "input_workbook": str(preprocess.input_workbook),
                        "preprocess_dir": str(preprocess.run_dir),
                        "preprocess_summary_file": str(preprocess.summary_file),
                        "phase06_xlsx": str(preprocess.phase06_xlsx),
                        "preprocess_log": preprocess.summary.get("preprocess_log", {}),
                        "manual_bbox_grid": preprocess.summary.get("manual_bbox_grid"),
                        "task_report": [*preprocess.summary["task_report"]],
                        "paused_after_preprocess": True,
                    }
                    (run_dir / "summary.json").write_text(
                        json.dumps(summary, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    progress.pause(
                        52,
                        "Preprocess validation required",
                        "The preprocess phase06 workbook is ready for manual validation. Download it and continue when you approve the output.",
                        details={
                            "phase06_xlsx": str(preprocess.phase06_xlsx),
                            "preprocess_summary_file": str(preprocess.summary_file),
                            "paused_after_preprocess": True,
                        },
                    )
                    print(json.dumps(summary, ensure_ascii=False))
                    return
        if model is None:
            model = run_model_pipeline(
                phase06_input,
                run_dir,
                progress_callback=progress_callback,
                selected_model_id=selected_model_id,
            )
        preprocess_summary = {}
        preprocess_task_report = []
        preprocess_input_workbook = ""
        preprocess_run_dir = ""
        preprocess_summary_file = ""
        if preprocess is not None:
            preprocess_summary = preprocess.summary
            preprocess_task_report = preprocess.summary["task_report"]
            preprocess_input_workbook = str(preprocess.input_workbook)
            preprocess_run_dir = str(preprocess.run_dir)
            preprocess_summary_file = str(preprocess.summary_file)
        else:
            existing_preprocess_summary_file = run_dir / "preprocess" / "summary.json"
            if existing_preprocess_summary_file.exists():
                preprocess_summary = json.loads(existing_preprocess_summary_file.read_text(encoding="utf-8"))
                preprocess_task_report = preprocess_summary.get("task_report", [])
                preprocess_input_workbook = str(preprocess_summary.get("input_workbook", ""))
                preprocess_run_dir = str(run_dir / "preprocess")
                preprocess_summary_file = str(existing_preprocess_summary_file)
        summary = {
            "run_dir": str(run_dir),
            "input_workbook": preprocess_input_workbook,
            "preprocess_dir": preprocess_run_dir,
            "preprocess_summary_file": preprocess_summary_file,
            "preprocess_log": preprocess_summary.get("preprocess_log", {}),
            "manual_bbox_grid": preprocess_summary.get("manual_bbox_grid"),
            "selected_germplasm_names": selected_germplasm_names,
            "selected_germplasm_row_ids": selected_germplasm_row_ids,
            "selected_germplasm_projection_mode": selected_germplasm_projection_mode,
            "selected_germplasm_selection_mode": selected_germplasm_selection_mode,
            "selected_id_header": selected_id_header,
            "climate_scope": climate_scope,
            "phase06_xlsx": str(phase06_input),
            "phase2_csv": model.summary["phase2_csv"],
            "phase3_csv": model.summary["phase3_csv"],
            "phase4_csv": model.summary["phase4_csv"],
            "phase5_csv": model.summary["phase5_csv"],
            "phase_analysis_dir": model.summary["phase_analysis_dir"],
            "phase_analysis_model_id": model.summary["phase_analysis_model_id"],
            "phase_analysis_model_dir": model.summary["phase_analysis_model_dir"],
            "phase_analysis_created_at": model.summary["phase_analysis_created_at"],
            "phase_analysis_description": model.summary["phase_analysis_description"],
            "phase_analysis_skipped": model.summary["phase_analysis_skipped"],
            "phase_analysis_metric_name": model.summary["phase_analysis_metric_name"],
            "phase_analysis_metric_value": model.summary["phase_analysis_metric_value"],
            "model_input_csv": model.summary["model_input_csv"],
            "prediction_csv": model.summary["prediction_csv"],
            "prediction_xlsx": model.summary["prediction_xlsx"],
            "prediction_model_name": model.summary["prediction_model_name"],
            "prediction_feature_count": model.summary["prediction_feature_count"],
            "prediction_model_id": model.summary["prediction_model_id"],
            "prediction_model_created_at": model.summary["prediction_model_created_at"],
            "prediction_model_display_name": model.summary["prediction_model_display_name"],
            "prediction_model_description": model.summary["prediction_model_description"],
            "prediction_model_metric_name": model.summary["prediction_model_metric_name"],
            "prediction_model_metric_value": model.summary["prediction_model_metric_value"],
            "geojson_file": str(model.geojson_file),
            "total_features": model.geojson["metadata"]["total_features"],
            "task_report": [
                *preprocess_task_report,
                *model.summary["task_report"],
            ],
        }
        (run_dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        source_name = (
            args.input.name
            if args.input is not None
            else Path(preprocess_input_workbook).name
            if preprocess_input_workbook
            else args.phase06_input.name
            if args.phase06_input is not None
            else "the uploaded workbook"
        )
        progress.complete(
            f"File processed successfully: {source_name}.",
            details={"prediction_model_name": summary["prediction_model_name"]},
        )
        print(json.dumps(summary, ensure_ascii=False))
    except Exception as error:
        progress.error(str(error))
        raise


if __name__ == "__main__":
    main()
