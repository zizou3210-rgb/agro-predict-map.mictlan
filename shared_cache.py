from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import RLock
from typing import Any

from config_env import resolve_shared_cache_dir


_DB_LOCK = RLock()
CLIMATE_FEATURE_CACHE_VERSION = 2
SOIL_CACHE_VERSION = 1
NASA_CACHE_KIND = "nasa_series"
CLIMATE_FEATURE_CACHE_KIND = "climate_features"
SOIL_CACHE_KIND = "soil_points"
SQLITE_BATCH_SIZE = 400


def resolve_shared_cache_db_path() -> Path:
    return resolve_shared_cache_dir() / "shared_cache.sqlite3"


def _connect(db_path: Path | None = None) -> sqlite3.Connection:
    target_path = db_path or resolve_shared_cache_db_path()
    target_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(target_path, timeout=30, check_same_thread=False)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.execute("PRAGMA temp_store=MEMORY")
    _ensure_schema(connection)
    return connection


def _ensure_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS climate_feature_cache (
            cache_key TEXT PRIMARY KEY,
            cache_version INTEGER NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_accessed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS nasa_series_cache (
            cache_key TEXT PRIMARY KEY,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_accessed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS soil_point_cache (
            cache_key TEXT PRIMARY KEY,
            cache_version INTEGER NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_accessed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS cache_metadata (
            metadata_key TEXT PRIMARY KEY,
            metadata_value TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )


def _read_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _get_metadata(connection: sqlite3.Connection, key: str) -> str | None:
    row = connection.execute(
        "SELECT metadata_value FROM cache_metadata WHERE metadata_key = ?",
        (key,),
    ).fetchone()
    if row is None:
        return None
    return str(row[0])


def _set_metadata(connection: sqlite3.Connection, key: str, value: str) -> None:
    connection.execute(
        """
        INSERT INTO cache_metadata (metadata_key, metadata_value)
        VALUES (?, ?)
        ON CONFLICT(metadata_key) DO UPDATE SET
            metadata_value = excluded.metadata_value,
            updated_at = CURRENT_TIMESTAMP
        """,
        (key, value),
    )


def _resolve_legacy_nasa_cache_path() -> Path:
    return resolve_shared_cache_dir() / "nasa_power_cache.json"


def _resolve_legacy_climate_feature_cache_path() -> Path:
    return resolve_shared_cache_dir() / "climate_feature_cache.json"


def _resolve_legacy_soil_cache_path() -> Path:
    return resolve_shared_cache_dir() / "soilgrids_cache.json"


def _ensure_nasa_seeded(connection: sqlite3.Connection) -> None:
    if _get_metadata(connection, "seeded:nasa_series_cache") == "1":
        return
    legacy_path = _resolve_legacy_nasa_cache_path()
    payload = _read_json_file(legacy_path)
    rows = []
    for raw_key, value in payload.items():
        if not isinstance(raw_key, str) or not isinstance(value, dict):
            continue
        parts = raw_key.split("|")
        if len(parts) != 4:
            continue
        rows.append((raw_key, json.dumps(value, ensure_ascii=False, sort_keys=True)))
    if rows:
        connection.executemany(
            """
            INSERT INTO nasa_series_cache (cache_key, payload_json)
            VALUES (?, ?)
            ON CONFLICT(cache_key) DO NOTHING
            """,
            rows,
        )
    _set_metadata(connection, "seeded:nasa_series_cache", "1")


def _ensure_climate_feature_seeded(connection: sqlite3.Connection) -> None:
    if _get_metadata(connection, "seeded:climate_feature_cache") == "1":
        return
    payload = _read_json_file(_resolve_legacy_climate_feature_cache_path())
    if payload.get("cache_version") != CLIMATE_FEATURE_CACHE_VERSION or not isinstance(payload.get("entries"), dict):
        _set_metadata(connection, "seeded:climate_feature_cache", "1")
        return
    rows = [
        (
            cache_key,
            CLIMATE_FEATURE_CACHE_VERSION,
            json.dumps(value, ensure_ascii=False, sort_keys=True),
        )
        for cache_key, value in payload["entries"].items()
        if isinstance(cache_key, str) and isinstance(value, dict)
    ]
    if rows:
        connection.executemany(
            """
            INSERT INTO climate_feature_cache (cache_key, cache_version, payload_json)
            VALUES (?, ?, ?)
            ON CONFLICT(cache_key) DO NOTHING
            """,
            rows,
        )
    _set_metadata(connection, "seeded:climate_feature_cache", "1")


def _ensure_soil_seeded(connection: sqlite3.Connection) -> None:
    if _get_metadata(connection, "seeded:soil_point_cache") == "1":
        return
    payload = _read_json_file(_resolve_legacy_soil_cache_path())
    points = payload.get("points", {}) if isinstance(payload, dict) else {}
    rows = [
        (
            cache_key,
            SOIL_CACHE_VERSION,
            json.dumps(value, ensure_ascii=False, sort_keys=True),
        )
        for cache_key, value in points.items()
        if isinstance(cache_key, str) and isinstance(value, dict)
    ]
    if rows:
        connection.executemany(
            """
            INSERT INTO soil_point_cache (cache_key, cache_version, payload_json)
            VALUES (?, ?, ?)
            ON CONFLICT(cache_key) DO NOTHING
            """,
            rows,
        )
    _set_metadata(connection, "seeded:soil_point_cache", "1")


def load_climate_feature_cache(path: Path, *, use_sqlite: bool = True) -> dict[str, dict[str, object]]:
    if not use_sqlite:
        payload = _read_json_file(path)
        if payload.get("cache_version") != CLIMATE_FEATURE_CACHE_VERSION or not isinstance(payload.get("entries"), dict):
            return {}
        return payload["entries"]

    with _DB_LOCK:
        with _connect() as connection:
            _ensure_climate_feature_seeded(connection)
            rows = connection.execute(
                """
                SELECT cache_key, payload_json
                FROM climate_feature_cache
                WHERE cache_version = ?
                """,
                (CLIMATE_FEATURE_CACHE_VERSION,),
            ).fetchall()

    cache: dict[str, dict[str, object]] = {}
    for cache_key, payload_json in rows:
        try:
            payload = json.loads(payload_json)
        except json.JSONDecodeError:
            continue
        if isinstance(cache_key, str) and isinstance(payload, dict):
            cache[cache_key] = payload
    return cache


def _chunk_values(values: list[str], chunk_size: int = SQLITE_BATCH_SIZE) -> list[list[str]]:
    return [values[index:index + chunk_size] for index in range(0, len(values), chunk_size)]


def _update_last_accessed_at(
    connection: sqlite3.Connection,
    table_name: str,
    cache_keys: list[str],
) -> None:
    if not cache_keys:
        return
    for chunk in _chunk_values(cache_keys):
        placeholders = ", ".join("?" for _ in chunk)
        connection.execute(
            f"""
            UPDATE {table_name}
            SET last_accessed_at = CURRENT_TIMESTAMP
            WHERE cache_key IN ({placeholders})
            """,
            tuple(chunk),
        )


def get_climate_feature_cache_entry(
    serialized_key: str,
    *,
    db_path: Path | None = None,
    touch_access: bool = True,
) -> dict[str, object] | None:
    payloads = get_climate_feature_cache_entries(
        [serialized_key],
        db_path=db_path,
        touch_access=touch_access,
    )
    return payloads.get(serialized_key)


def get_climate_feature_cache_entries(
    serialized_keys: list[str],
    *,
    db_path: Path | None = None,
    touch_access: bool = True,
) -> dict[str, dict[str, object]]:
    normalized_keys = [key for key in serialized_keys if isinstance(key, str) and key]
    if not normalized_keys:
        return {}

    payloads: dict[str, dict[str, object]] = {}
    with _DB_LOCK:
        with _connect(db_path) as connection:
            _ensure_climate_feature_seeded(connection)
            for chunk in _chunk_values(normalized_keys):
                placeholders = ", ".join("?" for _ in chunk)
                rows = connection.execute(
                    f"""
                    SELECT cache_key, payload_json
                    FROM climate_feature_cache
                    WHERE cache_version = ? AND cache_key IN ({placeholders})
                    """,
                    (CLIMATE_FEATURE_CACHE_VERSION, *chunk),
                ).fetchall()
                for cache_key, payload_json in rows:
                    try:
                        payload = json.loads(payload_json)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(cache_key, str) and isinstance(payload, dict):
                        payloads[cache_key] = payload

            missing_keys = [key for key in normalized_keys if key not in payloads]
            if missing_keys:
                legacy_payload = _read_json_file(_resolve_legacy_climate_feature_cache_path())
                legacy_entries = legacy_payload.get("entries", {}) if isinstance(legacy_payload, dict) else {}
                migrated_rows = []
                if isinstance(legacy_entries, dict):
                    for missing_key in missing_keys:
                        legacy_entry = legacy_entries.get(missing_key)
                        if not isinstance(legacy_entry, dict):
                            continue
                        payloads[missing_key] = legacy_entry
                        migrated_rows.append(
                            (
                                missing_key,
                                CLIMATE_FEATURE_CACHE_VERSION,
                                json.dumps(legacy_entry, ensure_ascii=False, sort_keys=True),
                            )
                        )
                if migrated_rows:
                    connection.executemany(
                        """
                        INSERT INTO climate_feature_cache (cache_key, cache_version, payload_json)
                        VALUES (?, ?, ?)
                        ON CONFLICT(cache_key) DO UPDATE SET
                            payload_json = excluded.payload_json,
                            last_accessed_at = CURRENT_TIMESTAMP
                        """,
                        migrated_rows,
                    )
            if touch_access:
                _update_last_accessed_at(connection, "climate_feature_cache", list(payloads.keys()))
    return payloads


def save_climate_feature_cache(
    path: Path,
    cache: dict[str, dict[str, object]],
    *,
    use_sqlite: bool = True,
) -> None:
    if not use_sqlite:
        _write_json_file(
            path,
            {
                "cache_version": CLIMATE_FEATURE_CACHE_VERSION,
                "entries": cache,
            },
        )
        return
    upsert_climate_feature_cache_entries(cache)


def upsert_climate_feature_cache_entries(
    entries: dict[str, dict[str, object]],
    *,
    db_path: Path | None = None,
) -> None:
    if not entries:
        return
    rows = [
        (
            cache_key,
            CLIMATE_FEATURE_CACHE_VERSION,
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
        )
        for cache_key, payload in entries.items()
        if isinstance(cache_key, str) and isinstance(payload, dict)
    ]
    if not rows:
        return
    with _DB_LOCK:
        with _connect(db_path) as connection:
            connection.executemany(
                """
                INSERT INTO climate_feature_cache (cache_key, cache_version, payload_json)
                VALUES (?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    cache_version = excluded.cache_version,
                    payload_json = excluded.payload_json,
                    last_accessed_at = CURRENT_TIMESTAMP
                """,
                rows,
            )


def load_nasa_cache(path: Path, *, use_sqlite: bool = True) -> dict[tuple[str, str, str, str], dict[str, dict[str, float | None]]]:
    if not use_sqlite:
        payload = _read_json_file(path)
        cache: dict[tuple[str, str, str, str], dict[str, dict[str, float | None]]] = {}
        for raw_key, value in payload.items():
            if not isinstance(raw_key, str):
                continue
            parts = raw_key.split("|")
            if len(parts) != 4 or not isinstance(value, dict):
                continue
            cache[(parts[0], parts[1], parts[2], parts[3])] = value
        return cache

    with _DB_LOCK:
        with _connect() as connection:
            _ensure_nasa_seeded(connection)
            rows = connection.execute(
                "SELECT cache_key, payload_json FROM nasa_series_cache"
            ).fetchall()
    cache: dict[tuple[str, str, str, str], dict[str, dict[str, float | None]]] = {}
    for cache_key, payload_json in rows:
        if not isinstance(cache_key, str):
            continue
        parts = cache_key.split("|")
        if len(parts) != 4:
            continue
        try:
            payload = json.loads(payload_json)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            cache[(parts[0], parts[1], parts[2], parts[3])] = payload
    return cache


def get_nasa_cache_entry(
    cache_key: tuple[str, str, str, str],
    *,
    db_path: Path | None = None,
    touch_access: bool = True,
) -> dict[str, dict[str, float | None]] | None:
    payloads = get_nasa_cache_entries(
        [cache_key],
        db_path=db_path,
        touch_access=touch_access,
    )
    return payloads.get(cache_key)


def get_nasa_cache_entries(
    cache_keys: list[tuple[str, str, str, str]],
    *,
    db_path: Path | None = None,
    touch_access: bool = True,
) -> dict[tuple[str, str, str, str], dict[str, dict[str, float | None]]]:
    normalized_pairs = [
        (cache_key, "|".join(cache_key))
        for cache_key in cache_keys
        if len(cache_key) == 4
    ]
    if not normalized_pairs:
        return {}

    serialized_to_tuple = {serialized: cache_key for cache_key, serialized in normalized_pairs}
    payloads: dict[tuple[str, str, str, str], dict[str, dict[str, float | None]]] = {}
    with _DB_LOCK:
        with _connect(db_path) as connection:
            _ensure_nasa_seeded(connection)
            serialized_keys = list(serialized_to_tuple.keys())
            found_serialized: set[str] = set()
            for chunk in _chunk_values(serialized_keys):
                placeholders = ", ".join("?" for _ in chunk)
                rows = connection.execute(
                    f"""
                    SELECT cache_key, payload_json
                    FROM nasa_series_cache
                    WHERE cache_key IN ({placeholders})
                    """,
                    tuple(chunk),
                ).fetchall()
                for serialized_key, payload_json in rows:
                    try:
                        payload = json.loads(payload_json)
                    except json.JSONDecodeError:
                        continue
                    cache_key = serialized_to_tuple.get(str(serialized_key))
                    if cache_key is not None and isinstance(payload, dict):
                        payloads[cache_key] = payload
                        found_serialized.add(str(serialized_key))

            missing_serialized = [key for key in serialized_keys if key not in found_serialized]
            if missing_serialized:
                legacy_payload = _read_json_file(_resolve_legacy_nasa_cache_path())
                migrated_rows = []
                for serialized_key in missing_serialized:
                    legacy_entry = legacy_payload.get(serialized_key)
                    if not isinstance(legacy_entry, dict):
                        continue
                    cache_key = serialized_to_tuple.get(serialized_key)
                    if cache_key is None:
                        continue
                    payloads[cache_key] = legacy_entry
                    migrated_rows.append(
                        (serialized_key, json.dumps(legacy_entry, ensure_ascii=False, sort_keys=True))
                    )
                if migrated_rows:
                    connection.executemany(
                        """
                        INSERT INTO nasa_series_cache (cache_key, payload_json)
                        VALUES (?, ?)
                        ON CONFLICT(cache_key) DO UPDATE SET
                            payload_json = excluded.payload_json,
                            last_accessed_at = CURRENT_TIMESTAMP
                        """,
                        migrated_rows,
                    )
            if touch_access:
                _update_last_accessed_at(connection, "nasa_series_cache", list(found_serialized))
    return payloads


def save_nasa_cache(
    path: Path,
    cache: dict[tuple[str, str, str, str], dict[str, dict[str, float | None]]],
    *,
    use_sqlite: bool = True,
) -> None:
    if not use_sqlite:
        serialized = {"|".join(key): value for key, value in sorted(cache.items())}
        _write_json_file(path, serialized)
        return
    upsert_nasa_cache_entries(cache)


def upsert_nasa_cache_entries(
    entries: dict[tuple[str, str, str, str], dict[str, dict[str, float | None]]],
    *,
    db_path: Path | None = None,
) -> None:
    if not entries:
        return
    rows = [
        ("|".join(key), json.dumps(payload, ensure_ascii=False, sort_keys=True))
        for key, payload in entries.items()
        if len(key) == 4 and isinstance(payload, dict)
    ]
    if not rows:
        return
    with _DB_LOCK:
        with _connect(db_path) as connection:
            connection.executemany(
                """
                INSERT INTO nasa_series_cache (cache_key, payload_json)
                VALUES (?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    last_accessed_at = CURRENT_TIMESTAMP
                """,
                rows,
            )


def merge_nasa_cache_json_into_sqlite(source_cache: Path, *, db_path: Path | None = None) -> None:
    source_payload = _read_json_file(source_cache)
    if not source_payload:
        return
    entries: dict[tuple[str, str, str, str], dict[str, dict[str, float | None]]] = {}
    for raw_key, value in source_payload.items():
        if not isinstance(raw_key, str) or not isinstance(value, dict):
            continue
        parts = raw_key.split("|")
        if len(parts) != 4:
            continue
        entries[(parts[0], parts[1], parts[2], parts[3])] = value
    upsert_nasa_cache_entries(entries, db_path=db_path)


def load_soil_cache_payload(path: Path, *, use_sqlite: bool = True) -> dict[str, Any]:
    if not use_sqlite:
        return _read_json_file(path)

    payload = {"version": SOIL_CACHE_VERSION, "points": {}}
    with _DB_LOCK:
        with _connect() as connection:
            _ensure_soil_seeded(connection)
            rows = connection.execute(
                """
                SELECT cache_key, payload_json
                FROM soil_point_cache
                WHERE cache_version = ?
                """,
                (SOIL_CACHE_VERSION,),
            ).fetchall()
    for cache_key, payload_json in rows:
        try:
            point_payload = json.loads(payload_json)
        except json.JSONDecodeError:
            continue
        if isinstance(cache_key, str) and isinstance(point_payload, dict):
            payload["points"][cache_key] = point_payload
    return payload


def get_soil_cache_entry(
    cache_key: str,
    *,
    db_path: Path | None = None,
) -> dict[str, Any] | None:
    with _DB_LOCK:
        with _connect(db_path) as connection:
            _ensure_soil_seeded(connection)
            row = connection.execute(
                """
                SELECT payload_json
                FROM soil_point_cache
                WHERE cache_key = ? AND cache_version = ?
                """,
                (cache_key, SOIL_CACHE_VERSION),
            ).fetchone()
            if row is None:
                legacy_payload = _read_json_file(_resolve_legacy_soil_cache_path())
                legacy_points = legacy_payload.get("points", {}) if isinstance(legacy_payload, dict) else {}
                legacy_entry = legacy_points.get(cache_key) if isinstance(legacy_points, dict) else None
                if isinstance(legacy_entry, dict):
                    connection.execute(
                        """
                        INSERT INTO soil_point_cache (cache_key, cache_version, payload_json)
                        VALUES (?, ?, ?)
                        ON CONFLICT(cache_key) DO UPDATE SET
                            payload_json = excluded.payload_json,
                            last_accessed_at = CURRENT_TIMESTAMP
                        """,
                        (
                            cache_key,
                            SOIL_CACHE_VERSION,
                            json.dumps(legacy_entry, ensure_ascii=False, sort_keys=True),
                        ),
                    )
                    row = (json.dumps(legacy_entry, ensure_ascii=False, sort_keys=True),)
                else:
                    return None
            connection.execute(
                """
                UPDATE soil_point_cache
                SET last_accessed_at = CURRENT_TIMESTAMP
                WHERE cache_key = ?
                """,
                (cache_key,),
            )
    try:
        payload = json.loads(row[0])
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def write_soil_cache_payload(path: Path, payload: dict[str, Any], *, use_sqlite: bool = True) -> None:
    if not use_sqlite:
        _write_json_file(path, payload)
        return
    points = payload.get("points", {}) if isinstance(payload, dict) else {}
    upsert_soil_cache_entries(points if isinstance(points, dict) else {})


def upsert_soil_cache_entries(
    entries: dict[str, dict[str, Any]],
    *,
    db_path: Path | None = None,
) -> None:
    if not entries:
        return
    rows = [
        (
            cache_key,
            SOIL_CACHE_VERSION,
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
        )
        for cache_key, payload in entries.items()
        if isinstance(cache_key, str) and isinstance(payload, dict)
    ]
    if not rows:
        return
    with _DB_LOCK:
        with _connect(db_path) as connection:
            connection.executemany(
                """
                INSERT INTO soil_point_cache (cache_key, cache_version, payload_json)
                VALUES (?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    cache_version = excluded.cache_version,
                    payload_json = excluded.payload_json,
                    last_accessed_at = CURRENT_TIMESTAMP
                """,
                rows,
            )


def merge_soil_cache_json_into_sqlite(source_cache: Path, *, db_path: Path | None = None) -> None:
    source_payload = _read_json_file(source_cache)
    points = source_payload.get("points", {}) if isinstance(source_payload, dict) else {}
    if isinstance(points, dict):
        upsert_soil_cache_entries(points, db_path=db_path)
