"""Exercise the separate CE processes used by New Workspace, without PYTHONPATH."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from ce_pipeline.phase01.phase1 import read_sheet_headers_and_rows, write_xlsx

ROOT = Path(__file__).resolve().parents[1]


class CeScriptEntrypointsTest(unittest.TestCase):
    def run_phase(self, phase: str, cwd: Path, *arguments: str) -> dict:
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        env.pop("PYTHONHOME", None)
        script = "phase1.py" if phase == "phase01" else "phase02.py"
        result = subprocess.run(
            [sys.executable, str(ROOT / "ce_pipeline" / phase / script), *map(str, arguments)],
            cwd=cwd, env=env, capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_new_workspace_phase01_and_phase02_as_independent_processes(self):
        # This folder intentionally lies outside the source checkout and has spaces.
        with tempfile.TemporaryDirectory(prefix="new workspace ") as directory:
            root = Path(directory)
            source = root / "input.xlsx"
            definition = root / "selection.json"
            phase1 = root / "phase1.xlsx"
            phase2 = root / "phase2.xlsx"
            log = root / "phase2.json"
            settings = {
                "target_column":"Yield", "longitude_column":"Longitude", "latitude_column":"Latitude",
                "planting_date_column":"Planting", "harvesting_date_column":"Harvesting",
                "soil_texture_column":"Soil", "soil_depth_column":"Depth",
            }
            headers = ["Name", "Farm", *settings.values()]
            record = {"Name":"CIM-RT-EAPP1-E -013", "Farm":"001", "Yield":"5.5",
                "Longitude":"36.817223", "Latitude":"-1.286389", "Planting":"2026-03-01",
                "Harvesting":"2026-08-01", "Soil":"Loam", "Depth":"75"}
            write_xlsx(source, headers, [record, {**record, "Name":"Invalid target", "Yield":"0"}])
            definition.write_text(json.dumps({"initial_settings":settings,
                "divisions":{"germplams_identifiers":["Name", "Farm"]}}), encoding="utf-8")
            created = self.run_phase("phase01", root,
                "--source-workbook",source,"--definition-file",definition,"--output-file",phase1)
            self.assertEqual(created["row_count"], 2)
            validated = self.run_phase("phase02", root,
                "--phase01-workbook",phase1,"--definition-file",definition,
                "--output-file",phase2,"--log-file",log)
            self.assertEqual(validated["kept_row_count"], 1)
            self.assertEqual(validated["removed_row_count"], 1)
            self.assertEqual(validated["removed_by_reason"]["invalid_target_value"], 1)
            _, rows = read_sheet_headers_and_rows(phase2)
            self.assertEqual(rows[0]["Name"], record["Name"])
            self.assertEqual(rows[0]["Farm"], "001")
            self.assertEqual(rows[0]["Yield"], "5.5")
            self.assertEqual(json.loads(log.read_text())["kept_row_count"], 1)


if __name__ == "__main__":
    unittest.main()
