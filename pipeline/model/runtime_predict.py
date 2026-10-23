from __future__ import annotations

import argparse
import json
import pickle
import os
from pathlib import Path

import pandas as pd


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Grain Yield model inference.")
    parser.add_argument("--model-file", required=True, type=Path)
    parser.add_argument("--input-csv", required=True, type=Path)
    parser.add_argument("--output-json", required=True, type=Path)
    parser.add_argument("--progress-json", type=Path)
    return parser


def predict_batches(model, df, report, batch_size=4096):
    predictions = []
    report(0, len(df))
    for start in range(0, len(df), batch_size):
        predictions.extend(model.prediction(df.iloc[start:start + batch_size].to_numpy()).tolist())
        report(min(start + batch_size, len(df)), len(df))
    return predictions


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    with args.model_file.open("rb") as handle:
        model = pickle.load(handle)

    df = pd.read_csv(args.input_csv)
    if args.progress_json:
        def report(completed, total):
            temporary = args.progress_json.with_suffix(".tmp")
            temporary.write_text(json.dumps({"completed": completed, "total": total}), encoding="utf-8")
            os.replace(temporary, args.progress_json)
        predictions = predict_batches(model, df, report)
    else:
        predictions = model.prediction(df.to_numpy()).tolist()
    args.output_json.write_text(
        json.dumps({"predictions": predictions}, ensure_ascii=False),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
