from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
MODELS_DIR = ROOT_DIR / "pipeline" / "model"
MODEL_METADATA_FILE = "metadata.json"


@dataclass
class RegisteredModel:
    model_id: str
    model_dir: Path
    metadata: dict[str, Any]


def ensure_models_dir() -> Path:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    return MODELS_DIR


def get_model_dir(model_id: str) -> Path:
    return ensure_models_dir() / model_id


def get_model_metadata_path(model_dir: Path) -> Path:
    return model_dir / MODEL_METADATA_FILE


def read_model_metadata(model_dir: Path) -> dict[str, Any] | None:
    metadata_path = get_model_metadata_path(model_dir)
    if not metadata_path.exists():
        return None
    return json.loads(metadata_path.read_text(encoding="utf-8"))


def write_model_metadata(model_dir: Path, metadata: dict[str, Any]) -> None:
    metadata_path = get_model_metadata_path(model_dir)
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")


def list_registered_models() -> list[RegisteredModel]:
    models_root = ensure_models_dir()
    models: list[RegisteredModel] = []

    for child in models_root.iterdir():
        if not child.is_dir():
            continue
        metadata = read_model_metadata(child)
        if metadata is None:
            continue
        model_id = str(metadata.get("model_id") or child.name)
        models.append(RegisteredModel(model_id=model_id, model_dir=child, metadata=metadata))

    models.sort(
        key=lambda item: str(item.metadata.get("created_at") or item.model_id),
        reverse=True,
    )
    return models


def get_latest_registered_model() -> RegisteredModel | None:
    models = list_registered_models()
    return models[0] if models else None


def get_registered_model(model_id: str) -> RegisteredModel | None:
    normalized_model_id = model_id.strip()
    if not normalized_model_id:
        return None
    for registered_model in list_registered_models():
        if registered_model.model_id == normalized_model_id:
            return registered_model
    return None


def delete_registered_model(model_id: str) -> bool:
    registered_model = get_registered_model(model_id)
    if registered_model is None:
        return False
    shutil.rmtree(registered_model.model_dir)
    return True


def rename_registered_model(model_id: str, display_name: str) -> RegisteredModel | None:
    registered_model = get_registered_model(model_id)
    if registered_model is None:
        return None
    normalized_display_name = display_name.strip()
    metadata = dict(registered_model.metadata)
    metadata["display_name"] = normalized_display_name
    write_model_metadata(registered_model.model_dir, metadata)
    return RegisteredModel(
        model_id=registered_model.model_id,
        model_dir=registered_model.model_dir,
        metadata=metadata,
    )


def build_download_url(file_path: str | Path | None) -> str:
    if not file_path:
        return ""
    resolved = Path(file_path).expanduser().resolve()
    try:
        relative = resolved.relative_to(ROOT_DIR)
    except ValueError:
        return ""
    return f"/{relative.as_posix()}"


def build_model_api_url(model_id: str, suffix: str) -> str:
    return f"/api/models/{model_id}/{suffix.lstrip('/')}"


def list_models_for_ui() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for registered_model in list_registered_models():
        metadata = registered_model.metadata
        featurehero_params = metadata.get("featurehero_params") or {}
        machines = featurehero_params.get("machines") or []
        optimization_csv = metadata.get("optimization_csv") or (
            registered_model.model_dir / "optimization_sort_original.csv"
        )
        items.append(
            {
                "model_id": registered_model.model_id,
                "display_name": metadata.get("display_name", ""),
                "created_at": metadata.get("created_at", ""),
                "description": metadata.get("description", ""),
                "machine_name": metadata.get("machine_name", ""),
                "selected_feature_count": metadata.get("selected_feature_count", 0),
                "metric_name": metadata.get("metric_name", ""),
                "metric_value": metadata.get("metric_value"),
                "target_column": metadata.get("target_column", ""),
                "selected_features": metadata.get("selected_features", []),
                "number_generation": featurehero_params.get("number_generation"),
                "number_population": featurehero_params.get("number_population"),
                "machine_keys": [str(machine) for machine in machines],
                "download_urls": {
                    "best_model_pkl": build_model_api_url(
                        registered_model.model_id,
                        "best-model.pkl",
                    ),
                    "best_features_csv": build_model_api_url(
                        registered_model.model_id,
                        "best-features.csv",
                    ),
                    "optimization_csv": build_model_api_url(
                        registered_model.model_id,
                        "optimization.csv",
                    ),
                    "selection_summary_csv": build_model_api_url(
                        registered_model.model_id,
                        "selection-summary.csv",
                    ),
                },
                "is_active": False,
            }
        )

    if items:
        items[0]["is_active"] = True
    return items
