from __future__ import annotations

import argparse
import json
import pickle
from pathlib import Path

import pandas as pd


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Grain Yield model inference.")
    parser.add_argument("--model-file", required=True, type=Path)
    parser.add_argument("--input-csv", required=True, type=Path)
    parser.add_argument("--output-json", required=True, type=Path)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    with args.model_file.open("rb") as handle:
        model = pickle.load(handle)

    df = pd.read_csv(args.input_csv)
    predictions = model.prediction(df.to_numpy()).tolist()
    args.output_json.write_text(
        json.dumps({"predictions": predictions}, ensure_ascii=False),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
