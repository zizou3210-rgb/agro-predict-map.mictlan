from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline import model_registry


class TestModelRegistry(unittest.TestCase):
    def test_rename_registered_model_updates_display_name_without_changing_id(self) -> None:
        with tempfile.TemporaryDirectory(prefix="app_model_registry_") as temp_dir:
            models_dir = Path(temp_dir) / "model"
            model_dir = models_dir / "20260511-123456"
            model_dir.mkdir(parents=True, exist_ok=True)
            metadata_path = model_dir / "metadata.json"
            metadata_path.write_text(
                json.dumps(
                    {
                        "model_id": "20260511-123456",
                        "created_at": "2026-05-11T12:34:56",
                        "description": "Auto generated model.",
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            with patch.object(model_registry, "MODELS_DIR", models_dir):
                updated = model_registry.rename_registered_model("20260511-123456", "Kenya April Run")

            self.assertIsNotNone(updated)
            self.assertEqual(updated.model_id, "20260511-123456")
            persisted = json.loads(metadata_path.read_text(encoding="utf-8"))
            self.assertEqual(persisted["display_name"], "Kenya April Run")
            self.assertEqual(persisted["model_id"], "20260511-123456")


if __name__ == "__main__":
    unittest.main()
