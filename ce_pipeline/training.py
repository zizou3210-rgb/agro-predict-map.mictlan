#!/usr/bin/env python3
from __future__ import annotations

if __package__ in {None, ""}:
    import sys
    from pathlib import Path

    APP_BOOT_DIR = Path(__file__).resolve().parents[1]
    PACKAGE_PARENT = APP_BOOT_DIR
    if str(PACKAGE_PARENT) not in sys.path:
        sys.path.insert(0, str(PACKAGE_PARENT))

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from ce_pipeline.phase04.phase04 import CANONICAL_TARGET_COLUMN
from ce_pipeline.phase05.phase05 import run_ce_phase05
from ce_pipeline.prediction.prediction import update_saved_model_prediction_metadata
from pipeline.phase_analysis import run_phase_analysis


@dataclass
class CeTrainingOutputs:
    summary: dict[str, object]
    geojson: dict[str, object]
    summary_file: Path
    geojson_file: Path
    prediction_summary: dict[str, object]
    prediction_geojson: dict[str, object]


def run_ce_training(
    phase04_workbook: Path,
    training_input_csv: Path,
    run_dir: Path,
    *,
    source_name: str,
    target_column: str,
    progress_file: Path | None = None,
) -> CeTrainingOutputs:
    run_dir.mkdir(parents=True, exist_ok=True)

    training_df = pd.read_csv(training_input_csv, dtype=object)
    training_df.columns = [str(column).strip() for column in training_df.columns]

    def training_progress_callback(percent: int, stage: str, message: str) -> None:
        if progress_file is None:
            return
        normalized_percent = max(0, min(100, int(percent)))
        overall_percent = 50 + round((normalized_percent / 100) * 45)
        payload: dict[str, object] = {
            "status": "running",
            "percent": max(0, min(100, int(overall_percent))),
            "stage": stage,
            "message": message,
            "details": {
                "phase": "training",
                "target_column": target_column,
                "featurehero_percent": normalized_percent,
            },
        }
        progress_file.parent.mkdir(parents=True, exist_ok=True)
        progress_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if CANONICAL_TARGET_COLUMN not in training_df.columns:
        raise KeyError(f"Missing canonical target column in phase04 training input: {CANONICAL_TARGET_COLUMN}")

    phase_analysis = run_phase_analysis(
        training_df,
        run_dir / "phase_analysis",
        training_input_csv,
        target_column=target_column,
        progress_callback=training_progress_callback,
    )
    run_root = phase04_workbook.parents[2] if len(phase04_workbook.parents) >= 3 else run_dir.parent.parent
    selection_summary_file = run_root / "selection_summary.json"
    phase04_selected_fields_csv = phase04_workbook.parent / "phase04_selected_fields.csv"
    phase04_normalization_stats_file = phase04_workbook.parent / "phase04_normalization_stats.json"
    phase_analysis.metadata = update_saved_model_prediction_metadata(
        model_dir=phase_analysis.model_dir,
        metadata=phase_analysis.metadata,
        selection_summary_file=selection_summary_file if selection_summary_file.exists() else None,
        phase04_selected_fields_csv=phase04_selected_fields_csv if phase04_selected_fields_csv.exists() else None,
        phase04_workbook=phase04_workbook if phase04_workbook.exists() else None,
        phase04_training_input_csv=training_input_csv if training_input_csv.exists() else None,
        phase04_normalization_stats_file=(
            phase04_normalization_stats_file if phase04_normalization_stats_file.exists() else None
        ),
    )
    phase05_outputs = run_ce_phase05(
        phase04_workbook=phase04_workbook,
        training_input_csv=training_input_csv,
        run_dir=run_dir / "phase05",
        source_name=source_name,
        target_column=target_column,
        selected_model_id=phase_analysis.model_id,
        progress_file=progress_file,
    )

    summary = {
        "workflow": "ce_pipeline_training",
        "source_name": source_name,
        "target_column": target_column,
        "canonical_target_column": CANONICAL_TARGET_COLUMN,
        "phase04_xlsx": str(phase04_workbook),
        "phase04_selected_fields_csv": str((phase04_workbook.parent / "phase04_selected_fields.csv")),
        "phase04_training_csv": str(training_input_csv),
        "phase04_training_xlsx": str(training_input_csv.with_suffix(".xlsx")),
        "phase_analysis_dir": str(run_dir / "phase_analysis"),
        "phase_analysis_model_id": phase_analysis.model_id,
        "phase_analysis_model_dir": str(phase_analysis.model_dir),
        "phase_analysis_created_at": phase_analysis.metadata.get("created_at", ""),
        "phase_analysis_description": phase_analysis.description,
        "phase_analysis_skipped": False,
        "phase_analysis_metric_name": phase_analysis.metadata.get("metric_name", ""),
        "phase_analysis_metric_value": phase_analysis.metadata.get("metric_value"),
        "model_input_csv": phase05_outputs.summary["model_input_csv"],
        "prediction_csv": phase05_outputs.summary["prediction_csv"],
        "prediction_xlsx": phase05_outputs.summary["prediction_xlsx"],
        "prediction_model_raw_csv": phase05_outputs.summary["prediction_model_raw_csv"],
        "prediction_model_raw_xlsx": phase05_outputs.summary["prediction_model_raw_xlsx"],
        "prediction_model_name": phase05_outputs.summary["prediction_model_name"],
        "prediction_feature_count": phase05_outputs.summary["prediction_feature_count"],
        "prediction_model_id": phase05_outputs.summary["prediction_model_id"],
        "prediction_model_created_at": phase05_outputs.summary["prediction_model_created_at"],
        "prediction_model_display_name": phase05_outputs.summary["prediction_model_display_name"],
        "prediction_model_description": phase05_outputs.summary["prediction_model_description"],
        "prediction_model_metric_name": phase05_outputs.summary["prediction_model_metric_name"],
        "prediction_model_metric_value": phase05_outputs.summary["prediction_model_metric_value"],
        "phase05_summary_file": str(phase05_outputs.summary_file),
        "phase05_geojson_file": str(phase05_outputs.geojson_file),
        "phase05_run_dir": str(run_dir / "phase05"),
        "geojson_file": str(phase05_outputs.geojson_file),
        "total_features": phase05_outputs.geojson["metadata"]["total_features"],
        "task_report": [
            {
                "phase": "phase04",
                "title": "Preparing ce_pipeline training dataset",
                "output_file": str(phase04_workbook),
            },
            {
                "phase": "phase_analysis",
                "title": "Running FeatureHero model analysis",
                "output_file": str((run_dir / "phase_analysis") / "summary.json"),
            },
            *phase05_outputs.summary.get("task_report", []),
        ],
    }
    summary_file = run_dir / "summary.json"
    summary_file.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return CeTrainingOutputs(
        summary=summary,
        geojson=phase05_outputs.geojson,
        summary_file=summary_file,
        geojson_file=phase05_outputs.geojson_file,
        prediction_summary=phase05_outputs.summary,
        prediction_geojson=phase05_outputs.geojson,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run ce_pipeline training using the phase04 dataset.")
    parser.add_argument("--phase04-workbook", required=True, help="Path to the generated phase04 workbook.")
    parser.add_argument("--training-input-csv", required=True, help="Path to the generated phase04 training CSV.")
    parser.add_argument("--run-dir", required=True, help="Directory where training artifacts will be created.")
    parser.add_argument("--source-name", default="phase04.xlsx", help="Source workbook name for metadata.")
    parser.add_argument("--target-column", required=True, help="Original target column selected in Initial Settings.")
    parser.add_argument("--progress-file", default="", help="Optional JSON progress file updated while FeatureHero training runs.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    progress_file = Path(args.progress_file).expanduser().resolve() if str(args.progress_file).strip() else None
    outputs = run_ce_training(
        phase04_workbook=Path(args.phase04_workbook).expanduser().resolve(),
        training_input_csv=Path(args.training_input_csv).expanduser().resolve(),
        run_dir=Path(args.run_dir).expanduser().resolve(),
        source_name=str(args.source_name or "phase04.xlsx"),
        target_column=str(args.target_column or "").strip(),
        progress_file=progress_file,
    )
    print(json.dumps({
        "summary_file": str(outputs.summary_file),
        "geojson_file": str(outputs.geojson_file),
        "summary": outputs.summary,
        "geojson": outputs.geojson,
        "prediction_summary": outputs.prediction_summary,
        "prediction_geojson": outputs.prediction_geojson,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
