import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.resource_paths import get_featurehero_python


class FeatureHeroPythonTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.current = self.root / "current-python"
        self.current.touch()
        self.enterContext(patch.dict(os.environ, {"APP_FEATUREHERO_PYTHON": "", "APP_PIPELINE_PYTHON": ""}))
        self.enterContext(patch("pipeline.resource_paths.APP_RESOURCES_DIR", self.root / "resources"))
        self.enterContext(patch("pipeline.resource_paths.sys.executable", str(self.current)))
        self.probe = self.enterContext(patch("pipeline.resource_paths.subprocess.run"))
        self.probe.return_value = subprocess.CompletedProcess([], 0)

    def test_pipeline_python_is_used_when_vendored_venv_is_broken(self):
        broken = self.root / "resources/featurehero/.venv/bin/python"
        broken.parent.mkdir(parents=True)
        broken.symlink_to(self.root / "missing-python3.12")
        pipeline = self.root / "pipeline-python"
        pipeline.touch()
        with patch.dict(os.environ, {"APP_PIPELINE_PYTHON": str(pipeline)}):
            self.assertEqual(get_featurehero_python(), pipeline)

    def test_featurehero_override_takes_precedence(self):
        override = self.root / "featurehero-python"
        override.touch()
        with patch.dict(os.environ, {"APP_FEATUREHERO_PYTHON": str(override),
                                     "APP_PIPELINE_PYTHON": str(self.current)}):
            self.assertEqual(get_featurehero_python(), override)

    def test_current_python_is_used_without_vendored_venv(self):
        self.assertEqual(get_featurehero_python(), self.current)

    def test_vendored_python_retains_precedence_over_current_python(self):
        vendored = self.root / "resources/featurehero/.venv/bin/python"
        vendored.parent.mkdir(parents=True)
        vendored.touch()
        self.assertEqual(get_featurehero_python(), vendored)

    def test_incompatible_override_falls_back_to_current_python312(self):
        incompatible = self.root / "python314"
        incompatible.touch()
        self.probe.side_effect = lambda args, **kwargs: subprocess.CompletedProcess(
            args, 1 if args[0] == str(incompatible) else 0,
        )
        with patch.dict(os.environ, {"APP_FEATUREHERO_PYTHON": str(incompatible)}):
            self.assertEqual(get_featurehero_python(), self.current)

    def test_no_compatible_python_produces_actionable_error(self):
        self.probe.return_value = subprocess.CompletedProcess([], 1)
        with self.assertRaisesRegex(FileNotFoundError, "Python 3.12.*APP_FEATUREHERO_PYTHON"):
            get_featurehero_python()


if __name__ == "__main__":
    unittest.main()
