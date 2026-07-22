from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import shared_cache


class SharedCacheTest(unittest.TestCase):
    def test_climate_feature_cache_entry_round_trip_uses_sqlite(self) -> None:
        with tempfile.TemporaryDirectory(prefix="shared_cache_sqlite_") as tmp_dir_name:
            db_path = Path(tmp_dir_name) / "shared_cache.sqlite3"
            entries = {
                "v2|CHC_0p05_R1C2|2026-01-01|2026-03-15": {
                    "series_key": {
                        "pixel_id": "CHC_0p05_R1C2",
                        "date_of_planting": "2026-01-01",
                        "date_of_harvesting": "2026-03-15",
                    },
                    "output_row": {"planting_week_1_total_prectotcorr": "14"},
                    "audit_row": {"forecast_reference_year": "2025"},
                }
            }
            with patch("shared_cache.resolve_shared_cache_db_path", return_value=db_path):
                shared_cache.upsert_climate_feature_cache_entries(entries)
                loaded = shared_cache.get_climate_feature_cache_entry(
                    "v2|CHC_0p05_R1C2|2026-01-01|2026-03-15"
                )

            self.assertEqual(loaded, entries["v2|CHC_0p05_R1C2|2026-01-01|2026-03-15"])

    def test_nasa_cache_entry_round_trip_uses_sqlite(self) -> None:
        with tempfile.TemporaryDirectory(prefix="shared_nasa_sqlite_") as tmp_dir_name:
            db_path = Path(tmp_dir_name) / "shared_cache.sqlite3"
            entries = {
                ("1.25", "32.50", "2026-01-01", "2026-03-15"): {
                    "T2M": {"20260101": 20.0},
                    "PRECTOTCORR": {"20260101": 1.0},
                }
            }
            with patch("shared_cache.resolve_shared_cache_db_path", return_value=db_path):
                shared_cache.upsert_nasa_cache_entries(entries)
                loaded = shared_cache.get_nasa_cache_entry(
                    ("1.25", "32.50", "2026-01-01", "2026-03-15")
                )

            self.assertEqual(loaded, entries[("1.25", "32.50", "2026-01-01", "2026-03-15")])

    def test_soil_cache_entry_round_trip_uses_sqlite(self) -> None:
        with tempfile.TemporaryDirectory(prefix="shared_soil_sqlite_") as tmp_dir_name:
            db_path = Path(tmp_dir_name) / "shared_cache.sqlite3"
            entries = {
                "1.250000,32.500000": {
                    "Soil type/texture": "Loam",
                    "soil_source": "soilgrids",
                }
            }
            with patch("shared_cache.resolve_shared_cache_db_path", return_value=db_path):
                shared_cache.upsert_soil_cache_entries(entries)
                loaded = shared_cache.get_soil_cache_entry("1.250000,32.500000")

            self.assertEqual(loaded, entries["1.250000,32.500000"])

    def test_nasa_cache_entry_migrates_from_legacy_json_on_first_read(self) -> None:
        with tempfile.TemporaryDirectory(prefix="shared_nasa_migration_") as tmp_dir_name:
            temp_dir = Path(tmp_dir_name)
            db_path = temp_dir / "shared_cache.sqlite3"
            legacy_cache_dir = temp_dir / "cache"
            legacy_cache_dir.mkdir(parents=True, exist_ok=True)
            legacy_nasa_json = legacy_cache_dir / "nasa_power_cache.json"
            legacy_nasa_json.write_text(
                '{"1.25|32.50|2026-01-01|2026-03-15":{"T2M":{"20260101":20.0},"PRECTOTCORR":{"20260101":1.0}}}',
                encoding="utf-8",
            )
            with patch("shared_cache.resolve_shared_cache_db_path", return_value=db_path), patch(
                "shared_cache.resolve_shared_cache_dir", return_value=legacy_cache_dir
            ):
                loaded = shared_cache.get_nasa_cache_entry(
                    ("1.25", "32.50", "2026-01-01", "2026-03-15")
                )
                migrated = shared_cache.load_nasa_cache(legacy_nasa_json, use_sqlite=True)

            self.assertEqual(loaded, migrated[("1.25", "32.50", "2026-01-01", "2026-03-15")])


if __name__ == "__main__":
    unittest.main()
