from __future__ import annotations

import json
import os
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent
APP_RUNTIME_NAME = "MictlanAgriXGBoost"
APP_ENV_FILE = APP_DIR / ".env"
APP_PACKAGE_FILE = APP_DIR / "package.json"
APP_SETTINGS_ENV_KEYS = (
    "APP_FEATUREHERO_NUMBER_GENERATION",
    "APP_FEATUREHERO_NUMBER_POPULATION",
    "APP_FEATUREHERO_MACHINES",
    "APP_FEATUREHERO_METRIC",
    "APP_NASA_POWER_RESOLUTION_KM",
    "APP_FEATUREHERO_JOB_TIMEOUT_SECONDS",
)
SUPPORTED_FEATUREHERO_MACHINES = {
    "extreme_gradient_boost_regression",
    "random_forest_regression",
      "lasso_regression",
    "support_vector_regression",
}
SUPPORTED_FEATUREHERO_METRICS = {
    "mean_absolute_error",
    "root_mean_squared_error",
}
SUPPORTED_NASA_POWER_RESOLUTION_KM = set(range(1, 11))


def resolve_runtime_root() -> Path:
    override = os.environ.get("APP_RUNTIME_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()

    home = Path.home()
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
        if local_app_data:
            return Path(local_app_data) / APP_RUNTIME_NAME
        return home / "AppData" / "Local" / APP_RUNTIME_NAME

    if os.sys.platform == "darwin":
        return home / "Library" / "Application Support" / APP_RUNTIME_NAME

    xdg_data_home = os.environ.get("XDG_DATA_HOME", "").strip()
    if xdg_data_home and "/snap/code/" in xdg_data_home:
        return home / ".local" / "share" / APP_RUNTIME_NAME
    if xdg_data_home:
        return Path(xdg_data_home).expanduser() / APP_RUNTIME_NAME
    return home / ".local" / "share" / APP_RUNTIME_NAME


def resolve_shared_cache_dir() -> Path:
    return resolve_runtime_root() / "cache"


def load_app_env(env_file: Path | None = None) -> dict[str, str]:
    target_file = env_file or APP_ENV_FILE
    values: dict[str, str] = {}
    if not target_file.exists():
        return values

    for raw_line in target_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        key = key.strip()
        value = raw_value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key] = value
        os.environ.setdefault(key, value)

    return values


def _get_int(name: str, default: int) -> int:
    raw_value = os.environ.get(name, "").strip()
    if not raw_value:
        return default
    return int(raw_value)


def _get_bool(name: str, default: bool) -> bool:
    raw_value = os.environ.get(name, "").strip().lower()
    if not raw_value:
        return default
    if raw_value in {"1", "true", "yes", "on"}:
        return True
    if raw_value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(
        f"{name} must be a boolean-like value such as 1/0, true/false, yes/no, or on/off."
    )


def _get_json_list(name: str, default: list[str]) -> list[str]:
    raw_value = os.environ.get(name, "").strip()
    if not raw_value:
        return default
    parsed = json.loads(raw_value)
    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        raise ValueError(f"{name} must be a JSON array of strings.")
    return parsed


def get_app_version() -> str:
    load_app_env()
    configured = os.environ.get("APP_VERSION", "").strip()
    if configured:
        return configured
    if APP_PACKAGE_FILE.exists():
        try:
            payload = json.loads(APP_PACKAGE_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        version = str(payload.get("version", "")).strip()
        if version:
            return version
    return "1.0.0"


def get_preprocess_validation_enabled() -> bool:
    load_app_env()
    return _get_bool("APP_ENABLE_PREPROCESS_VALIDATION", True)


def get_ce_pipeline_download_enabled() -> bool:
    load_app_env()
    return _get_bool("CIMMYT_APP_ENABLE_CE_PIPELINE_DOWNLOAD", True)


def get_training_results_download_dev_enabled() -> bool:
    load_app_env()
    return _get_bool("APP_DEV_ENABLE_TRAINING_RESULTS_DOWNLOAD", False)


def get_prediction_bridge_dev_row_limit() -> int:
    load_app_env()
    value = _get_int("APP_DEV_PREDICTION_BRIDGE_ROW_LIMIT", 0)
    if value < 0:
        raise ValueError("APP_DEV_PREDICTION_BRIDGE_ROW_LIMIT must be zero or a positive integer.")
    return value


def get_nasa_power_resolution_km() -> int:
    load_app_env()
    value = _get_int("APP_NASA_POWER_RESOLUTION_KM", 5)
    if value not in SUPPORTED_NASA_POWER_RESOLUTION_KM:
        allowed = ", ".join(str(item) for item in sorted(SUPPORTED_NASA_POWER_RESOLUTION_KM))
        raise ValueError(
            f"APP_NASA_POWER_RESOLUTION_KM must be one of: {allowed}."
        )
    return value


def get_featurehero_params() -> dict[str, object]:
    load_app_env()
    params = {
        "number_generation": _get_int("APP_FEATUREHERO_NUMBER_GENERATION", 200),
        "number_population": _get_int("APP_FEATUREHERO_NUMBER_POPULATION", 120),
        "machines": _get_json_list(
            "APP_FEATUREHERO_MACHINES",
            ["extreme_gradient_boost_regression"],
        ),
        "metric": os.environ.get("APP_FEATUREHERO_METRIC", "mean_absolute_error").strip()
        or "mean_absolute_error",
    }
    number_generation = int(params["number_generation"])
    number_population = int(params["number_population"])
    if number_generation < 10:
        raise ValueError(
            "APP_FEATUREHERO_NUMBER_GENERATION must be an integer greater than or equal to 10."
        )
    if number_population < 10:
        raise ValueError(
            "APP_FEATUREHERO_NUMBER_POPULATION must be an integer greater than or equal to 10."
        )
    if number_population % 10 != 0:
        raise ValueError(
            "APP_FEATUREHERO_NUMBER_POPULATION must be a multiple of 10."
        )
    return params


def get_featurehero_job_timeout_seconds() -> int:
    load_app_env()
    value = _get_int("APP_FEATUREHERO_JOB_TIMEOUT_SECONDS", 21600)
    if value < 600:
        raise ValueError("APP_FEATUREHERO_JOB_TIMEOUT_SECONDS must be greater than or equal to 600.")
    return value


def get_featurehero_settings() -> dict[str, object]:
    params = get_featurehero_params()
    return {
        "number_generation": int(params["number_generation"]),
        "number_population": int(params["number_population"]),
        "machines": [str(item) for item in params["machines"]],
        "metric": str(params["metric"]),
        "nasa_power_resolution_km": get_nasa_power_resolution_km(),
    }


def validate_featurehero_settings(payload: dict[str, object]) -> dict[str, object]:
    number_generation = int(payload.get("number_generation", 0))
    number_population = int(payload.get("number_population", 0))
    machines = payload.get("machines", [])
    metric = str(payload.get("metric", "")).strip()
    nasa_power_resolution_km = int(payload.get("nasa_power_resolution_km", 0))
    if number_generation < 10:
        raise ValueError("APP_FEATUREHERO_NUMBER_GENERATION must be an integer greater than or equal to 10.")
    if number_population < 10:
        raise ValueError("APP_FEATUREHERO_NUMBER_POPULATION must be an integer greater than or equal to 10.")
    if number_population % 10 != 0:
        raise ValueError("APP_FEATUREHERO_NUMBER_POPULATION must be a multiple of 10.")
    if not isinstance(machines, list) or not machines or not all(str(item).strip() for item in machines):
        raise ValueError("APP_FEATUREHERO_MACHINES must be a non-empty JSON array of strings.")
    normalized_machines = [str(item).strip() for item in machines]
    unsupported_machines = [item for item in normalized_machines if item not in SUPPORTED_FEATUREHERO_MACHINES]
    if unsupported_machines:
        raise ValueError(f"Unsupported FeatureHero machine(s): {', '.join(unsupported_machines)}.")
    if metric not in SUPPORTED_FEATUREHERO_METRICS:
        raise ValueError(f"Unsupported FeatureHero metric: {metric}.")
    if nasa_power_resolution_km not in SUPPORTED_NASA_POWER_RESOLUTION_KM:
        allowed = ", ".join(str(value) for value in sorted(SUPPORTED_NASA_POWER_RESOLUTION_KM))
        raise ValueError(
            f"Unsupported NASA POWER resolution: {nasa_power_resolution_km}. Allowed values: {allowed} km."
        )
    return {
        "number_generation": number_generation,
        "number_population": number_population,
        "machines": normalized_machines,
        "metric": metric,
        "nasa_power_resolution_km": nasa_power_resolution_km,
    }


def update_featurehero_settings(
    payload: dict[str, object],
    env_file: Path | None = None,
) -> dict[str, object]:
    validated = validate_featurehero_settings(payload)
    target_file = env_file or APP_ENV_FILE
    existing_lines = (
        target_file.read_text(encoding="utf-8").splitlines()
        if target_file.exists()
        else []
    )
    replacement_map = {
        "APP_FEATUREHERO_NUMBER_GENERATION": str(validated["number_generation"]),
        "APP_FEATUREHERO_NUMBER_POPULATION": str(validated["number_population"]),
        "APP_FEATUREHERO_MACHINES": json.dumps(validated["machines"], ensure_ascii=False),
        "APP_FEATUREHERO_METRIC": str(validated["metric"]),
        "APP_NASA_POWER_RESOLUTION_KM": str(validated["nasa_power_resolution_km"]),
        "APP_FEATUREHERO_JOB_TIMEOUT_SECONDS": str(get_featurehero_job_timeout_seconds()),
    }
    updated_lines: list[str] = []
    seen_keys: set[str] = set()
    for raw_line in existing_lines:
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#") or "=" not in raw_line:
            updated_lines.append(raw_line)
            continue
        key, _ = raw_line.split("=", 1)
        normalized_key = key.strip()
        if normalized_key in replacement_map:
            updated_lines.append(f"{normalized_key}={replacement_map[normalized_key]}")
            seen_keys.add(normalized_key)
        else:
            updated_lines.append(raw_line)
    for key, value in replacement_map.items():
        if key not in seen_keys:
            updated_lines.append(f"{key}={value}")
    target_file.write_text("\n".join(updated_lines).rstrip() + "\n", encoding="utf-8")
    os.environ["APP_FEATUREHERO_NUMBER_GENERATION"] = replacement_map["APP_FEATUREHERO_NUMBER_GENERATION"]
    os.environ["APP_FEATUREHERO_NUMBER_POPULATION"] = replacement_map["APP_FEATUREHERO_NUMBER_POPULATION"]
    os.environ["APP_FEATUREHERO_MACHINES"] = replacement_map["APP_FEATUREHERO_MACHINES"]
    os.environ["APP_FEATUREHERO_METRIC"] = replacement_map["APP_FEATUREHERO_METRIC"]
    os.environ["APP_NASA_POWER_RESOLUTION_KM"] = replacement_map["APP_NASA_POWER_RESOLUTION_KM"]
    os.environ["APP_FEATUREHERO_JOB_TIMEOUT_SECONDS"] = replacement_map["APP_FEATUREHERO_JOB_TIMEOUT_SECONDS"]
    return validated
