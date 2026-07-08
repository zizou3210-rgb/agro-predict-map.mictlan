from __future__ import annotations

from math import hypot, isfinite
from typing import Any


def _as_float(value: object) -> float | None:
    if value in {None, ""}:
        return None
    try:
        numeric = float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None
    return numeric if isfinite(numeric) else None


def _normalized_value_cells(
    grid_cells: list[dict[str, Any]],
    predicted_lookup: dict[str, float],
) -> list[dict[str, float | str]]:
    normalized: list[dict[str, float | str]] = []
    for cell in grid_cells:
        grid_cell_id = str(cell.get("grid_cell_id") or "").strip()
        predicted_value = predicted_lookup.get(grid_cell_id)
        if not grid_cell_id or predicted_value is None or not isfinite(predicted_value):
            continue
        center_longitude = _as_float(cell.get("center_longitude"))
        center_latitude = _as_float(cell.get("center_latitude"))
        longitude_min = _as_float(cell.get("longitude_min"))
        longitude_max = _as_float(cell.get("longitude_max"))
        latitude_min = _as_float(cell.get("latitude_min"))
        latitude_max = _as_float(cell.get("latitude_max"))
        if None in {center_longitude, center_latitude, longitude_min, longitude_max, latitude_min, latitude_max}:
            continue
        normalized.append({
            "grid_cell_id": grid_cell_id,
            "predicted_value": float(predicted_value),
            "center_longitude": float(center_longitude),
            "center_latitude": float(center_latitude),
            "longitude_min": float(longitude_min),
            "longitude_max": float(longitude_max),
            "latitude_min": float(latitude_min),
            "latitude_max": float(latitude_max),
        })
    return normalized


def _build_backend_idw_surface(
    valued_cells: list[dict[str, float | str]],
    *,
    subdivisions_per_cell: int,
    neighbor_count: int,
    weight_power: float,
) -> list[dict[str, float | str]]:
    samples: list[dict[str, float | str]] = []
    for cell in valued_cells:
        lon_step = (float(cell["longitude_max"]) - float(cell["longitude_min"])) / subdivisions_per_cell
        lat_step = (float(cell["latitude_max"]) - float(cell["latitude_min"])) / subdivisions_per_cell
        for row in range(subdivisions_per_cell):
            for column in range(subdivisions_per_cell):
                longitude_min = float(cell["longitude_min"]) + lon_step * column
                longitude_max = float(cell["longitude_max"]) if column == subdivisions_per_cell - 1 else longitude_min + lon_step
                latitude_min = float(cell["latitude_min"]) + lat_step * row
                latitude_max = float(cell["latitude_max"]) if row == subdivisions_per_cell - 1 else latitude_min + lat_step
                center_longitude = (longitude_min + longitude_max) / 2
                center_latitude = (latitude_min + latitude_max) / 2
                nearest_cells = sorted(
                    (
                        {
                            "cell": valued_cell,
                            "distance": hypot(
                                center_longitude - float(valued_cell["center_longitude"]),
                                center_latitude - float(valued_cell["center_latitude"]),
                            ) or 0.000001,
                        }
                        for valued_cell in valued_cells
                    ),
                    key=lambda item: item["distance"],
                )[:neighbor_count]
                weighted_value = 0.0
                total_weight = 0.0
                for item in nearest_cells:
                    distance = float(item["distance"])
                    weight = 1 / distance ** weight_power
                    weighted_value += float(item["cell"]["predicted_value"]) * weight
                    total_weight += weight
                samples.append({
                    "id": f'{cell["grid_cell_id"]}:{row}:{column}',
                    "longitudeMin": longitude_min,
                    "longitudeMax": longitude_max,
                    "latitudeMin": latitude_min,
                    "latitudeMax": latitude_max,
                    "predictedValue": weighted_value / total_weight if total_weight > 0 else float(cell["predicted_value"]),
                })
    return samples


def _build_backend_kriging_surface(
    valued_cells: list[dict[str, float | str]],
    *,
    subdivisions_per_cell: int,
) -> list[dict[str, float | str]] | None:
    try:
        import numpy as np
        from pykrige.ok import OrdinaryKriging
    except Exception:
        return None

    longitudes = np.array([float(cell["center_longitude"]) for cell in valued_cells], dtype=float)
    latitudes = np.array([float(cell["center_latitude"]) for cell in valued_cells], dtype=float)
    values = np.array([float(cell["predicted_value"]) for cell in valued_cells], dtype=float)
    if len(values) < 3:
        return None

    try:
        kriging = OrdinaryKriging(
            longitudes,
            latitudes,
            values,
            variogram_model="linear",
            verbose=False,
            enable_plotting=False,
        )
    except Exception:
        return None

    samples: list[dict[str, float | str]] = []
    for cell in valued_cells:
        lon_step = (float(cell["longitude_max"]) - float(cell["longitude_min"])) / subdivisions_per_cell
        lat_step = (float(cell["latitude_max"]) - float(cell["latitude_min"])) / subdivisions_per_cell
        for row in range(subdivisions_per_cell):
            for column in range(subdivisions_per_cell):
                longitude_min = float(cell["longitude_min"]) + lon_step * column
                longitude_max = float(cell["longitude_max"]) if column == subdivisions_per_cell - 1 else longitude_min + lon_step
                latitude_min = float(cell["latitude_min"]) + lat_step * row
                latitude_max = float(cell["latitude_max"]) if row == subdivisions_per_cell - 1 else latitude_min + lat_step
                center_longitude = (longitude_min + longitude_max) / 2
                center_latitude = (latitude_min + latitude_max) / 2
                try:
                    interpolated, _ = kriging.execute("points", [center_longitude], [center_latitude])
                    predicted_value = float(interpolated[0])
                except Exception:
                    return None
                samples.append({
                    "id": f'{cell["grid_cell_id"]}:{row}:{column}',
                    "longitudeMin": longitude_min,
                    "longitudeMax": longitude_max,
                    "latitudeMin": latitude_min,
                    "latitudeMax": latitude_max,
                    "predictedValue": predicted_value,
                })
    return samples


def build_manual_grid_interpolated_surface(
    grid_cells: list[dict[str, Any]],
    predicted_lookup: dict[str, float],
    *,
    minimum_valid_cells: int = 12,
    subdivisions_per_cell: int = 12,
    neighbor_count: int = 12,
    weight_power: float = 1.15,
) -> dict[str, Any]:
    valued_cells = _normalized_value_cells(grid_cells, predicted_lookup)
    valid_cell_count = len(valued_cells)
    if valid_cell_count < minimum_valid_cells:
        return {
            "method": "mean",
            "valid_cell_count": valid_cell_count,
            "sample_count": 0,
            "samples": [],
        }

    kriging_samples = _build_backend_kriging_surface(
        valued_cells,
        subdivisions_per_cell=subdivisions_per_cell,
    )
    if kriging_samples:
        return {
            "method": "kriging",
            "valid_cell_count": valid_cell_count,
            "sample_count": len(kriging_samples),
            "samples": kriging_samples,
        }

    idw_samples = _build_backend_idw_surface(
        valued_cells,
        subdivisions_per_cell=subdivisions_per_cell,
        neighbor_count=neighbor_count,
        weight_power=weight_power,
    )
    return {
        "method": "idw",
        "valid_cell_count": valid_cell_count,
        "sample_count": len(idw_samples),
        "samples": idw_samples,
    }
